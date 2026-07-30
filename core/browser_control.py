"""
J.A.R.V.I.S — Browser Control  (gated, origin-allowlisted Playwright driver)

The browser half of JARVIS's Computer Use layer. It drives a real local Chromium
(so you watch it work), but every rail from the desktop controller applies here
too — and the DOM lets us enforce some of them *better* than on the native side:

  · ORIGIN ALLOWLIST. A session lists the sites it may touch. `navigate` to any
    other origin is refused, and every action re-checks the current page's origin
    (fail closed) — so a redirect/pop-up to another site can't be acted on.
  · PASSWORD FIELDS ARE REFUSED AT THE DOM LEVEL. `fill` inspects the element; an
    `input[type=password]` (or a credential-named field) is never typed into. You
    log in yourself.
  · STRUCTURED DOM IS DATA, NOT COMMANDS. `extract` returns interactive elements
    for YOU to choose from; the page's text never decides the next action.

Playwright's sync API is thread-affine, so the browser lives on its own worker
thread and is driven through a command queue. The coordinator
(`core.desktop_control`) owns the session, approval, submission gate and audit;
this module is just the safe mechanic.
"""
from __future__ import annotations

import base64
import logging
import queue
import re
import threading
from urllib.parse import urlparse

logger = logging.getLogger("jarvis.browser_control")

# Credential-ish field names refused even if not type=password (defence in depth).
_CRED_FIELD_RE = re.compile(
    r"(pass|pwd|otp|2fa|mfa|cvv|cvc|card.?number|ccnum|ssn|secret|seed|"
    r"private.?key|api.?key|token)", re.I)


def origin_of(url: str) -> str:
    """scheme://host[:port] — the unit the allowlist works in."""
    try:
        p = urlparse(url if "://" in url else "https://" + url)
        if not p.hostname:
            return ""
        host = p.hostname
        return f"{p.scheme}://{host}" + (f":{p.port}" if p.port else "")
    except Exception:
        return ""


class BrowserDriver:
    """A single Chromium page on a dedicated thread, bound to an allowlist."""

    def __init__(self, allowed_origins, headless: bool = False) -> None:
        self.allowed = {origin_of(o) for o in (allowed_origins or []) if o}
        self.allowed.discard("")
        self._headless = headless
        self._cmd: queue.Queue = queue.Queue()
        self._out: queue.Queue = queue.Queue()
        self._ready = threading.Event()
        self._err = None
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()
        self._ready.wait(timeout=45)
        if self._err:
            raise RuntimeError(self._err)

    # ── worker thread (all Playwright calls happen here) ─────────────────
    def _run(self) -> None:
        try:
            from playwright.sync_api import sync_playwright
        except Exception as exc:                      # pragma: no cover
            self._err = f"playwright not installed: {exc}"
            self._ready.set()
            return
        pw = browser = None
        try:
            pw = sync_playwright().start()
            browser = pw.chromium.launch(headless=self._headless)
            page = browser.new_page()
        except Exception as exc:                      # pragma: no cover
            self._err = f"chromium launch failed: {exc} (try: playwright install chromium)"
            self._ready.set()
            return
        self._ready.set()
        while True:
            cmd, args = self._cmd.get()
            if cmd == "__stop__":
                try:
                    browser.close(); pw.stop()
                except Exception:
                    pass
                self._out.put(("ok", {"closed": True}))
                return
            try:
                self._out.put(("ok", self._dispatch(page, cmd, args)))
            except Exception as exc:
                self._out.put(("err", str(exc)[:250]))

    def _call(self, cmd: str, **args):
        self._cmd.put((cmd, args))
        try:
            status, val = self._out.get(timeout=60)
        except queue.Empty:
            raise RuntimeError("browser command timed out")
        if status == "err":
            raise RuntimeError(val)
        return val

    def _dispatch(self, page, cmd: str, args: dict):
        if cmd == "navigate":
            url = args["url"]
            o = origin_of(url)
            if o not in self.allowed:
                raise RuntimeError(f"origin {o!r} is not in this session's allowlist")
            page.goto(url, wait_until="domcontentloaded", timeout=30000)
            return {"url": page.url, "title": page.title()}

        # Every non-navigate action re-checks the LIVE origin (fail closed).
        if origin_of(page.url) not in self.allowed:
            raise RuntimeError(f"current page ({page.url}) is outside the allowlist — refused")

        if cmd == "current":
            return {"url": page.url, "title": page.title()}
        if cmd == "extract":
            return self._extract(page)
        if cmd == "click":
            page.click(args["selector"], timeout=8000)
            return {"clicked": args["selector"], "url": page.url}
        if cmd == "fill":
            self._guard_not_credential(page, args["selector"])
            page.fill(args["selector"], str(args.get("text", "")), timeout=8000)
            return {"filled": args["selector"]}
        if cmd == "select":
            page.select_option(args["selector"], str(args.get("value", "")), timeout=8000)
            return {"selected": args.get("value")}
        if cmd == "upload":
            page.set_input_files(args["selector"], args["path"], timeout=8000)
            return {"uploaded": args["path"]}
        if cmd == "screenshot":
            return {"b64": base64.b64encode(page.screenshot()).decode("ascii")}
        raise RuntimeError(f"unknown browser command {cmd!r}")

    def _guard_not_credential(self, page, selector: str) -> None:
        """Refuse to type into a password / credential field — the user does that."""
        try:
            el = page.query_selector(selector)
            if el is None:
                return
            typ = (el.get_attribute("type") or "").lower()
            nid = " ".join(filter(None, [el.get_attribute("name") or "",
                                         el.get_attribute("id") or "",
                                         el.get_attribute("autocomplete") or ""]))
        except Exception:
            return
        if typ == "password" or _CRED_FIELD_RE.search(nid):
            raise RuntimeError("refuses to fill a password/credential field — please type it yourself")

    def _extract(self, page) -> dict:
        js = """() => {
          const out = [];
          const nodes = document.querySelectorAll(
            'a,button,input,select,textarea,[role=button],[role=link]');
          for (let i = 0; i < nodes.length && out.length < 80; i++) {
            const el = nodes[i];
            const r = el.getBoundingClientRect();
            if (r.width <= 0 || r.height <= 0) continue;
            out.push({
              tag: el.tagName.toLowerCase(),
              type: (el.getAttribute('type') || ''),
              name: (el.getAttribute('name') || el.id || ''),
              text: ((el.innerText || el.value || el.getAttribute('placeholder') || '')
                     .trim().slice(0, 60)),
            });
          }
          return { url: location.href, title: document.title, elements: out };
        }"""
        return page.evaluate(js)

    # ── public API (thread-safe; each returns a dict) ────────────────────
    def navigate(self, url: str) -> dict:
        return self._call("navigate", url=url)

    def current(self) -> dict:
        return self._call("current")

    def extract(self) -> dict:
        return self._call("extract")

    def click(self, selector: str) -> dict:
        return self._call("click", selector=selector)

    def fill(self, selector: str, text: str) -> dict:
        return self._call("fill", selector=selector, text=text)

    def select(self, selector: str, value: str) -> dict:
        return self._call("select", selector=selector, value=value)

    def upload(self, selector: str, path: str) -> dict:
        return self._call("upload", selector=selector, path=path)

    def screenshot(self) -> dict:
        return self._call("screenshot")

    def close(self) -> None:
        try:
            self._cmd.put(("__stop__", {}))
            self._out.get(timeout=10)
        except Exception:
            pass
