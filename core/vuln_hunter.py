"""
J.A.R.V.I.S — Vulnerability Hunter (local, scope-gated, AUTHORISED testing only)

Extends the recon pipeline from "runs scanners" to "finds confirmable bugs and
hands you a ranked manual-hunting hit-list." This is the piece that actually
targets mid/high-value bugs — honestly split into what a machine can confirm and
what only a human can:

  1. AUTOMATED FINDINGS — bug classes automation confirms on its own:
        · exposed sensitive files (.git/.env/backups)   → info disclosure
        · CORS misconfiguration (reflected origin + creds)
        · subdomain takeover (dangling CNAME fingerprints)
        · open redirects (param-based)
     Each comes with a CVSS 3.1 score + CWE, ready to drop into a report.

  2. MANUAL HIT-LIST — the mid/high money (IDOR, broken access control, business
     logic, SSRF) that needs human judgement. We CANNOT confirm these, but we
     classify every discovered endpoint/param into buckets so you know exactly
     which requests to test by hand, and with what technique.

Pure-Python where it can be, so it runs with no extra tool installs:
  · historical URLs via the Wayback Machine CDX API
  · JS endpoint + secret extraction (regex over fetched scripts)
  · active checks over plain HTTP (requests)
subfinder / httpx (from core.recon_pipeline) widen the host surface when present.

━━━ HARD SAFETY RULES (enforced in code, do not weaken) ━━━━━━━━━━━━━━━━━━━━━━━━
  1. Every host AND every URL is re-checked IN-SCOPE (core.bug_bounty) before a
     single request leaves the machine. Off-scope → dropped, never touched.
  2. A global request budget + politeness delay keep this within program rate
     limits. It probes; it does not flood.
  3. Checks are read-oriented and benign (GET, a reflected header, a redirect to
     example.com). No destructive payloads, no exploitation, no data exfil.
Legal ONLY against programs that authorise testing, on in-scope assets.
"""
from __future__ import annotations

import json
import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse, urlencode, parse_qsl, urlunparse

from core.bug_bounty import get_tracker
from core import cvss

HUNT_DIR = Path.home() / ".jarvis" / "bug_bounty" / "hunts"

# Identify honestly. Some programs require a recognisable UA or a custom header;
# set BUG_BOUNTY_UA / researcher handle in your program notes and edit here.
UA = "JARVIS-BugBountyRecon/1.0 (authorised security testing)"

# Conservative limits — stay a polite guest inside the program's rate policy.
MAX_REQUESTS = 500          # global budget for one hunt
MAX_HOSTS = 40              # cap live hosts we actively probe
MAX_JS = 40                 # cap JS files we fetch + parse
MAX_URLS_CLASSIFY = 4000    # cap wayback URLs we classify
CONCURRENCY = 8
REQ_TIMEOUT = 10

# ─── Sensitive files worth probing (path → what a hit means) ─────────────────
SENSITIVE_PATHS = {
    "/.git/config":        ("git repo exposed", "[core]"),
    "/.git/HEAD":          ("git repo exposed", "ref:"),
    "/.env":               (".env secrets exposed", "="),
    "/.env.local":         (".env secrets exposed", "="),
    "/.aws/credentials":   ("AWS credentials exposed", "aws_"),
    "/config.json":        ("config file exposed", "{"),
    "/.DS_Store":          ("directory listing leak", "\x00\x00\x00"),
    "/.svn/entries":       ("svn repo exposed", ""),
    "/backup.zip":         ("backup archive exposed", "PK"),
    "/backup.sql":         ("database dump exposed", ""),
    "/.htpasswd":          ("htpasswd exposed", ":"),
    "/server-status":      ("apache server-status exposed", "Apache Server Status"),
    "/phpinfo.php":        ("phpinfo exposed", "PHP Version"),
    "/wp-config.php.bak":  ("wp-config backup exposed", "DB_PASSWORD"),
    "/.env.bak":           (".env backup exposed", "="),
}

# ─── Subdomain-takeover fingerprints (service → response signature) ──────────
# Classic can-i-take-over-xyz signatures; a dangling CNAME + this body = takeover.
TAKEOVER_FINGERPRINTS = {
    "GitHub Pages":   "There isn't a GitHub Pages site here",
    "Heroku":         "No such app",
    "AWS S3":         "NoSuchBucket",
    "Shopify":        "Sorry, this shop is currently unavailable",
    "Fastly":         "Fastly error: unknown domain",
    "Ghost":          "The thing you were looking for is no longer here",
    "Surge.sh":       "project not found",
    "Bitbucket":      "Repository not found",
    "Unbounce":       "The requested URL was not found on this server",
    "Tumblr":         "Whatever you were looking for doesn't currently exist",
    "Wordpress":      "Do you want to register",
    "Zendesk":        "Help Center Closed",
    "Readme.io":      "Project doesnt exist... yet!",
}

# ─── Manual hit-list classification (param/path signal → bug class + how) ────
IDOR_PARAMS = {"id", "user_id", "userid", "uid", "account", "account_id", "acct",
               "order", "order_id", "invoice", "doc", "document", "file", "file_id",
               "uuid", "gid", "pid", "cid", "record", "profile", "customer"}
SSRF_PARAMS = {"url", "uri", "u", "link", "dest", "destination", "redirect", "domain",
               "callback", "webhook", "target", "fetch", "site", "html", "path",
               "continue", "data", "reference", "return", "returnto", "image", "img"}
REDIRECT_PARAMS = {"redirect", "url", "next", "dest", "destination", "return",
                   "returnurl", "return_url", "continue", "r", "u", "goto", "out",
                   "target", "redirect_uri", "redirect_url", "callback"}
AUTH_HINTS = ("login", "logout", "signin", "register", "signup", "reset", "forgot",
              "password", "passwd", "token", "oauth", "sso", "saml", "mfa", "otp",
              "verify", "confirm", "session")
ADMIN_HINTS = ("admin", "administrator", "manage", "management", "internal",
               "dashboard", "console", "backend", "staff", "superuser", "root",
               "config", "settings", "debug")
API_HINTS = ("/api/", "/rest/", "/graphql", "/v1/", "/v2/", "/v3/", ".json",
             "/gql", "/query", "/rpc")
UPLOAD_HINTS = ("upload", "import", "attachment", "avatar", "file", "media", "photo")

_ID_SEG = re.compile(r"^\d{2,}$|^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}"
                     r"-[0-9a-f]{4}-[0-9a-f]{12}$", re.I)


def _hint_re(hints) -> "re.Pattern":
    """Boundary-aware matcher: the hint must start at a non-letter (so 'file'
    matches '/file' and '/user-file' but NOT 'profile')."""
    return re.compile(r"(?<![a-z])(" + "|".join(re.escape(h) for h in hints) + r")", re.I)


_AUTH_RE = _hint_re(AUTH_HINTS)
_ADMIN_RE = _hint_re(ADMIN_HINTS)
_UPLOAD_RE = _hint_re(UPLOAD_HINTS)

# JS endpoint + secret regexes.
_JS_ENDPOINT = re.compile(r"""['"`](/[A-Za-z0-9_\-./{}:]{2,120})['"`]""")
_JS_FULLURL = re.compile(r"""['"`](https?://[A-Za-z0-9_\-./?=&{}:%]{6,200})['"`]""")
_SECRET_PATTERNS = {
    "AWS access key":   re.compile(r"AKIA[0-9A-Z]{16}"),
    "Google API key":   re.compile(r"AIza[0-9A-Za-z\-_]{35}"),
    "Slack token":      re.compile(r"xox[baprs]-[0-9A-Za-z\-]{10,48}"),
    "Stripe live key":  re.compile(r"sk_live_[0-9A-Za-z]{24,}"),
    "Generic secret":   re.compile(r"""(?i)(api[_-]?key|secret|passwd|password|token)"""
                                   r"""["'`]?\s*[:=]\s*["'`][0-9A-Za-z\-_.]{12,64}["'`]"""),
    "Private key":      re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
    "JWT":              re.compile(r"eyJ[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{6,}"),
}


@dataclass
class Finding:
    kind: str                      # cvss BUG_TYPES key
    title: str
    url: str
    evidence: str = ""
    severity: str = "info"
    cvss_score: float = 0.0
    cvss_vector: str = ""
    cwe: str = ""
    confidence: str = "firm"       # firm | tentative

    def line(self) -> str:
        sev = self.severity.upper()
        tag = f"CVSS {self.cvss_score} {sev}" if self.cvss_score else sev
        conf = "" if self.confidence == "firm" else " (verify)"
        return f"[{tag}] {self.title}{conf}\n      {self.url}\n      {self.evidence}".rstrip()


class VulnHunter:
    def __init__(self, jarvis=None):
        self.jarvis = jarvis
        self.bounty = get_tracker(jarvis)
        HUNT_DIR.mkdir(parents=True, exist_ok=True)
        self._budget = MAX_REQUESTS
        self._session = None

    # ─── Scope gate (the safety control) ──────────────────────────────────
    def _host_in_scope(self, target_id: str, host: str) -> bool:
        return self.bounty.in_scope(target_id, host) is True

    def _url_in_scope(self, target_id: str, url: str) -> bool:
        host = urlparse(url).hostname or ""
        return self._host_in_scope(target_id, host)

    # ─── Rate-limited HTTP (never raises; respects the global budget) ──────
    def _requests(self):
        import requests
        if self._session is None:
            s = requests.Session()
            s.headers.update({"User-Agent": UA})
            self._session = s
        return self._session

    def _get(self, url: str, allow_redirects: bool = True,
             extra_headers: Optional[dict] = None):
        """One budgeted GET. Returns a response or None. Politeness delay baked in."""
        if self._budget <= 0:
            return None
        self._budget -= 1
        try:
            r = self._requests().get(url, timeout=REQ_TIMEOUT,
                                     allow_redirects=allow_redirects,
                                     headers=extra_headers or {}, verify=True)
            time.sleep(0.15)   # polite spacing
            return r
        except Exception:
            return None

    # ─── Surface expansion ────────────────────────────────────────────────
    def _wayback_urls(self, root: str) -> list[str]:
        """Historical URLs from the Wayback Machine CDX API (no tool needed)."""
        api = ("https://web.archive.org/cdx/search/cdx?"
               + urlencode({"url": f"*.{root}/*", "output": "json",
                            "fl": "original", "collapse": "urlkey", "limit": "6000"}))
        r = self._get(api)
        if not r or r.status_code != 200:
            return []
        try:
            rows = r.json()
            return [row[0] for row in rows[1:]] if len(rows) > 1 else []
        except Exception:
            return []

    def _js_files(self, urls: list[str]) -> list[str]:
        return [u for u in urls if urlparse(u).path.lower().endswith(".js")][:MAX_JS]

    def _analyse_js(self, target_id: str, js_urls: list[str]) -> tuple[set, list[Finding]]:
        """Fetch JS, pull endpoints, flag leaked secrets. Scope-gated per URL."""
        endpoints: set[str] = set()
        findings: list[Finding] = []
        js_urls = [u for u in js_urls if self._url_in_scope(target_id, u)]

        def work(u):
            r = self._get(u)
            if not r or r.status_code != 200 or not r.text:
                return None
            return u, r.text[:400000]

        with ThreadPoolExecutor(max_workers=CONCURRENCY) as ex:
            for fut in as_completed([ex.submit(work, u) for u in js_urls]):
                res = fut.result()
                if not res:
                    continue
                u, body = res
                for m in _JS_ENDPOINT.findall(body):
                    endpoints.add(m)
                for name, pat in _SECRET_PATTERNS.items():
                    hit = pat.search(body)
                    if hit:
                        t = cvss.bug_type("info-disclosure")
                        s, sev, vec = cvss.score(t["vector"])
                        findings.append(Finding(
                            kind="info-disclosure",
                            title=f"{name} leaked in client-side JavaScript",
                            url=u, evidence=f"match: {hit.group(0)[:60]}…",
                            severity=sev, cvss_score=s, cvss_vector=vec,
                            cwe=f"{t['cwe'][0]} ({t['cwe'][1]})",
                            confidence="firm"))
        return endpoints, findings

    # ─── Automated confirmable checks ─────────────────────────────────────
    def _check_exposed_files(self, target_id: str, hosts: list[str]) -> list[Finding]:
        found: list[Finding] = []
        targets = [(h, p, meta) for h in hosts
                   for p, meta in SENSITIVE_PATHS.items()]

        def work(item):
            host, path, (label, sig) = item
            base = host if host.startswith("http") else f"https://{host}"
            url = base.rstrip("/") + path
            if not self._url_in_scope(target_id, url):
                return None
            r = self._get(url, allow_redirects=False)
            if not r or r.status_code != 200 or not r.text:
                return None
            body = r.text[:2000]
            # Require the signature so we don't flag a 200 catch-all/SPA page.
            if sig and sig not in body and sig not in r.content[:200].decode("latin-1", "ignore"):
                return None
            ctype = r.headers.get("Content-Type", "")
            if "text/html" in ctype and sig in ("", "="):  # avoid SPA false-positives
                return None
            t = cvss.bug_type("info-disclosure")
            s, sev, vec = cvss.score(t["vector"])
            return Finding(kind="info-disclosure",
                           title=label, url=url,
                           evidence=f"HTTP 200, signature '{sig or path}' present",
                           severity=sev, cvss_score=s, cvss_vector=vec,
                           cwe=f"{t['cwe'][0]} ({t['cwe'][1]})", confidence="firm")

        with ThreadPoolExecutor(max_workers=CONCURRENCY) as ex:
            for fut in as_completed([ex.submit(work, it) for it in targets]):
                r = fut.result()
                if r:
                    found.append(r)
        return found

    def _check_cors(self, target_id: str, hosts: list[str]) -> list[Finding]:
        found: list[Finding] = []
        evil = "https://evil-jarvis-poc.example"

        def work(host):
            base = host if host.startswith("http") else f"https://{host}"
            if not self._url_in_scope(target_id, base):
                return None
            r = self._get(base, allow_redirects=True, extra_headers={"Origin": evil})
            if not r:
                return None
            acao = r.headers.get("Access-Control-Allow-Origin", "")
            acac = r.headers.get("Access-Control-Allow-Credentials", "")
            reflected = acao == evil or acao == "*"
            if reflected and acac.lower() == "true" and acao != "*":
                t = cvss.bug_type("cors")
                s, sev, vec = cvss.score(t["vector"])
                return Finding(kind="cors",
                               title="CORS reflects arbitrary Origin with credentials",
                               url=base,
                               evidence=f"ACAO: {acao}  ACAC: {acac}",
                               severity=sev, cvss_score=s, cvss_vector=vec,
                               cwe=f"{t['cwe'][0]} ({t['cwe'][1]})", confidence="firm")
            return None

        with ThreadPoolExecutor(max_workers=CONCURRENCY) as ex:
            for fut in as_completed([ex.submit(work, h) for h in hosts]):
                r = fut.result()
                if r:
                    found.append(r)
        return found

    def _check_takeover(self, target_id: str, hosts: list[str]) -> list[Finding]:
        found: list[Finding] = []

        def work(host):
            base = host if host.startswith("http") else f"https://{host}"
            if not self._url_in_scope(target_id, base):
                return None
            r = self._get(base)
            if not r or not r.text:
                return None
            body = r.text[:4000]
            for service, sig in TAKEOVER_FINGERPRINTS.items():
                if sig in body:
                    t = cvss.bug_type("subdomain-takeover")
                    s, sev, vec = cvss.score(t["vector"])
                    return Finding(kind="subdomain-takeover",
                                   title=f"Possible subdomain takeover ({service})",
                                   url=base,
                                   evidence=f"unclaimed-{service} signature: '{sig[:40]}'",
                                   severity=sev, cvss_score=s, cvss_vector=vec,
                                   cwe=f"{t['cwe'][0]} ({t['cwe'][1]})",
                                   confidence="tentative")
            return None

        with ThreadPoolExecutor(max_workers=CONCURRENCY) as ex:
            for fut in as_completed([ex.submit(work, h) for h in hosts]):
                r = fut.result()
                if r:
                    found.append(r)
        return found

    def _check_open_redirect(self, target_id: str, urls: list[str]) -> list[Finding]:
        """Param-based open redirect: set a redirect param to example.com and see
        if the server 30x-es us there. Benign external target, no exploitation."""
        found: list[Finding] = []
        canary = "https://example.com/jarvis-canary"
        candidates = []
        for u in urls:
            p = urlparse(u)
            q = dict(parse_qsl(p.query))
            hit = [k for k in q if k.lower() in REDIRECT_PARAMS]
            if hit:
                candidates.append((u, p, q, hit))
        # de-dup by (host, path, param-set) to avoid hammering
        seen, uniq = set(), []
        for u, p, q, hit in candidates:
            key = (p.hostname, p.path, tuple(sorted(hit)))
            if key not in seen:
                seen.add(key)
                uniq.append((u, p, q, hit))
        uniq = uniq[:60]

        def work(item):
            u, p, q, hit = item
            for k in hit:
                q[k] = canary
            test = urlunparse((p.scheme, p.netloc, p.path, p.params,
                               urlencode(q), p.fragment))
            if not self._url_in_scope(target_id, test):
                return None
            r = self._get(test, allow_redirects=False)
            if not r:
                return None
            loc = r.headers.get("Location", "")
            if r.status_code in (301, 302, 303, 307, 308) and "example.com" in loc:
                t = cvss.bug_type("open-redirect")
                s, sev, vec = cvss.score(t["vector"])
                return Finding(kind="open-redirect",
                               title=f"Open redirect via '{hit[0]}' parameter",
                               url=test,
                               evidence=f"HTTP {r.status_code} → Location: {loc[:80]}",
                               severity=sev, cvss_score=s, cvss_vector=vec,
                               cwe=f"{t['cwe'][0]} ({t['cwe'][1]})", confidence="firm")
            return None

        with ThreadPoolExecutor(max_workers=CONCURRENCY) as ex:
            for fut in as_completed([ex.submit(work, it) for it in uniq]):
                r = fut.result()
                if r:
                    found.append(r)
        return found

    # ─── Manual hit-list classification ───────────────────────────────────
    def _classify(self, urls: list[str]) -> dict[str, list[str]]:
        buckets: dict[str, list[str]] = {
            "idor": [], "ssrf": [], "open-redirect": [], "auth": [],
            "admin": [], "api": [], "upload": [],
        }
        seen = {k: set() for k in buckets}

        def add(bucket, url):
            key = url.split("?")[0] + "|" + "&".join(sorted(
                k for k, _ in parse_qsl(urlparse(url).query)))
            if key not in seen[bucket]:
                seen[bucket].add(key)
                buckets[bucket].append(url)

        for u in urls[:MAX_URLS_CLASSIFY]:
            p = urlparse(u)
            path = p.path.lower()
            params = {k.lower() for k, _ in parse_qsl(p.query)}
            segs = [s for s in path.split("/") if s]

            if params & IDOR_PARAMS or any(_ID_SEG.match(s) for s in segs):
                add("idor", u)
            if params & SSRF_PARAMS:
                add("ssrf", u)
            if params & REDIRECT_PARAMS:
                add("open-redirect", u)
            if _AUTH_RE.search(path):
                add("auth", u)
            if _ADMIN_RE.search(path):
                add("admin", u)
            if any(h in u.lower() for h in API_HINTS):
                add("api", u)
            if _UPLOAD_RE.search(path):
                add("upload", u)
        return buckets

    # ─── Orchestration ────────────────────────────────────────────────────
    def hunt(self, target_id: str, root_domain: str) -> str:
        t = self.bounty.get(target_id)                 # raises if unknown
        root = root_domain.strip().lower().lstrip("*.")

        # GATE 1: root must be explicitly in scope.
        if not self._host_in_scope(target_id, root):
            return (f"⛔ Refused: '{root}' is not confirmed IN-SCOPE for "
                    f"[{t.id}] {t.program}. Add it first:\n"
                    f"  /bounty scope {t.id} in {root}\n"
                    f"Only test assets the program authorises.")

        self._budget = MAX_REQUESTS
        started = time.time()
        log = [f"🎯 Vuln hunt — [{t.id}] {t.program} — root: {root}", ""]

        # 1) Live host surface (reuse recon pipeline's tools when present).
        try:
            from core.recon_pipeline import detect_tools, ReconPipeline
            tools = detect_tools()
            rp = ReconPipeline(self.jarvis)
            subs = rp._subdomains(tools, root)
            in_scope_hosts = [h for h in subs if self._host_in_scope(target_id, h)]
            live = rp._live_hosts(tools, in_scope_hosts) or in_scope_hosts
        except Exception:
            live = [root]
        live = [h for h in (live or [root]) if self._host_in_scope(
            target_id, urlparse(h if h.startswith("http") else "https://" + h).hostname or h)]
        live = live[:MAX_HOSTS] or [root]
        log.append(f"Live in-scope hosts: {len(live)}")

        # 2) Surface expansion: wayback + JS.
        wb = self._wayback_urls(root)
        wb = [u for u in wb if self._url_in_scope(target_id, u)]
        log.append(f"Historical URLs (in-scope): {len(wb)}")
        js_endpoints, js_findings = self._analyse_js(target_id, self._js_files(wb))
        if js_endpoints:
            log.append(f"Endpoints extracted from JS: {len(js_endpoints)}")

        # 3) Automated confirmable checks.
        findings: list[Finding] = []
        findings += js_findings
        findings += self._check_exposed_files(target_id, live)
        findings += self._check_cors(target_id, live)
        findings += self._check_takeover(target_id, live)
        findings += self._check_open_redirect(target_id, wb)

        # 4) Manual hit-list.
        buckets = self._classify(wb)

        # 5) Persist.
        stamp = time.strftime("%Y%m%d-%H%M%S")
        (HUNT_DIR / f"{t.id}-{stamp}.json").write_text(json.dumps({
            "target": t.id, "root": root, "live_hosts": live,
            "wayback_count": len(wb),
            "findings": [asdict(f) for f in findings],
            "hitlist": {k: v for k, v in buckets.items()},
            "requests_used": MAX_REQUESTS - self._budget,
            "elapsed_s": round(time.time() - started),
        }, indent=2, ensure_ascii=False), encoding="utf-8")

        return self._format(t, findings, buckets, log, started)

    # ─── Reporting ────────────────────────────────────────────────────────
    def _format(self, t, findings: list[Finding], buckets: dict,
                log: list[str], started: float) -> str:
        out = list(log)
        out.append("")

        out.append("═══ AUTOMATED FINDINGS (machine-confirmed) ═══")
        if findings:
            findings.sort(key=lambda f: f.cvss_score, reverse=True)
            for f in findings:
                out += ["", f.line()]
            out += ["", f"→ Draft a report for any of these:  "
                        f"/bounty report {t.id} <bug-type> <title>"]
        else:
            out.append("  none — clean on the automated checks (expected; the "
                       "money is usually in the manual list below).")

        out += ["", "═══ MANUAL HIT-LIST (where mid/high bugs live — test by hand) ═══"]
        HOW = {
            "idor":          "swap the ID for another user's — do you get their data? (CWE-639)",
            "ssrf":          "point the param at http://169.254.169.254/ or a collaborator (CWE-918)",
            "open-redirect": "already auto-tested; anything here is an extra candidate (CWE-601)",
            "auth":          "test reset-token reuse, session fixation, MFA bypass (CWE-287)",
            "admin":         "hit these as a low-priv / unauth user — do they load? (CWE-284)",
            "api":           "enumerate objects, remove auth header, tamper roles (CWE-284)",
            "upload":        "test extension/content-type bypass, path traversal (CWE-434)",
        }
        any_manual = False
        for bucket in ["idor", "access-control-admin", "api", "ssrf", "auth", "upload", "open-redirect"]:
            key = "admin" if bucket == "access-control-admin" else bucket
            items = buckets.get(key, [])
            if not items:
                continue
            any_manual = True
            label = {"admin": "ADMIN / privileged paths", "idor": "IDOR candidates",
                     "api": "API / object endpoints", "ssrf": "SSRF candidates",
                     "auth": "AUTH flows", "upload": "FILE UPLOAD",
                     "open-redirect": "REDIRECT params"}.get(key, key.upper())
            out += ["", f"── {label}  ({len(items)})  — {HOW.get(key,'')}"]
            for u in items[:12]:
                out.append(f"     {u}")
            if len(items) > 12:
                out.append(f"     … +{len(items)-12} more (full list in the saved hunt JSON)")
        if not any_manual:
            out.append("  (no classified endpoints — try a wider-scope root or a program "
                       "with more historical URLs.)")

        out += ["", f"(hunt saved · {round(time.time()-started)}s · "
                    f"{MAX_REQUESTS - self._budget} requests · budget cap {MAX_REQUESTS})",
                "Reminder: verify every finding reproduces before you report it. "
                "Only in-scope assets."]
        return "\n".join(out)


_hunter: Optional[VulnHunter] = None


def get_hunter(jarvis=None) -> VulnHunter:
    global _hunter
    if _hunter is None:
        _hunter = VulnHunter(jarvis)
    return _hunter
