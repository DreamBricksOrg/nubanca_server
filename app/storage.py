import shutil
from datetime import datetime
from pathlib import Path

FOLDERS = ("captures", "photos", "discards", "back-covers")
ALLOWED_EXTENSIONS = {".jpg", ".jpeg", ".png"}


def ensure_folders(root: Path) -> None:
    for name in FOLDERS:
        (root / name).mkdir(parents=True, exist_ok=True)


def is_allowed_extension(filename: str) -> bool:
    return Path(filename).suffix.lower() in ALLOWED_EXTENSIONS


def list_image_files(folder: Path) -> list[Path]:
    return [
        p for p in folder.iterdir()
        if p.is_file() and is_allowed_extension(p.name)
    ]


def most_recent_file(folder: Path):
    files = list_image_files(folder)
    if not files:
        return None
    return max(files, key=lambda p: p.stat().st_mtime)


def build_timestamped_filename(ext: str, dest_folder: Path, moment: datetime = None) -> str:
    moment = moment or datetime.now()
    base = moment.strftime("%Y%m%d_%H%M%S")
    ext = ext.lower()
    candidate = f"{base}{ext}"
    counter = 1
    while (dest_folder / candidate).exists():
        candidate = f"{base}_{counter}{ext}"
        counter += 1
    return candidate


def promote_latest_capture(captures_folder: Path, photos_folder: Path):
    files = list_image_files(captures_folder)
    if not files:
        return None

    latest = max(files, key=lambda p: p.stat().st_mtime)
    for f in files:
        if f != latest:
            f.unlink()

    new_name = build_timestamped_filename(latest.suffix, photos_folder)
    dest = photos_folder / new_name
    shutil.move(str(latest), str(dest))
    return dest


def discard_latest_photo(photos_folder: Path, discards_folder: Path):
    latest = most_recent_file(photos_folder)
    if latest is None:
        return None

    dest = discards_folder / latest.name
    shutil.move(str(latest), str(dest))
    return dest
