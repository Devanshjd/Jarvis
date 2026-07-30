"""
Browser-driver integration test — real headless Chromium, LOCAL fixture only.

Proves the gated browser mechanic for real (never a live site):
  · navigate is refused off the allowlist, allowed on it,
  · extract returns the page's interactive elements (data, not commands),
  · a normal text field fills,
  · a password field is REFUSED at the DOM level.

Serves a tiny fixture page on 127.0.0.1 and drives it headless. Skips cleanly
(exit 0) if Playwright's Chromium isn't installed.

Run:  python training/test_browser_control.py
"""
from __future__ import annotations

import io
import sys
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

_FIXTURE = b"""<!doctype html><html><body>
<h1>Fixture</h1>
<form>
  <input id="q" name="q" type="text" placeholder="search">
  <input id="pw" name="password" type="password">
  <button id="go" type="button">Go</button>
</form>
</body></html>"""


class _Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-Type", "text/html")
        self.end_headers()
        self.wfile.write(_FIXTURE)

    def log_message(self, *a):
        pass


def main() -> None:
    print("=" * 64)
    print(" BROWSER-DRIVER INTEGRATION (headless, local fixture)")
    print("=" * 64)

    # Skip cleanly if chromium isn't installed.
    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            p.chromium.launch(headless=True).close()
    except Exception as exc:
        print(f"  [SKIP] Playwright/Chromium unavailable: {str(exc)[:80]}")
        print("         (install: playwright install chromium)")
        sys.exit(0)

    from core.browser_control import BrowserDriver

    httpd = HTTPServer(("127.0.0.1", 0), _Handler)
    port = httpd.server_port
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{port}"

    passed, failed = 0, 0

    def check(name, cond):
        nonlocal passed, failed
        if cond:
            print(f"  [PASS] {name}"); passed += 1
        else:
            print(f"  [FAIL] {name}"); failed += 1

    drv = BrowserDriver([base], headless=True)
    try:
        r = drv.navigate(base + "/")
        check("navigate to an allowlisted origin", "127.0.0.1" in r.get("url", ""))

        ex = drv.extract()
        names = {e.get("name") for e in ex.get("elements", [])}
        check("extract returns interactive elements", {"q", "password"} <= names)

        check("fill a normal text field", drv.fill("#q", "hello world").get("filled") == "#q")

        refused = False
        try:
            drv.fill("#pw", "hunter2")
        except RuntimeError:
            refused = True
        check("password field refused at the DOM level", refused)

        off = False
        try:
            drv.navigate("https://example.com/")
        except RuntimeError:
            off = True
        check("navigate off the allowlist refused", off)
    finally:
        drv.close()
        httpd.shutdown()

    print(f"\n  {passed}/{passed + failed} passed")
    sys.exit(0 if failed == 0 else 1)


if __name__ == "__main__":
    main()
