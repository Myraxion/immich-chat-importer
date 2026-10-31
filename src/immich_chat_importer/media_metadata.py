from dataclasses import dataclass
from datetime import datetime, timezone, tzinfo
from pathlib import Path

from PIL import Image

_EXIF_DATETIME_ORIGINAL = 36867
_EXIF_DATETIME = 306


@dataclass(frozen=True)
class MediaMetadata:
    exif_date: datetime | None
    capture_time: datetime
    is_image: bool


def inspect_media(path: Path, target_tz: tzinfo, fallback_created_at: datetime) -> MediaMetadata:
    """Inspect once; a missing EXIF value is distinct from an uninspected file."""
    is_image = False
    capture = None
    try:
        with Image.open(path) as img:
            is_image = True
            capture = _read_exif_datetime(img, target_tz)
    except Exception:
        pass
    return MediaMetadata(
        capture.astimezone(target_tz) if capture else None,
        capture or fallback_created_at,
        is_image,
    )


def _read_exif_datetime(img: Image.Image, target_tz: tzinfo) -> datetime | None:
    try:
        exif = img.getexif()
        original = exif.get_ifd(34665)
    except Exception:
        return None
    if not exif:
        return None
    for tag, offset_tag in ((_EXIF_DATETIME_ORIGINAL, 36881), (_EXIF_DATETIME, 36880)):
        raw = original.get(tag) or exif.get(tag)
        if not raw:
            continue
        try:
            value = datetime.strptime(str(raw), "%Y:%m:%d %H:%M:%S")
            offset = original.get(offset_tag) or exif.get(offset_tag)
            zone = target_tz
            if offset:
                parsed = datetime.strptime(str(offset), "%z").utcoffset()
                if parsed is not None:
                    zone = timezone(parsed)
            return value.replace(tzinfo=zone)
        except ValueError:
            continue
    return None
