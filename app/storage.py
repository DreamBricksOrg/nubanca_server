import os
import shutil
import tempfile
import uuid
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


def build_unique_filename(ext: str) -> str:
    ext = ext.lower()
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    suffix = uuid.uuid4().hex[:8]
    return f"{timestamp}_{suffix}{ext}"


def promote_latest_capture(captures_folder: Path, photos_folder: Path):
    files = list_image_files(captures_folder)
    if not files:
        return None

    latest = max(files, key=lambda p: p.stat().st_mtime)

    new_name = build_timestamped_filename(latest.suffix, photos_folder)
    dest = photos_folder / new_name
    shutil.move(str(latest), str(dest))

    for f in files:
        if f != latest:
            f.unlink()

    return dest


def discard_latest_photo(photos_folder: Path, discards_folder: Path):
    latest = most_recent_file(photos_folder)
    if latest is None:
        return None

    dest = discards_folder / latest.name
    shutil.move(str(latest), str(dest))
    return dest


def save_uploaded_image(file_storage, dest_folder: Path) -> Path:
    if file_storage is None or not file_storage.filename:
        raise ValueError("Nenhum arquivo enviado")
    if not is_allowed_extension(file_storage.filename):
        raise ValueError("Extensão de arquivo não permitida")

    ext = Path(file_storage.filename).suffix.lower()
    name = build_timestamped_filename(ext, dest_folder)
    dest = dest_folder / name
    file_storage.save(str(dest))
    return dest


def save_uploaded_image_to_tempfile(file_storage) -> Path:
    if file_storage is None or not file_storage.filename:
        raise ValueError("Nenhum arquivo enviado")
    if not is_allowed_extension(file_storage.filename):
        raise ValueError("Extensão de arquivo não permitida")

    ext = Path(file_storage.filename).suffix.lower()
    fd, temp_name = tempfile.mkstemp(suffix=ext)
    temp_path = Path(temp_name)
    with os.fdopen(fd, "wb") as f:
        file_storage.save(f)
    return temp_path
