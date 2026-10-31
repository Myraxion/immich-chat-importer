from datetime import UTC, datetime
from zoneinfo import ZoneInfo

import pytest
from PIL import Image

from immich_chat_importer.media_metadata import inspect_media


def test_exif_offset_preserves_capture_time_and_localizes_template_date(tmp_path):
    path = tmp_path / "photo.jpg"
    exif = Image.Exif()
    exif[34665] = {36867: "2020:01:02 14:00:00", 36881: "+09:00"}
    Image.new("RGB", (2, 2)).save(path, exif=exif)
    metadata = inspect_media(path, ZoneInfo("Asia/Shanghai"), datetime(2026, 1, 1, tzinfo=UTC))
    assert metadata.is_image
    assert metadata.capture_time.isoformat() == "2020-01-02T14:00:00+09:00"
    assert metadata.exif_date.isoformat() == "2020-01-02T13:00:00+08:00"


@pytest.mark.parametrize(
    "image,raw,offset",
    [
        (True, None, None),
        (True, "invalid", None),
        (True, "2020:01:02 14:00:00", "invalid"),
        (False, None, None),
    ],
)
def test_unavailable_exif_stays_absent_and_uses_message_fallback(tmp_path, image, raw, offset):
    path = tmp_path / "media"
    if image:
        exif = Image.Exif()
        if raw:
            exif[34665] = {36867: raw}
            if offset:
                exif[34665][36881] = offset
        Image.new("RGB", (2, 2)).save(path, format="JPEG", exif=exif)
    else:
        path.write_bytes(b"video bytes")
    fallback = datetime(2026, 1, 1, tzinfo=UTC)
    metadata = inspect_media(path, ZoneInfo("Asia/Shanghai"), fallback)
    assert metadata.exif_date is None
    assert metadata.capture_time == fallback
    assert metadata.is_image is image


@pytest.mark.parametrize("platform", ["telegram", "discord"])
@pytest.mark.parametrize(
    "raw,filename,created,sidecar",
    [
        (
            "2020:01:02 14:00:00",
            "20200102_1300.jpg",
            "2020-01-02T14:00:00+09:00",
            "2020-01-02T13:00:00+08:00",
        ),
        (None, "photo.jpg", "2026-01-01T00:00:00+00:00", "2026-01-01T08:00:00+08:00"),
        ("invalid", "photo.jpg", "2026-01-01T00:00:00+00:00", "2026-01-01T08:00:00+08:00"),
    ],
)
async def test_naming_and_upload_share_one_inspection(
    tmp_path, monkeypatch, platform, raw, filename, created, sidecar
):
    import hashlib
    from types import SimpleNamespace

    import httpx
    from aiogram.types import Message

    from immich_chat_importer.adapters.telegram.bot import _extract_ingest_item
    from immich_chat_importer.config import Settings
    from immich_chat_importer.adapters.discord.bot import process_import
    from immich_chat_importer.runtime import ingestion_runtime

    path = tmp_path / "photo.jpg"
    exif = Image.Exif()
    if raw:
        exif[34665] = {36867: raw, 36881: "+09:00"}
    Image.new("RGB", (2, 2)).save(path, exif=exif)
    original_bytes = path.read_bytes()
    opened = []
    original_open = Image.open

    def open_image(*args, **kwargs):
        opened.append(args[0])
        return original_open(*args, **kwargs)

    monkeypatch.setattr(Image, "open", open_image)
    requests = []
    original_client = httpx.AsyncClient

    def upload(request):
        requests.append(request)
        return httpx.Response(201, json={"id": "asset", "status": "created"})

    monkeypatch.setattr(
        "immich_chat_importer.immich.httpx.AsyncClient",
        lambda **kw: original_client(**kw, transport=httpx.MockTransport(upload)),
    )
    settings = Settings.model_construct(
        immich_url="https://immich.test",
        immich_api_key="key",
        tz="Asia/Shanghai",
        data_dir=tmp_path,
        cleanup_local_files=False,
        discord_allowed_user_ids=[42],
        telegram_document_name_template="{exif_date:%Y%m%d_%H%M}",
        discord_filename_template="{exif_date:%Y%m%d_%H%M}",
    )
    async with ingestion_runtime(settings) as pipeline:
        if platform == "telegram":

            class Bot:
                async def get_file(self, file_id):
                    return SimpleNamespace(file_path=str(path))

            message = Message.model_validate(
                {
                    "message_id": 1,
                    "date": datetime(2026, 1, 1, tzinfo=UTC),
                    "chat": {"id": 42, "type": "private"},
                    "document": {"file_id": "f", "file_unique_id": "u", "file_name": "photo.jpg"},
                }
            )
            item = await _extract_ingest_item(Bot(), message, tmp_path, settings)
            assert item.file_name == filename
            result = await pipeline.ingest([item])
            assert result.uploaded == 1
        else:
            message = SimpleNamespace(
                id=1,
                channel=SimpleNamespace(id=42),
                author=SimpleNamespace(id=42, name="Alice"),
                created_at=datetime(2026, 1, 1, tzinfo=UTC),
                content="",
                attachments=[
                    SimpleNamespace(
                        id=1,
                        filename="photo.jpg",
                        size=len(original_bytes),
                        url="https://cdn.test/photo",
                    )
                ],
            )
            async with original_client(
                transport=httpx.MockTransport(
                    lambda req: httpx.Response(200, content=original_bytes)
                )
            ) as client:
                result = await process_import(message, 42, settings, pipeline, client)
                assert "Uploaded: 1" in result
    assert len(opened) == 1
    request = requests[0]
    assert request.headers["x-immich-checksum"] == hashlib.sha1(original_bytes).hexdigest()
    assert original_bytes in request.content
    assert filename.encode() in request.content
    if platform == "discord" and raw != "2020:01:02 14:00:00":
        created = "2026-01-01T08:00:00+08:00"
    assert created.encode() in request.content
    assert sidecar.encode() in request.content


async def test_archive_members_use_own_capture_time_and_keep_original_names(tmp_path):
    from unittest.mock import AsyncMock
    from zipfile import ZipFile

    from immich_chat_importer.pipeline import IngestionPipeline, IngestItem
    from immich_chat_importer.state import State

    dated = tmp_path / "dated.jpg"
    plain = tmp_path / "plain.jpg"
    exif = Image.Exif()
    exif[34665] = {36867: "2020:01:02 14:00:00", 36881: "+09:00"}
    Image.new("RGB", (2, 2)).save(dated, exif=exif)
    Image.new("RGB", (2, 2)).save(plain)
    archive = tmp_path / "photos.zip"
    with ZipFile(archive, "w") as z:
        z.write(dated, "dated.jpg")
        z.write(plain, "plain.jpg")
    immich = AsyncMock()
    immich.upload_asset.side_effect = lambda **kw: {"id": kw["file_name"], "status": "created"}
    immich.get_or_create_album.return_value = "album"
    immich.add_to_album.return_value = {}
    fallback = datetime(2026, 1, 1, tzinfo=UTC)
    pipeline = IngestionPipeline(immich, State(), target_tz=ZoneInfo("Asia/Shanghai"))
    summary = await pipeline.ingest(
        [
            IngestItem(
                1,
                2,
                archive,
                "renamed.zip",
                fallback,
                target_album="Photos",
                original_file_name="photos.zip",
            )
        ]
    )
    assert summary.uploaded == 2
    uploads = {
        call.kwargs["file_name"]: call.kwargs for call in immich.upload_asset.await_args_list
    }
    assert uploads["dated.jpg"]["file_created_at"].isoformat() == "2020-01-02T14:00:00+09:00"
    assert uploads["plain.jpg"]["file_created_at"] == fallback
    assert all(upload["is_image"] for upload in uploads.values())
    immich.get_or_create_album.assert_awaited_once_with("Photos")
    immich.add_to_album.assert_awaited_once_with("album", ["dated.jpg", "plain.jpg"])
