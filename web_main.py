"""
Launch the browser-based JARVIS shell.
"""

from __future__ import annotations

import os
import sys
import threading
import webbrowser

import uvicorn


ROOT = os.path.dirname(os.path.abspath(__file__))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from web.server import app  # noqa: E402


def _open_browser():
    try:
        webbrowser.open("http://127.0.0.1:8765", new=1)
    except Exception:
        pass


if __name__ == "__main__":
    host = os.environ.get("JARVIS_HOST", "127.0.0.1")
    port = int(os.environ.get("JARVIS_PORT", "8765"))
    if os.environ.get("JARVIS_NO_BROWSER", "").strip().lower() not in {"1", "true", "yes"}:
        threading.Timer(1.2, _open_browser).start()
    uvicorn.run(app, host=host, port=port, log_level="info")
