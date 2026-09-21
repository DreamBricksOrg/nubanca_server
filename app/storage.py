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
