import os
import subprocess
import sys
import threading
import time
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest


@contextmanager
def server(statuses):
    paths = []

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            paths.append(self.path)
            status = statuses.get(self.path, 500)
            if status is None:
                time.sleep(4)
                return
            self.send_response(status)
            self.end_headers()

        def log_message(self, *args):
            pass

    http = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=http.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{http.server_port}/api/", paths
    finally:
        http.shutdown()
        http.server_close()
        thread.join()


@pytest.mark.parametrize(
    "statuses,code,expected",
    [
        ({"/api/server/ping": 200}, 0, ["/api/server/ping"]),
        (
            {"/api/server/ping": 404, "/api/server-info/ping": 200},
            0,
            ["/api/server/ping", "/api/server-info/ping"],
        ),
        ({"/api/server/ping": 503}, 1, ["/api/server/ping"]),
        ({"/api/server/ping": None}, 1, ["/api/server/ping"]),
        (
            {"/api/server/ping": 404, "/api/server-info/ping": 404},
            1,
            ["/api/server/ping", "/api/server-info/ping"],
        ),
    ],
)
def test_healthcheck_cli(statuses, code, expected):
    with server(statuses) as (url, paths):
        env = {**os.environ, "IMMICH_URL": url}
        result = subprocess.run(
            [sys.executable, "-m", "immich_chat_importer.healthcheck"],
            env=env,
            capture_output=True,
            text=True,
            timeout=10,
        )
        assert result.returncode == code, result.stderr
        assert paths == expected


def test_healthcheck_import_uses_only_standard_library():
    code = (
        "import sys; import immich_chat_importer.healthcheck; "
        "assert not {'pydantic', 'httpx', 'PIL'} & sys.modules.keys()"
    )
    result = subprocess.run(
        [sys.executable, "-c", code], capture_output=True, text=True, timeout=10
    )
    assert result.returncode == 0, result.stderr


@pytest.mark.parametrize("url", ["", "invalid-url", "http://127.0.0.1:0/api"])
def test_healthcheck_cli_invalid_or_unreachable_url(url):
    result = subprocess.run(
        [sys.executable, "-m", "immich_chat_importer.healthcheck"],
        env={**os.environ, "IMMICH_URL": url},
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert result.returncode == 1
