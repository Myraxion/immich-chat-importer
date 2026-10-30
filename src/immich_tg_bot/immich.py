import hashlib
import logging
from datetime import datetime
from pathlib import Path
from typing import Any

import httpx

log = logging.getLogger(__name__)


def sha1_file(path: Path, chunk: int = 65536) -> str:
    h = hashlib.sha1()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(chunk), b""):
            h.update(block)
    return h.hexdigest()


class ImmichClient:
    def __init__(self, base_url: str, api_key: str) -> None:
        self.base_url = base_url
        self._album_cache: dict[str, str] = {}
        self._client = httpx.AsyncClient(
            base_url=base_url,
            headers={"x-api-key": api_key, "Accept": "application/json"},
            timeout=httpx.Timeout(connect=30.0, read=600.0, write=600.0, pool=30.0),
        )

    async def aclose(self) -> None:
        await self._client.aclose()

    async def ping(self) -> bool:
        try:
            r = await self._client.get("/server/ping")
            if r.status_code == 200:
                return True
            if r.status_code != 404:
                return False
            r = await self._client.get("/server-info/ping")
            return r.status_code == 200
        except httpx.HTTPError as e:
            log.warning("Immich ping failed: %s", e)
            return False

    async def upload_asset(
        self,
        *,
        file_path: Path,
        device_asset_id: str,
        device_id: str,
        file_created_at: datetime,
        file_modified_at: datetime,
        checksum: str | None = None,
        file_name: str | None = None,
    ) -> dict[str, Any]:
        headers: dict[str, str] = {}
        if checksum:
            headers["x-immich-checksum"] = checksum
        upload_name = file_name or file_path.name
        with file_path.open("rb") as f:
            files = {"assetData": (upload_name, f, "application/octet-stream")}
            data = {
                "deviceAssetId": device_asset_id,
                "deviceId": device_id,
                "fileCreatedAt": file_created_at.isoformat(),
                "fileModifiedAt": file_modified_at.isoformat(),
            }
            r = await self._client.post("/assets", files=files, data=data, headers=headers)
        r.raise_for_status()
        return r.json()

    async def get_or_create_album(self, name: str) -> str:
        if name in self._album_cache:
            return self._album_cache[name]
        r = await self._client.get("/albums")
        r.raise_for_status()
        for album in r.json():
            if album.get("albumName"):
                self._album_cache[album["albumName"]] = album["id"]
            if album.get("albumName") == name:
                return album["id"]
        r = await self._client.post("/albums", json={"albumName": name})
        r.raise_for_status()
        album_id = r.json()["id"]
        self._album_cache[name] = album_id
        return album_id

    async def add_to_album(self, album_id: str, asset_ids: list[str]) -> dict[str, str]:
        if not asset_ids:
            return {}
        r = await self._client.put(
            f"/albums/{album_id}/assets",
            json={"ids": asset_ids},
        )
        r.raise_for_status()
        return {
            result["id"]: result.get("error", "unknown")
            for result in r.json()
            if not result["success"] and result.get("error") != "duplicate"
        }
