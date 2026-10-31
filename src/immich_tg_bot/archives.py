import asyncio
import logging
import zipfile
from pathlib import Path

log = logging.getLogger(__name__)

ARCHIVE_EXTENSIONS = (
    ".zip",
    ".rar",
    ".7z",
    ".tar",
    ".tar.gz",
    ".tgz",
    ".tar.bz2",
    ".tbz2",
    ".tar.xz",
    ".txz",
)

_JUNK_NAMES = {".DS_Store", "Thumbs.db", "desktop.ini"}
_JUNK_PARTS = ("__MACOSX",)

MEDIA_EXTENSIONS = {
    # photos
    ".jpg",
    ".jpeg",
    ".png",
    ".gif",
    ".webp",
    ".heic",
    ".heif",
    ".bmp",
    ".tif",
    ".tiff",
    ".avif",
    # raw
    ".dng",
    ".raw",
    ".cr2",
    ".cr3",
    ".nef",
    ".arw",
    ".rw2",
    ".orf",
    ".raf",
    # video
    ".mp4",
    ".mov",
    ".m4v",
    ".avi",
    ".mkv",
    ".webm",
    ".3gp",
    ".mpg",
    ".mpeg",
    ".wmv",
    ".flv",
}


def is_archive(filename: str) -> bool:
    name = filename.lower()
    return any(name.endswith(ext) for ext in ARCHIVE_EXTENSIONS)


def is_media(filename: str) -> bool:
    name = filename.lower()
    return Path(name).suffix in MEDIA_EXTENSIONS


async def extract(archive: Path, dest: Path) -> None:
    """Extract any libarchive-supported format (zip/rar/7z/tar*) via bsdtar."""
    dest.mkdir(parents=True, exist_ok=True)
    options = []
    if zipfile.is_zipfile(archive):
        with zipfile.ZipFile(archive) as bundle:
            for entry in bundle.infolist():
                if entry.flag_bits & 0x800 or entry.filename.isascii():
                    continue
                raw_name = entry.filename.encode("cp437")
                try:
                    raw_name.decode("utf-8")
                except UnicodeDecodeError:
                    try:
                        raw_name.decode("gbk")
                    except UnicodeDecodeError:
                        continue
                    options = ["--options", "hdrcharset=GBK"]
                    break
    proc = await asyncio.create_subprocess_exec(
        "bsdtar",
        "-x",
        *options,
        "-f",
        str(archive),
        "-C",
        str(dest),
        stdin=asyncio.subprocess.DEVNULL,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    _, stderr = await proc.communicate()
    if proc.returncode != 0:
        raise RuntimeError(
            f"bsdtar exited {proc.returncode}: {stderr.decode('utf-8', errors='replace').strip()}"
        )


def walk_media(root: Path) -> tuple[list[Path], list[Path]]:
    found: list[Path] = []
    skipped: list[Path] = []
    for p in root.rglob("*"):
        if not p.is_file():
            continue
        if p.name in _JUNK_NAMES or p.name.startswith("._"):
            continue
        if any(part in _JUNK_PARTS for part in p.parts):
            continue
        if p.suffix.lower() in MEDIA_EXTENSIONS:
            found.append(p)
        else:
            skipped.append(p)
    return found, skipped
