"""
J.A.R.V.I.S — Web Research Engine

Active internet research capability: fetch, parse, extract knowledge, cache results.

Features:
    - Multi-backend web search (DuckDuckGo, Wikipedia, Google CSE)
    - HTML parsing with clean text extraction (stdlib + optional BeautifulSoup)
    - Pattern-based knowledge extraction into knowledge graph triples
    - Research caching with configurable TTL
    - Security-specific research (CVE, technology, OSINT)
    - Rate limiting, timeouts, thread safety
    - Graceful degradation on network failures

Usage:
    researcher = WebResearcher(jarvis=jarvis_instance)
    result = researcher.research("Python asyncio", depth="deep")
    print(result.summary)
    print(result.facts_extracted)

    # Security research
    cve = researcher.research_cve("CVE-2024-1234")
    tech = researcher.research_technology("Apache 2.4")
    target = researcher.research_target("example.com")
"""

import hashlib
import json
import logging
import os
import re
import ssl
import threading
import time
from dataclasses import dataclass, field, asdict
from datetime import datetime, timedelta
from html.parser import HTMLParser
from pathlib import Path
from typing import Optional
from urllib.parse import urlencode, urljoin, urlparse, quote

logger = logging.getLogger("jarvis.web_research")

# ---------------------------------------------------------------------------
# Optional imports — degrade gracefully
# ---------------------------------------------------------------------------

try:
    import requests as _requests
    _HAS_REQUESTS = True
except ImportError:
    _requests = None
    _HAS_REQUESTS = False

try:
    from bs4 import BeautifulSoup as _BeautifulSoup
    _HAS_BS4 = True
except ImportError:
    _BeautifulSoup = None
    _HAS_BS4 = False

# Standard library HTTP — always available
import urllib.request
import urllib.error

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

CACHE_PATH = Path.home() / ".jarvis_research_cache.json"
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/125.0.0.0 Safari/537.36 JARVIS/1.0"
)
REQUEST_TIMEOUT = 10  # seconds
MAX_REQUESTS_PER_SECOND = 5
MAX_CONTENT_LENGTH = 500_000  # ~500 KB text limit per page

# TTL presets (seconds)
TTL_NEWS = 3600          # 1 hour
TTL_GENERAL = 86400      # 24 hours
TTL_TECHNICAL = 604800   # 7 days


# ---------------------------------------------------------------------------
# ResearchResult dataclass
# ---------------------------------------------------------------------------

@dataclass
class ResearchResult:
    """Holds the output of a research query."""
    query: str = ""
    summary: str = ""
    sources: list = field(default_factory=list)        # [{url, title, snippet, relevance}]
    facts_extracted: list = field(default_factory=list) # list of str
    references: list = field(default_factory=list)      # list of URLs
    confidence: float = 0.0                             # 0–1
    knowledge_stored: int = 0                           # facts pushed to knowledge graph

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "ResearchResult":
        return cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})


# ---------------------------------------------------------------------------
# Rate limiter (token bucket, thread-safe)
# ---------------------------------------------------------------------------

class _RateLimiter:
    """Simple token-bucket rate limiter."""

    def __init__(self, max_per_second: int = MAX_REQUESTS_PER_SECOND):
        self._interval = 1.0 / max_per_second
        self._last = 0.0
        self._lock = threading.Lock()

    def wait(self):
        with self._lock:
            now = time.monotonic()
            wait_time = self._last + self._interval - now
            if wait_time > 0:
                time.sleep(wait_time)
            self._last = time.monotonic()


# ---------------------------------------------------------------------------
# Stdlib HTML parser (fallback when BeautifulSoup not available)
# ---------------------------------------------------------------------------

class _StdlibHTMLTextExtractor(HTMLParser):
    """Extracts visible text from HTML using only the standard library."""

    _SKIP_TAGS = frozenset({"script", "style", "noscript", "svg", "head", "iframe"})

    def __init__(self):
        super().__init__()
        self._pieces: list[str] = []
        self._skip_depth = 0

    def handle_starttag(self, tag, attrs):
        if tag.lower() in self._SKIP_TAGS:
            self._skip_depth += 1

    def handle_endtag(self, tag):
        if tag.lower() in self._SKIP_TAGS and self._skip_depth > 0:
            self._skip_depth -= 1

    def handle_data(self, data):
        if self._skip_depth == 0:
            text = data.strip()
            if text:
                self._pieces.append(text)

    def get_text(self) -> str:
        return "\n".join(self._pieces)


class _StdlibLinkExtractor(HTMLParser):
    """Extracts all <a href=...> links."""

    def __init__(self):
        super().__init__()
        self.links: list[str] = []

    def handle_starttag(self, tag, attrs):
        if tag.lower() == "a":
            for name, value in attrs:
                if name == "href" and value:
                    self.links.append(value)


class _StdlibMetaExtractor(HTMLParser):
    """Extracts <title> and <meta> tags."""

    def __init__(self):
        super().__init__()
        self.title = ""
        self.meta: dict[str, str] = {}
        self._in_title = False

    def handle_starttag(self, tag, attrs):
        tag = tag.lower()
        if tag == "title":
            self._in_title = True
        elif tag == "meta":
            attr_dict = dict(attrs)
            name = attr_dict.get("name", attr_dict.get("property", "")).lower()
            content = attr_dict.get("content", "")
            if name and content:
                self.meta[name] = content

    def handle_endtag(self, tag):
        if tag.lower() == "title":
            self._in_title = False

    def handle_data(self, data):
        if self._in_title:
            self.title += data


class _StdlibMainContentExtractor(HTMLParser):
    """Best-effort extraction of main content (article/main tags, or largest text block)."""

    _MAIN_TAGS = frozenset({"article", "main", "section"})
    _SKIP_TAGS = frozenset({"script", "style", "noscript", "nav", "footer",
                            "header", "aside", "svg", "iframe", "head"})

    def __init__(self):
        super().__init__()
        self._pieces: list[str] = []
        self._main_pieces: list[str] = []
        self._in_main = 0
        self._skip_depth = 0

    def handle_starttag(self, tag, attrs):
        tag = tag.lower()
        if tag in self._SKIP_TAGS:
            self._skip_depth += 1
        if tag in self._MAIN_TAGS:
            self._in_main += 1

    def handle_endtag(self, tag):
        tag = tag.lower()
        if tag in self._SKIP_TAGS and self._skip_depth > 0:
            self._skip_depth -= 1
        if tag in self._MAIN_TAGS and self._in_main > 0:
            self._in_main -= 1

    def handle_data(self, data):
        if self._skip_depth > 0:
            return
        text = data.strip()
        if not text:
            return
        self._pieces.append(text)
        if self._in_main > 0:
            self._main_pieces.append(text)

    def get_main_content(self) -> str:
        # Prefer text inside <article>/<main>/<section>; fall back to all visible text
        if self._main_pieces:
            return "\n".join(self._main_pieces)
        return "\n".join(self._pieces)


# ---------------------------------------------------------------------------
# ResearchCache
# ---------------------------------------------------------------------------

class ResearchCache:
    """JSON-file cache for research results with TTL."""

    def __init__(self, cache_path: str = None):
        self._path = Path(cache_path) if cache_path else CACHE_PATH
        self._lock = threading.Lock()
        self._data: dict = {}
        self._load()

    # -- persistence --

    def _load(self):
        try:
            if self._path.exists():
                with open(self._path, "r", encoding="utf-8") as f:
                    self._data = json.load(f)
        except Exception as exc:
            logger.warning("Cache load failed, starting fresh: %s", exc)
            self._data = {}

    def _save(self):
        try:
            with open(self._path, "w", encoding="utf-8") as f:
                json.dump(self._data, f, indent=2, default=str)
        except Exception as exc:
            logger.warning("Cache save failed: %s", exc)

    # -- public API --

    @staticmethod
    def _key(query: str) -> str:
        return hashlib.sha256(query.strip().lower().encode()).hexdigest()[:32]

    def get_cached(self, query: str) -> Optional[ResearchResult]:
        with self._lock:
            key = self._key(query)
            entry = self._data.get(key)
            if not entry:
                return None
            # Check TTL
            stored = datetime.fromisoformat(entry["timestamp"])
            ttl = entry.get("ttl", TTL_GENERAL)
            if (datetime.now() - stored).total_seconds() > ttl:
                del self._data[key]
                self._save()
                return None
            return ResearchResult.from_dict(entry["result"])

    def cache_result(self, query: str, result: ResearchResult,
                     ttl: int = TTL_GENERAL):
        with self._lock:
            key = self._key(query)
            self._data[key] = {
                "result": result.to_dict(),
                "timestamp": datetime.now().isoformat(),
                "ttl": ttl,
            }
            self._save()

    def clear_expired(self):
        """Remove all expired entries."""
        with self._lock:
            now = datetime.now()
            expired = []
            for key, entry in self._data.items():
                stored = datetime.fromisoformat(entry["timestamp"])
                ttl = entry.get("ttl", TTL_GENERAL)
                if (now - stored).total_seconds() > ttl:
                    expired.append(key)
            for key in expired:
                del self._data[key]
            if expired:
                self._save()
            return len(expired)


# ---------------------------------------------------------------------------
# KnowledgeExtractor — pattern-based triple extraction
# ---------------------------------------------------------------------------

class KnowledgeExtractor:
    """Extract (subject, predicate, object) triples from text via regex patterns."""

    # Each pattern: (compiled regex, predicate, subject_group, object_group)
    _PATTERNS = [
        # "X is a Y" / "X is an Y"
        (re.compile(r"([A-Z][\w\s]{1,40}?)\s+is\s+(?:a|an)\s+(.{3,60}?)[.\n]", re.I),
         "is_a", 1, 2),
        # "X was founded in Y"
        (re.compile(r"([A-Z][\w\s]{1,40}?)\s+was\s+founded\s+in\s+(.{3,40}?)[.\n,]", re.I),
         "founded", 1, 2),
        # "X uses Y"
        (re.compile(r"([A-Z][\w\s]{1,40}?)\s+uses?\s+(.{3,60}?)[.\n,]", re.I),
         "uses", 1, 2),
        # "X is located in Y"
        (re.compile(r"([A-Z][\w\s]{1,40}?)\s+is\s+located\s+in\s+(.{3,60}?)[.\n,]", re.I),
         "location", 1, 2),
        # "X has N employees"
        (re.compile(r"([A-Z][\w\s]{1,40}?)\s+has\s+([\d,]+)\s+employees", re.I),
         "employees", 1, 2),
        # "X costs $Y"
        (re.compile(r"([A-Z][\w\s]{1,40}?)\s+costs?\s+\$?([\d,.]+\s*\w*)", re.I),
         "price", 1, 2),
        # "X released version Y"
        (re.compile(r"([A-Z][\w\s]{1,40}?)\s+released?\s+version\s+([\w.]+)", re.I),
         "version", 1, 2),
        # "X vulnerability affects Y"
        (re.compile(r"(\S+\s+vulnerability)\s+affects?\s+(.{3,60}?)[.\n,]", re.I),
         "affects", 1, 2),
        # CVE affects product
        (re.compile(r"(CVE-\d{4}-\d{4,})\s+(?:affects?|impacts?)\s+(.{3,60}?)[.\n,]", re.I),
         "affects", 1, 2),
        # CVE severity
        (re.compile(r"(CVE-\d{4}-\d{4,}).*?(?:severity|score|CVSS)[:\s]+([\d.]+)", re.I),
         "severity", 1, 2),
        # "X is based on Y"
        (re.compile(r"([A-Z][\w\s]{1,40}?)\s+is\s+based\s+on\s+(.{3,60}?)[.\n,]", re.I),
         "based_on", 1, 2),
        # "X was created by Y"
        (re.compile(r"([A-Z][\w\s]{1,40}?)\s+was\s+created\s+by\s+(.{3,60}?)[.\n,]", re.I),
         "created_by", 1, 2),
        # "X runs on Y"
        (re.compile(r"([A-Z][\w\s]{1,40}?)\s+runs?\s+on\s+(.{3,60}?)[.\n,]", re.I),
         "runs_on", 1, 2),
    ]

    def extract_facts(self, text: str, topic: str = "") -> list[tuple]:
        """
        Extract (subject, predicate, object) triples from text.

        Returns list of 3-tuples.
        """
        if not text:
            return []

        facts: list[tuple] = []
        seen = set()

        for regex, predicate, subj_g, obj_g in self._PATTERNS:
            for match in regex.finditer(text):
                subj = match.group(subj_g).strip()
                obj_val = match.group(obj_g).strip()
                # Basic quality filter
                if len(subj) < 2 or len(obj_val) < 2:
                    continue
                if len(subj) > 80 or len(obj_val) > 120:
                    continue
                key = (subj.lower(), predicate, obj_val.lower())
                if key not in seen:
                    seen.add(key)
                    facts.append((subj, predicate, obj_val))

        # Also try to extract standalone CVE references
        for m in re.finditer(r"(CVE-\d{4}-\d{4,})", text):
            cve_id = m.group(1)
            key = (cve_id.lower(), "mentioned_in", topic.lower())
            if topic and key not in seen:
                seen.add(key)
                facts.append((cve_id, "mentioned_in", topic))

        return facts


# ---------------------------------------------------------------------------
# WebResearcher — main class
# ---------------------------------------------------------------------------

class WebResearcher:
    """
    JARVIS Web Research Engine.

    Fetches, parses, extracts knowledge from the internet and integrates it
    with JARVIS's knowledge graph.

    NOTE: This does NOT respect robots.txt by default. If you want to add
    robots.txt checking, see urllib.robotparser.
    """

    def __init__(self, jarvis=None):
        self._jarvis = jarvis
        self._kg = None  # knowledge graph — resolved lazily
        self._cache = ResearchCache()
        self._extractor = KnowledgeExtractor()
        self._rate = _RateLimiter()
        self._lock = threading.Lock()

        # Build an SSL context that works even when certs are outdated
        self._ssl_ctx = ssl.create_default_context()
        try:
            self._ssl_ctx.check_hostname = True
            self._ssl_ctx.verify_mode = ssl.CERT_REQUIRED
        except Exception:
            # If cert verification fails in some envs, allow unverified
            self._ssl_ctx = ssl._create_unverified_context()

        logger.info("WebResearcher online (requests=%s, bs4=%s)",
                     _HAS_REQUESTS, _HAS_BS4)

    # -- knowledge graph access --

    @property
    def kg(self):
        """Lazily resolve knowledge graph reference."""
        if self._kg is not None:
            return self._kg
        # Try to get it from JARVIS
        if self._jarvis:
            for attr in ("knowledge_graph", "kg", "knowledge"):
                kg = getattr(self._jarvis, attr, None)
                if kg is not None:
                    self._kg = kg
                    return self._kg
        return None

    # ======================================================================
    # HTTP fetching (requests preferred, urllib fallback)
    # ======================================================================

    def _http_get(self, url: str, timeout: int = REQUEST_TIMEOUT,
                  headers: dict = None) -> str:
        """Fetch a URL and return the response body as text."""
        self._rate.wait()
        hdrs = {"User-Agent": USER_AGENT}
        if headers:
            hdrs.update(headers)

        if _HAS_REQUESTS:
            try:
                resp = _requests.get(url, headers=hdrs, timeout=timeout,
                                     allow_redirects=True)
                resp.raise_for_status()
                return resp.text[:MAX_CONTENT_LENGTH]
            except Exception as exc:
                logger.debug("requests failed for %s: %s — trying urllib", url, exc)

        # Fallback: urllib
        req = urllib.request.Request(url, headers=hdrs)
        try:
            with urllib.request.urlopen(req, timeout=timeout,
                                        context=self._ssl_ctx) as resp:
                charset = resp.headers.get_content_charset() or "utf-8"
                data = resp.read(MAX_CONTENT_LENGTH)
                return data.decode(charset, errors="replace")
        except Exception as exc:
            logger.warning("HTTP GET failed for %s: %s", url, exc)
            raise

    def _http_get_json(self, url: str, timeout: int = REQUEST_TIMEOUT,
                       headers: dict = None) -> dict:
        """Fetch a URL and parse JSON response."""
        text = self._http_get(url, timeout=timeout, headers=headers)
        return json.loads(text)

    # ======================================================================
    # HTML parsing
    # ======================================================================

    def _clean_html(self, html: str) -> str:
        """Strip all HTML tags, scripts, styles — return clean text."""
        if _HAS_BS4:
            soup = _BeautifulSoup(html, "html.parser")
            for tag in soup(["script", "style", "noscript", "svg", "iframe"]):
                tag.decompose()
            return soup.get_text(separator="\n", strip=True)

        parser = _StdlibHTMLTextExtractor()
        try:
            parser.feed(html)
        except Exception:
            pass
        return parser.get_text()

    def _extract_links(self, html: str, base_url: str) -> list[str]:
        """Extract all absolute URLs from HTML."""
        if _HAS_BS4:
            soup = _BeautifulSoup(html, "html.parser")
            links = []
            for a in soup.find_all("a", href=True):
                href = a["href"]
                links.append(urljoin(base_url, href))
            return links

        parser = _StdlibLinkExtractor()
        try:
            parser.feed(html)
        except Exception:
            pass
        return [urljoin(base_url, href) for href in parser.links]

    def _extract_metadata(self, html: str) -> dict:
        """Extract title, description, keywords, author from HTML."""
        if _HAS_BS4:
            soup = _BeautifulSoup(html, "html.parser")
            title = soup.title.string.strip() if soup.title and soup.title.string else ""
            meta = {}
            for tag in soup.find_all("meta"):
                name = (tag.get("name") or tag.get("property") or "").lower()
                content = tag.get("content", "")
                if name and content:
                    meta[name] = content
            return {
                "title": title,
                "description": meta.get("description", meta.get("og:description", "")),
                "keywords": meta.get("keywords", ""),
                "author": meta.get("author", ""),
            }

        parser = _StdlibMetaExtractor()
        try:
            parser.feed(html)
        except Exception:
            pass
        return {
            "title": parser.title.strip(),
            "description": parser.meta.get("description",
                           parser.meta.get("og:description", "")),
            "keywords": parser.meta.get("keywords", ""),
            "author": parser.meta.get("author", ""),
        }

    def _extract_main_content(self, html: str) -> str:
        """Extract just the main article/content, excluding nav/footer/ads."""
        if _HAS_BS4:
            soup = _BeautifulSoup(html, "html.parser")
            # Remove unwanted elements
            for tag in soup(["script", "style", "noscript", "nav", "footer",
                             "header", "aside", "svg", "iframe"]):
                tag.decompose()
            # Try article or main tag first
            main = soup.find("article") or soup.find("main")
            if main:
                return main.get_text(separator="\n", strip=True)
            # Fall back to body
            body = soup.find("body")
            if body:
                return body.get_text(separator="\n", strip=True)
            return soup.get_text(separator="\n", strip=True)

        parser = _StdlibMainContentExtractor()
        try:
            parser.feed(html)
        except Exception:
            pass
        return parser.get_main_content()

    # ======================================================================
    # Public fetching / parsing API
    # ======================================================================

    def fetch_url(self, url: str) -> str:
        """Fetch a URL and return clean text content (HTML stripped)."""
        try:
            html = self._http_get(url)
            return self._clean_html(html)
        except Exception as exc:
            logger.error("fetch_url failed for %s: %s", url, exc)
            return ""

    def fetch_and_parse(self, url: str) -> dict:
        """
        Fetch URL and extract structured data.

        Returns dict with: url, title, text, links, metadata, fetched_at
        """
        try:
            html = self._http_get(url)
        except Exception as exc:
            logger.error("fetch_and_parse failed for %s: %s", url, exc)
            return {"url": url, "title": "", "text": "", "links": [],
                    "metadata": {}, "error": str(exc), "fetched_at": datetime.now().isoformat()}

        return {
            "url": url,
            "title": self._extract_metadata(html).get("title", ""),
            "text": self._extract_main_content(html),
            "links": self._extract_links(html, url),
            "metadata": self._extract_metadata(html),
            "fetched_at": datetime.now().isoformat(),
        }

    def learn_from_url(self, url: str) -> int:
        """
        Fetch a URL, extract knowledge facts, store in knowledge graph.

        Returns number of facts extracted and stored.
        """
        parsed = self.fetch_and_parse(url)
        text = parsed.get("text", "")
        title = parsed.get("title", "") or urlparse(url).hostname or "unknown"

        facts = self._extractor.extract_facts(text, topic=title)
        stored = 0

        if self.kg and facts:
            for subj, pred, obj_val in facts:
                try:
                    self.kg.add_fact(subj, pred, obj_val,
                                     entity_type="web_knowledge",
                                     confidence=0.6,
                                     source=f"web:{url}")
                    stored += 1
                except Exception as exc:
                    logger.debug("Failed to store fact (%s, %s, %s): %s",
                                 subj, pred, obj_val, exc)

        logger.info("Learned %d facts (%d stored) from %s", len(facts), stored, url)
        return stored

    # ======================================================================
    # Web search backends
    # ======================================================================

    def search_web(self, query: str, num_results: int = 5) -> list[dict]:
        """
        Search the web for a query. Returns list of {title, url, snippet}.

        Tries multiple backends with graceful fallback:
        1. DuckDuckGo Instant Answer API
        2. Wikipedia API
        3. Google Custom Search (if configured)
        """
        results = []

        # 1) DuckDuckGo
        try:
            ddg = self._search_duckduckgo(query)
            results.extend(ddg)
        except Exception as exc:
            logger.debug("DuckDuckGo search failed: %s", exc)

        # 2) Wikipedia
        try:
            wiki = self._search_wikipedia(query)
            if wiki:
                results.append(wiki)
        except Exception as exc:
            logger.debug("Wikipedia search failed: %s", exc)

        # 3) Google Custom Search (optional)
        try:
            google = self._search_google(query, num_results)
            results.extend(google)
        except Exception as exc:
            logger.debug("Google CSE search skipped/failed: %s", exc)

        # Deduplicate by URL
        seen_urls = set()
        unique = []
        for r in results:
            if r.get("url") and r["url"] not in seen_urls:
                seen_urls.add(r["url"])
                unique.append(r)

        return unique[:num_results]

    def _search_duckduckgo(self, query: str) -> list[dict]:
        """Search DuckDuckGo Instant Answer API (free, no key)."""
        url = "https://api.duckduckgo.com/?" + urlencode({
            "q": query, "format": "json", "no_html": "1", "skip_disambig": "1"
        })
        data = self._http_get_json(url)
        results = []

        # Abstract (main answer)
        if data.get("AbstractText"):
            results.append({
                "title": data.get("Heading", query),
                "url": data.get("AbstractURL", ""),
                "snippet": data["AbstractText"][:500],
                "source": "duckduckgo",
            })

        # Related topics
        for topic in data.get("RelatedTopics", [])[:5]:
            if isinstance(topic, dict) and topic.get("FirstURL"):
                results.append({
                    "title": topic.get("Text", "")[:100],
                    "url": topic["FirstURL"],
                    "snippet": topic.get("Text", "")[:300],
                    "source": "duckduckgo",
                })

        return results

    def _search_wikipedia(self, query: str) -> Optional[dict]:
        """Search Wikipedia REST API for a topic summary."""
        topic = quote(query.replace(" ", "_"), safe="")
        url = f"https://en.wikipedia.org/api/rest_v1/page/summary/{topic}"
        try:
            data = self._http_get_json(url)
            if data.get("extract"):
                return {
                    "title": data.get("title", query),
                    "url": data.get("content_urls", {}).get("desktop", {}).get("page", ""),
                    "snippet": data["extract"][:500],
                    "source": "wikipedia",
                }
        except Exception:
            pass
        return None

    def _search_google(self, query: str, num_results: int = 5) -> list[dict]:
        """Search Google Custom Search Engine (requires API key + CX)."""
        # Check for config
        api_key = os.environ.get("GOOGLE_CSE_API_KEY", "")
        cx = os.environ.get("GOOGLE_CSE_CX", "")
        if not api_key or not cx:
            return []

        url = "https://www.googleapis.com/customsearch/v1?" + urlencode({
            "key": api_key, "cx": cx, "q": query, "num": min(num_results, 10)
        })
        data = self._http_get_json(url)
        results = []
        for item in data.get("items", []):
            results.append({
                "title": item.get("title", ""),
                "url": item.get("link", ""),
                "snippet": item.get("snippet", ""),
                "source": "google",
            })
        return results

    # ======================================================================
    # References / cache lookup
    # ======================================================================

    def get_references(self, topic: str) -> list[dict]:
        """Return known references/sources for a topic from cache and knowledge graph."""
        refs = []

        # Check cache
        cached = self._cache.get_cached(topic)
        if cached:
            for src in cached.sources:
                refs.append(src)

        # Check knowledge graph
        if self.kg:
            try:
                info = self.kg.query_everything(topic)
                if info and info.get("facts"):
                    for fact in info["facts"]:
                        source = fact.get("source", "")
                        if source.startswith("web:"):
                            refs.append({
                                "url": source[4:],
                                "title": topic,
                                "snippet": f"{fact.get('predicate', '')}: {fact.get('value', '')}",
                            })
            except Exception:
                pass

        return refs

    # ======================================================================
    # Fact verification
    # ======================================================================

    def verify_fact(self, claim: str) -> dict:
        """
        Try to verify a factual claim by searching for it online.

        Returns dict with: claim, verified (bool), confidence, sources, explanation
        """
        results = self.search_web(claim, num_results=3)
        if not results:
            return {
                "claim": claim,
                "verified": False,
                "confidence": 0.0,
                "sources": [],
                "explanation": "Could not find any sources to verify this claim.",
            }

        supporting = 0
        source_info = []
        all_text = ""

        for result in results[:3]:
            snippet = result.get("snippet", "").lower()
            claim_words = set(claim.lower().split())
            snippet_words = set(snippet.split())
            overlap = len(claim_words & snippet_words) / max(len(claim_words), 1)

            if overlap > 0.3:
                supporting += 1

            source_info.append(result)
            all_text += " " + snippet

        total = len(results[:3])
        confidence = supporting / total if total > 0 else 0.0
        verified = confidence >= 0.5

        return {
            "claim": claim,
            "verified": verified,
            "confidence": round(confidence, 2),
            "sources": source_info,
            "explanation": (
                f"Found {supporting}/{total} sources supporting this claim."
                if total > 0 else "No sources found."
            ),
        }

    # ======================================================================
    # Main research entry point
    # ======================================================================

    def research(self, query: str, depth: str = "quick") -> ResearchResult:
        """
        Research a topic.

        Args:
            query: What to research
            depth: "quick" (1-2 sources) or "deep" (3-5 sources, comprehensive)

        Returns:
            ResearchResult with summary, facts, sources, references
        """
        # Check cache first
        cached = self._cache.get_cached(query)
        if cached:
            logger.info("Research cache hit for: %s", query)
            return cached

        max_sources = 2 if depth == "quick" else 5
        result = ResearchResult(query=query)

        # Search for sources
        search_results = self.search_web(query, num_results=max_sources + 2)

        if not search_results:
            result.summary = f"No results found for: {query}"
            result.confidence = 0.0
            return result

        # Fetch and analyze top sources
        all_text_parts = []
        all_facts = []

        for sr in search_results[:max_sources]:
            url = sr.get("url", "")
            if not url:
                continue

            result.sources.append({
                "url": url,
                "title": sr.get("title", ""),
                "snippet": sr.get("snippet", ""),
                "relevance": 1.0,
            })
            result.references.append(url)

            # For deep research, actually fetch and parse each page
            if depth == "deep" and url:
                try:
                    page = self.fetch_and_parse(url)
                    page_text = page.get("text", "")
                    if page_text:
                        all_text_parts.append(page_text[:5000])
                        facts = self._extractor.extract_facts(page_text, topic=query)
                        all_facts.extend(facts)
                except Exception as exc:
                    logger.debug("Failed to fetch %s: %s", url, exc)
            else:
                # Quick mode — use snippets
                snippet = sr.get("snippet", "")
                if snippet:
                    all_text_parts.append(snippet)
                    facts = self._extractor.extract_facts(snippet, topic=query)
                    all_facts.extend(facts)

        # Build summary from snippets / content
        combined = "\n\n".join(all_text_parts)
        result.summary = self._synthesize_summary(query, combined, search_results)

        # Deduplicate facts
        seen_facts = set()
        for subj, pred, obj_val in all_facts:
            key = (subj.lower(), pred, obj_val.lower())
            if key not in seen_facts:
                seen_facts.add(key)
                result.facts_extracted.append(f"{subj} {pred} {obj_val}")

        # Store facts in knowledge graph
        stored = 0
        if self.kg:
            for subj, pred, obj_val in all_facts:
                try:
                    self.kg.add_fact(subj, pred, obj_val,
                                     entity_type="web_research",
                                     confidence=0.6,
                                     source=f"research:{query}")
                    stored += 1
                except Exception:
                    pass
        result.knowledge_stored = stored

        # Confidence based on number of sources and facts
        src_score = min(len(result.sources) / max_sources, 1.0)
        fact_score = min(len(result.facts_extracted) / 5, 1.0) if depth == "deep" else 0.5
        result.confidence = round(0.6 * src_score + 0.4 * fact_score, 2)

        # Cache it
        ttl = TTL_NEWS if any(w in query.lower() for w in ("news", "today", "latest", "2026", "2025")) else TTL_GENERAL
        self._cache.cache_result(query, result, ttl=ttl)

        logger.info("Research complete: '%s' — %d sources, %d facts, confidence=%.2f",
                     query, len(result.sources), len(result.facts_extracted),
                     result.confidence)

        return result

    def _synthesize_summary(self, query: str, text: str,
                            search_results: list[dict]) -> str:
        """Build a summary from gathered text. Simple extraction-based approach."""
        if not text and not search_results:
            return f"No information found for: {query}"

        parts = []

        # Lead with the best snippet
        for sr in search_results[:2]:
            snippet = sr.get("snippet", "").strip()
            if snippet and len(snippet) > 20:
                parts.append(snippet)

        if not parts and text:
            # Take the first meaningful chunk of text
            sentences = re.split(r'(?<=[.!?])\s+', text[:2000])
            parts = [s.strip() for s in sentences[:5] if len(s.strip()) > 20]

        if not parts:
            return f"Found sources for '{query}' but could not extract a clear summary."

        summary = " ".join(parts)
        # Truncate to reasonable length
        if len(summary) > 1500:
            summary = summary[:1497] + "..."

        return summary

    # ======================================================================
    # Security-specific research
    # ======================================================================

    def research_cve(self, cve_id: str) -> dict:
        """
        Fetch CVE details from NIST NVD API.

        Returns dict with: cve_id, description, severity, cvss_score, affected,
                           references, published, modified
        """
        cve_id = cve_id.upper().strip()
        if not re.match(r"CVE-\d{4}-\d{4,}", cve_id):
            return {"error": f"Invalid CVE ID format: {cve_id}"}

        result = {
            "cve_id": cve_id,
            "description": "",
            "severity": "",
            "cvss_score": None,
            "affected": [],
            "references": [],
            "published": "",
            "modified": "",
        }

        # NVD API 2.0
        try:
            url = f"https://services.nvd.nist.gov/rest/json/cves/2.0?cveId={cve_id}"
            data = self._http_get_json(url, timeout=15)

            vulns = data.get("vulnerabilities", [])
            if vulns:
                cve_data = vulns[0].get("cve", {})

                # Description
                for desc in cve_data.get("descriptions", []):
                    if desc.get("lang") == "en":
                        result["description"] = desc.get("value", "")
                        break

                # CVSS score
                metrics = cve_data.get("metrics", {})
                for version_key in ("cvssMetricV31", "cvssMetricV30", "cvssMetricV2"):
                    metric_list = metrics.get(version_key, [])
                    if metric_list:
                        cvss = metric_list[0].get("cvssData", {})
                        result["cvss_score"] = cvss.get("baseScore")
                        result["severity"] = cvss.get("baseSeverity",
                                             metric_list[0].get("baseSeverity", ""))
                        break

                # References
                for ref in cve_data.get("references", []):
                    result["references"].append(ref.get("url", ""))

                # Dates
                result["published"] = cve_data.get("published", "")
                result["modified"] = cve_data.get("lastModified", "")

                # Affected products (from configurations)
                for config in cve_data.get("configurations", []):
                    for node in config.get("nodes", []):
                        for cpe_match in node.get("cpeMatch", []):
                            criteria = cpe_match.get("criteria", "")
                            if criteria:
                                result["affected"].append(criteria)

        except Exception as exc:
            logger.warning("NVD API fetch failed for %s: %s", cve_id, exc)
            result["error"] = str(exc)

        # Store in knowledge graph
        if self.kg and result.get("description"):
            try:
                self.kg.add_entity(cve_id, "vulnerability", {
                    "description": result["description"][:500],
                    "severity": result.get("severity", ""),
                    "cvss_score": str(result.get("cvss_score", "")),
                })
                for affected in result.get("affected", [])[:10]:
                    self.kg.add_relationship(cve_id, "affects", affected) if hasattr(self.kg, "add_relationship") else None
            except Exception:
                pass

        return result

    def research_technology(self, tech_name: str) -> dict:
        """
        Research a technology — known vulnerabilities, latest version, security advisories.

        Returns dict with: name, description, latest_version, vulnerabilities, advisories
        """
        result = {
            "name": tech_name,
            "description": "",
            "latest_version": "",
            "vulnerabilities": [],
            "advisories": [],
            "sources": [],
        }

        # Wikipedia for description
        try:
            wiki = self._search_wikipedia(tech_name)
            if wiki:
                result["description"] = wiki.get("snippet", "")
                result["sources"].append(wiki.get("url", ""))
        except Exception:
            pass

        # DuckDuckGo for general info
        try:
            ddg = self._search_duckduckgo(f"{tech_name} latest version")
            for r in ddg[:2]:
                result["sources"].append(r.get("url", ""))
                # Try to extract version from snippet
                snippet = r.get("snippet", "")
                version_match = re.search(
                    rf"{re.escape(tech_name)}\s+(\d+[\w.]*)",
                    snippet, re.IGNORECASE
                )
                if version_match and not result["latest_version"]:
                    result["latest_version"] = version_match.group(1)
        except Exception:
            pass

        # NVD search for vulnerabilities (keyword search)
        try:
            url = ("https://services.nvd.nist.gov/rest/json/cves/2.0?"
                   + urlencode({"keywordSearch": tech_name, "resultsPerPage": "5"}))
            data = self._http_get_json(url, timeout=15)
            for vuln in data.get("vulnerabilities", [])[:5]:
                cve = vuln.get("cve", {})
                cve_id = cve.get("id", "")
                desc = ""
                for d in cve.get("descriptions", []):
                    if d.get("lang") == "en":
                        desc = d.get("value", "")[:200]
                        break
                if cve_id:
                    result["vulnerabilities"].append({
                        "cve_id": cve_id,
                        "description": desc,
                    })
        except Exception as exc:
            logger.debug("NVD keyword search failed for %s: %s", tech_name, exc)

        # Store in knowledge graph
        if self.kg:
            try:
                facts = {"type": "technology"}
                if result["description"]:
                    facts["description"] = result["description"][:500]
                if result["latest_version"]:
                    facts["latest_version"] = result["latest_version"]
                self.kg.add_entity(tech_name, "technology", facts)
            except Exception:
                pass

        return result

    def research_target(self, domain: str) -> dict:
        """
        OSINT research on a target domain — WHOIS, DNS, certificate transparency, public info.

        Returns dict with: domain, certificates, subdomains, technologies, public_info
        """
        domain = domain.strip().lower()
        result = {
            "domain": domain,
            "certificates": [],
            "subdomains": [],
            "technologies": [],
            "public_info": "",
            "sources": [],
        }

        # crt.sh — certificate transparency logs
        try:
            url = f"https://crt.sh/?q={quote(domain)}&output=json"
            certs = self._http_get_json(url, timeout=15)
            seen_names = set()
            for cert in certs[:50]:
                name_value = cert.get("name_value", "")
                issuer = cert.get("issuer_name", "")
                not_after = cert.get("not_after", "")
                result["certificates"].append({
                    "common_name": name_value,
                    "issuer": issuer,
                    "expiry": not_after,
                })
                # Extract subdomains
                for name in name_value.split("\n"):
                    name = name.strip().lower()
                    if name and name not in seen_names and domain in name:
                        seen_names.add(name)
                        result["subdomains"].append(name)
            result["sources"].append(f"https://crt.sh/?q={domain}")
        except Exception as exc:
            logger.debug("crt.sh lookup failed for %s: %s", domain, exc)

        # Deduplicate subdomains
        result["subdomains"] = sorted(set(result["subdomains"]))

        # DuckDuckGo for public info
        try:
            search = self._search_duckduckgo(f"{domain} company")
            for r in search[:2]:
                if r.get("snippet"):
                    result["public_info"] += r["snippet"] + " "
                    result["sources"].append(r.get("url", ""))
        except Exception:
            pass

        result["public_info"] = result["public_info"].strip()[:1000]

        # Store in knowledge graph
        if self.kg:
            try:
                facts = {"type": "target"}
                if result["public_info"]:
                    facts["description"] = result["public_info"][:500]
                if result["subdomains"]:
                    facts["subdomains"] = ", ".join(result["subdomains"][:20])
                self.kg.add_entity(domain, "target", facts)

                for sub in result["subdomains"][:20]:
                    try:
                        self.kg.add_relationship(domain, "has_subdomain", sub)
                    except Exception:
                        pass
            except Exception:
                pass

        return result

    # ======================================================================
    # Utility
    # ======================================================================

    def clear_cache(self) -> int:
        """Clear expired cache entries. Returns number removed."""
        return self._cache.clear_expired()

    def cache_stats(self) -> dict:
        """Return cache statistics."""
        with self._cache._lock:
            total = len(self._cache._data)
        return {"total_entries": total, "cache_path": str(self._cache._path)}


# ---------------------------------------------------------------------------
# Convenience — module-level singleton
# ---------------------------------------------------------------------------

_default_researcher: Optional[WebResearcher] = None
_singleton_lock = threading.Lock()


def get_researcher(jarvis=None) -> WebResearcher:
    """Get or create the default WebResearcher singleton."""
    global _default_researcher
    with _singleton_lock:
        if _default_researcher is None:
            _default_researcher = WebResearcher(jarvis=jarvis)
        return _default_researcher


# ---------------------------------------------------------------------------
# Quick test
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG,
                        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s")

    researcher = WebResearcher()

    print("=== Quick research ===")
    r = researcher.research("Python programming language", depth="quick")
    print(f"Summary: {r.summary[:200]}")
    print(f"Sources: {len(r.sources)}")
    print(f"Facts: {r.facts_extracted[:5]}")
    print(f"Confidence: {r.confidence}")

    print("\n=== Wikipedia fetch ===")
    text = researcher.fetch_url("https://en.wikipedia.org/wiki/Python_(programming_language)")
    print(f"Fetched {len(text)} chars")

    print("\n=== CVE research ===")
    cve = researcher.research_cve("CVE-2021-44228")
    print(f"CVE: {cve.get('cve_id')} — {cve.get('severity')} ({cve.get('cvss_score')})")
    print(f"Description: {cve.get('description', '')[:150]}")
