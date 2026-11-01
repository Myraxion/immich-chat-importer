"""Lightweight Docker HEALTHCHECK; configuration comes from container environment."""

import os
import sys
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import HTTPRedirectHandler, Request, build_opener


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(
        self, req: Request, fp: Any, code: int, msg: str, headers: Any, newurl: str
    ) -> None:
        return None


def main() -> int:
    base_url = os.environ.get("IMMICH_URL", "").strip().rstrip("/")
    if not base_url:
        print("IMMICH_URL is required for the health check", file=sys.stderr)
        return 1
    headers = {"Accept": "application/json"}
    if key := os.environ.get("IMMICH_API_KEY"):
        headers["x-api-key"] = key
    opener = build_opener(_NoRedirect())
    for endpoint in ("/server/ping", "/server-info/ping"):
        try:
            with opener.open(Request(base_url + endpoint, headers=headers), timeout=3) as response:
                return 0 if response.status == 200 else 1
        except HTTPError as exc:
            exc.close()
            if exc.code != 404 or endpoint != "/server/ping":
                return 1
        except (URLError, OSError, ValueError):
            return 1
    return 1


if __name__ == "__main__":
    sys.exit(main())
