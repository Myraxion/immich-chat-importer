import hashlib
import logging
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import httpx

from .media_metadata import inspect_media
from .retry import retry

log = logging.getLogger(__name__)


def sha1_file(path: Path, chunk: int = 65536) -> str:
    h = hashlib.sha1()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(chunk), b""):
            h.update(block)
    return h.hexdigest()


class ImmichClient:
    def __init__(self, base_url: str, api_key: str, tz: str = "UTC") -> None:
        self.base_url = base_url
        self._tz = ZoneInfo(tz)
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
        is_image: bool | None = None,
    ) -> dict[str, Any]:
        headers: dict[str, str] = {}
        if checksum:
            headers["x-immich-checksum"] = checksum
        upload_name = file_name or file_path.name
        sidecar = None
        if is_image is None:
            is_image = inspect_media(file_path, self._tz, file_created_at).is_image
        if is_image:
            # Keep original bytes/checksum intact. Immich extracts capture time from XMP.
            date = file_created_at.astimezone(self._tz).isoformat()
            sidecar = (
                '<x:xmpmeta xmlns:x="adobe:ns:meta/">'
                '<rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#">'
                '<rdf:Description xmlns:exif="http://ns.adobe.com/exif/1.0/" '
                f'exif:DateTimeOriginal="{date}"/>'
                "</rdf:RDF></x:xmpmeta>"
            ).encode()

        async def upload() -> dict[str, Any]:
            with file_path.open("rb") as f:
                files: dict[str, tuple[str, Any, str]] = {
                    "assetData": (upload_name, f, "application/octet-stream")
                }
                if sidecar is not None:
                    files["sidecarData"] = (f"{upload_name}.xmp", sidecar, "application/rdf+xml")
                data = {
                    "deviceAssetId": device_asset_id,
                    "deviceId": device_id,
                    "fileCreatedAt": file_created_at.isoformat(),
                    "fileModifiedAt": file_modified_at.isoformat(),
                }
                r = await self._client.post("/assets", files=files, data=data, headers=headers)
            r.raise_for_status()
            return r.json()

        return await retry(upload, f"upload: {upload_name}")

    async def get_or_create_album(self, name: str) -> str:
        async def lookup() -> str | None:
            r = await self._client.get("/albums")
            r.raise_for_status()
            for album in r.json():
                if album.get("albumName") == name:
                    return album["id"]
            return None

        existing = await retry(lookup, f"album lookup: {name}")
        if existing:
            return existing
        try:
            r = await self._client.post("/albums", json={"albumName": name})
            r.raise_for_status()
            return r.json()["id"]
        except (httpx.TimeoutException, httpx.NetworkError, httpx.HTTPStatusError) as exc:
            if isinstance(exc, httpx.HTTPStatusError) and exc.response.status_code not in (
                500,
                502,
                503,
                504,
            ):
                raise
            try:
                existing = await retry(lookup, f"album lookup: {name}")
            except httpx.HTTPError:
                existing = None
            if existing:
                return existing
            raise RuntimeError(f"Album creation could not be confirmed: {name}") from exc

    async def add_to_album(self, album_id: str, asset_ids: list[str]) -> dict[str, str]:
        if not asset_ids:
            return {}

        async def associate() -> dict[str, str]:
            r = await self._client.put(f"/albums/{album_id}/assets", json={"ids": asset_ids})
            r.raise_for_status()
            return {
                result["id"]: result.get("error", "unknown")
                for result in r.json()
                if not result["success"] and result.get("error") != "duplicate"
            }

        return await retry(associate, f"album association: {album_id}")
