import functools
import http.server
import sys
import threading
from pathlib import Path

import pytest

TOOL_DIR = Path(__file__).resolve().parent.parent
if str(TOOL_DIR) not in sys.path:
    sys.path.insert(0, str(TOOL_DIR))

DATA = Path(__file__).resolve().parent / "data"


class _QuietHandler(http.server.SimpleHTTPRequestHandler):
    extensions_map = {**http.server.SimpleHTTPRequestHandler.extensions_map,
                      ".html": "text/html; charset=utf-8", ".txt": "text/plain; charset=utf-8"}

    def log_message(self, *args):
        pass


def _serve(directory: Path):
    handler = functools.partial(_QuietHandler, directory=str(directory))
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)  # port 0 = random free port
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server


@pytest.fixture(scope="session")
def site():
    """Local EN/FR fixture site; yields its base URL (no trailing slash)."""
    server = _serve(DATA / "site")
    host, port = server.server_address[:2]
    yield f"http://{host}:{port}"
    server.shutdown()
    server.server_close()
