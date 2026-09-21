# Photo Print API Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a Flask API that promotes new camera captures to a `photos` folder, lets a tablet discard or submit a treated final image, and stubs out the A4 print step.

**Architecture:** Flask app factory (`app/__init__.py`) with a pure-stdlib `storage.py` module (folder/file operations), a `printing.py` stub module, and a single blueprint (`routes.py`) exposing `GET /image`, `POST /discard`, `POST /print`, `GET /files/<folder>/<filename>`. Config (storage root, host, port, base URL) comes from environment variables via `app/config.py`.

**Tech Stack:** Python 3, Flask, python-dotenv, pytest (dev).

Reference spec: `docs/superpowers/specs/2026-09-21-photo-print-api-design.md`

---

### Task 1: Environment & scaffolding

**Files:**
- Create: `requirements.txt`
- Create: `requirements-dev.txt`
- Create: `pytest.ini`
- Create: `.env.example`
- Create: `app/__init__.py` (empty placeholder for now, filled in Task 7)
- Create: `app/config.py`

- [ ] **Step 1: Create the storage and app folder skeleton**

Run:
```bash
mkdir -p storage/captures storage/photos storage/discards storage/back-covers app tests
```

- [ ] **Step 2: Create `requirements.txt`**

```
Flask==3.0.3
python-dotenv==1.0.1
```

- [ ] **Step 3: Create `requirements-dev.txt`**

```
-r requirements.txt
pytest==8.3.3
```

- [ ] **Step 4: Create `pytest.ini`**

```ini
[pytest]
pythonpath = .
```

- [ ] **Step 5: Create a virtualenv and install dev dependencies**

Run:
```bash
python -m venv venv
source venv/Scripts/activate
pip install -r requirements-dev.txt
```
Expected: install completes with no errors.

- [ ] **Step 6: Create `.env.example`**

```
STORAGE_ROOT=storage
HOST=0.0.0.0
PORT=5000
BASE_URL=http://localhost:5000
```

- [ ] **Step 7: Create `app/config.py`**

```python
import os
from pathlib import Path


class Config:
    STORAGE_ROOT = Path(os.environ.get("STORAGE_ROOT", "storage")).resolve()
    HOST = os.environ.get("HOST", "0.0.0.0")
    PORT = int(os.environ.get("PORT", "5000"))
    BASE_URL = os.environ.get("BASE_URL") or f"http://localhost:{PORT}"
```

- [ ] **Step 8: Create empty `app/__init__.py` placeholder**

```python
```

(Left empty on purpose — filled in by Task 7 once `storage.py` and `routes.py` exist.)

- [ ] **Step 9: Commit**

```bash
git init
git add requirements.txt requirements-dev.txt pytest.ini .env.example app/config.py app/__init__.py
git commit -m "chore: scaffold project, config and dev environment"
```

---

### Task 2: `storage.ensure_folders`

**Files:**
- Modify: `app/storage.py` (create)
- Test: `tests/test_storage.py` (create)

- [ ] **Step 1: Write the failing test**

```python
# tests/test_storage.py
from app.storage import ensure_folders, FOLDERS


def test_ensure_folders_creates_all_expected_subfolders(tmp_path):
    ensure_folders(tmp_path)

    for name in FOLDERS:
        assert (tmp_path / name).is_dir()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_storage.py::test_ensure_folders_creates_all_expected_subfolders -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.storage'`

- [ ] **Step 3: Write minimal implementation**

```python
# app/storage.py
from pathlib import Path

FOLDERS = ("captures", "photos", "discards", "back-covers")
ALLOWED_EXTENSIONS = {".jpg", ".jpeg", ".png"}


def ensure_folders(root: Path) -> None:
    for name in FOLDERS:
        (root / name).mkdir(parents=True, exist_ok=True)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_storage.py::test_ensure_folders_creates_all_expected_subfolders -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add app/storage.py tests/test_storage.py
git commit -m "feat: add storage.ensure_folders"
```

---

### Task 3: `storage.is_allowed_extension` and `storage.list_image_files`

**Files:**
- Modify: `app/storage.py`
- Test: `tests/test_storage.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_storage.py (append)
from app.storage import is_allowed_extension, list_image_files


def test_is_allowed_extension_accepts_known_image_types():
    assert is_allowed_extension("foo.jpg")
    assert is_allowed_extension("foo.JPEG")
    assert is_allowed_extension("foo.png")


def test_is_allowed_extension_rejects_other_types():
    assert not is_allowed_extension("foo.txt")
    assert not is_allowed_extension("foo")


def test_list_image_files_only_returns_allowed_images(tmp_path):
    (tmp_path / "a.jpg").write_bytes(b"x")
    (tmp_path / "b.png").write_bytes(b"x")
    (tmp_path / "notes.txt").write_bytes(b"x")

    result = {p.name for p in list_image_files(tmp_path)}

    assert result == {"a.jpg", "b.png"}
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_storage.py -k "is_allowed_extension or list_image_files" -v`
Expected: FAIL with `ImportError: cannot import name 'is_allowed_extension'`

- [ ] **Step 3: Write minimal implementation**

```python
# app/storage.py (append)
def is_allowed_extension(filename: str) -> bool:
    return Path(filename).suffix.lower() in ALLOWED_EXTENSIONS


def list_image_files(folder: Path) -> list[Path]:
    return [
        p for p in folder.iterdir()
        if p.is_file() and is_allowed_extension(p.name)
    ]
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_storage.py -k "is_allowed_extension or list_image_files" -v`
Expected: PASS (3 passed)

- [ ] **Step 5: Commit**

```bash
git add app/storage.py tests/test_storage.py
git commit -m "feat: add is_allowed_extension and list_image_files"
```

---

### Task 4: `storage.most_recent_file` and `storage.build_timestamped_filename`

**Files:**
- Modify: `app/storage.py`
- Test: `tests/test_storage.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_storage.py (append)
import time
from datetime import datetime

from app.storage import most_recent_file, build_timestamped_filename


def test_most_recent_file_returns_none_when_folder_empty(tmp_path):
    assert most_recent_file(tmp_path) is None


def test_most_recent_file_returns_the_newest_by_mtime(tmp_path):
    older = tmp_path / "older.jpg"
    older.write_bytes(b"x")
    time.sleep(0.01)
    newer = tmp_path / "newer.jpg"
    newer.write_bytes(b"x")

    assert most_recent_file(tmp_path) == newer


def test_build_timestamped_filename_uses_given_moment(tmp_path):
    moment = datetime(2026, 9, 21, 14, 32, 1)

    name = build_timestamped_filename(".jpg", tmp_path, moment=moment)

    assert name == "20260921_143201.jpg"


def test_build_timestamped_filename_avoids_collisions(tmp_path):
    moment = datetime(2026, 9, 21, 14, 32, 1)
    (tmp_path / "20260921_143201.jpg").write_bytes(b"x")

    name = build_timestamped_filename(".jpg", tmp_path, moment=moment)

    assert name == "20260921_143201_1.jpg"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_storage.py -k "most_recent_file or build_timestamped_filename" -v`
Expected: FAIL with `ImportError: cannot import name 'most_recent_file'`

- [ ] **Step 3: Write minimal implementation**

```python
# app/storage.py (append)
from datetime import datetime


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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_storage.py -k "most_recent_file or build_timestamped_filename" -v`
Expected: PASS (4 passed)

- [ ] **Step 5: Commit**

```bash
git add app/storage.py tests/test_storage.py
git commit -m "feat: add most_recent_file and build_timestamped_filename"
```

---

### Task 5: `storage.promote_latest_capture`

**Files:**
- Modify: `app/storage.py`
- Test: `tests/test_storage.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_storage.py (append)
from app.storage import promote_latest_capture


def test_promote_latest_capture_returns_none_when_captures_empty(tmp_path):
    captures = tmp_path / "captures"
    photos = tmp_path / "photos"
    captures.mkdir()
    photos.mkdir()

    assert promote_latest_capture(captures, photos) is None


def test_promote_latest_capture_moves_and_renames_single_file(tmp_path):
    captures = tmp_path / "captures"
    photos = tmp_path / "photos"
    captures.mkdir()
    photos.mkdir()
    (captures / "DSC0001.jpg").write_bytes(b"x")

    dest = promote_latest_capture(captures, photos)

    assert dest.parent == photos
    assert dest.exists()
    assert not (captures / "DSC0001.jpg").exists()
    assert list(captures.iterdir()) == []


def test_promote_latest_capture_keeps_only_the_newest_and_deletes_others(tmp_path):
    captures = tmp_path / "captures"
    photos = tmp_path / "photos"
    captures.mkdir()
    photos.mkdir()
    (captures / "older.jpg").write_bytes(b"x")
    time.sleep(0.01)
    (captures / "newer.jpg").write_bytes(b"x")

    dest = promote_latest_capture(captures, photos)

    assert dest.exists()
    assert list(captures.iterdir()) == []
    assert len(list(photos.iterdir())) == 1
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_storage.py -k promote_latest_capture -v`
Expected: FAIL with `ImportError: cannot import name 'promote_latest_capture'`

- [ ] **Step 3: Write minimal implementation**

```python
# app/storage.py (append)
import shutil


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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_storage.py -k promote_latest_capture -v`
Expected: PASS (3 passed)

- [ ] **Step 5: Commit**

```bash
git add app/storage.py tests/test_storage.py
git commit -m "feat: add promote_latest_capture"
```

---

### Task 6: `storage.discard_latest_photo`

**Files:**
- Modify: `app/storage.py`
- Test: `tests/test_storage.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_storage.py (append)
from app.storage import discard_latest_photo


def test_discard_latest_photo_returns_none_when_photos_empty(tmp_path):
    photos = tmp_path / "photos"
    discards = tmp_path / "discards"
    photos.mkdir()
    discards.mkdir()

    assert discard_latest_photo(photos, discards) is None


def test_discard_latest_photo_moves_newest_file_keeping_its_name(tmp_path):
    photos = tmp_path / "photos"
    discards = tmp_path / "discards"
    photos.mkdir()
    discards.mkdir()
    (photos / "older.jpg").write_bytes(b"x")
    time.sleep(0.01)
    (photos / "20260921_143201.jpg").write_bytes(b"x")

    dest = discard_latest_photo(photos, discards)

    assert dest == discards / "20260921_143201.jpg"
    assert dest.exists()
    assert (photos / "older.jpg").exists()
    assert not (photos / "20260921_143201.jpg").exists()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_storage.py -k discard_latest_photo -v`
Expected: FAIL with `ImportError: cannot import name 'discard_latest_photo'`

- [ ] **Step 3: Write minimal implementation**

```python
# app/storage.py (append)
def discard_latest_photo(photos_folder: Path, discards_folder: Path):
    latest = most_recent_file(photos_folder)
    if latest is None:
        return None

    dest = discards_folder / latest.name
    shutil.move(str(latest), str(dest))
    return dest
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_storage.py -k discard_latest_photo -v`
Expected: PASS (2 passed)

- [ ] **Step 5: Commit**

```bash
git add app/storage.py tests/test_storage.py
git commit -m "feat: add discard_latest_photo"
```

---

### Task 7: `storage.save_uploaded_image`

**Files:**
- Modify: `app/storage.py`
- Test: `tests/test_storage.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_storage.py (append)
import io
from werkzeug.datastructures import FileStorage

from app.storage import save_uploaded_image


def test_save_uploaded_image_raises_for_missing_file(tmp_path):
    dest_folder = tmp_path / "back-covers"
    dest_folder.mkdir()

    try:
        save_uploaded_image(None, dest_folder)
        assert False, "expected ValueError"
    except ValueError:
        pass


def test_save_uploaded_image_raises_for_disallowed_extension(tmp_path):
    dest_folder = tmp_path / "back-covers"
    dest_folder.mkdir()
    upload = FileStorage(stream=io.BytesIO(b"x"), filename="final.gif")

    try:
        save_uploaded_image(upload, dest_folder)
        assert False, "expected ValueError"
    except ValueError:
        pass


def test_save_uploaded_image_saves_with_timestamped_name(tmp_path):
    dest_folder = tmp_path / "back-covers"
    dest_folder.mkdir()
    upload = FileStorage(stream=io.BytesIO(b"binary-image-data"), filename="final.jpg")

    dest = save_uploaded_image(upload, dest_folder)

    assert dest.parent == dest_folder
    assert dest.exists()
    assert dest.read_bytes() == b"binary-image-data"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_storage.py -k save_uploaded_image -v`
Expected: FAIL with `ImportError: cannot import name 'save_uploaded_image'`

- [ ] **Step 3: Write minimal implementation**

```python
# app/storage.py (append)
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_storage.py -k save_uploaded_image -v`
Expected: PASS (3 passed)

- [ ] **Step 5: Commit**

```bash
git add app/storage.py tests/test_storage.py
git commit -m "feat: add save_uploaded_image"
```

---

### Task 8: `printing.print_image` stub

**Files:**
- Create: `app/printing.py`
- Test: `tests/test_printing.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_printing.py
from pathlib import Path

from app.printing import print_image


def test_print_image_stub_returns_not_printed(tmp_path):
    fake_file = tmp_path / "cover.jpg"
    fake_file.write_bytes(b"x")

    result = print_image(fake_file)

    assert result == {
        "printed": False,
        "message": "Impressão ainda não implementada (stub)",
    }
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_printing.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.printing'`

- [ ] **Step 3: Write minimal implementation**

```python
# app/printing.py
import logging
from pathlib import Path

logger = logging.getLogger(__name__)


def print_image(path: Path) -> dict:
    """Stub: hardware (printer/driver for A4) is not available yet.

    Once defined, replace the body with the real PowerShell call, e.g.:
    subprocess.run(
        ["powershell", "-Command", f"Start-Process -FilePath '{path}' -Verb Print"],
        check=True,
    )
    """
    logger.info("print_image stub called for %s", path)
    return {"printed": False, "message": "Impressão ainda não implementada (stub)"}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_printing.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add app/printing.py tests/test_printing.py
git commit -m "feat: add print_image stub"
```

---

### Task 9: App factory (`create_app`) and folder auto-creation on startup

**Files:**
- Modify: `app/__init__.py`
- Test: `tests/conftest.py` (create)
- Test: `tests/test_app_factory.py` (create)

- [ ] **Step 1: Write the failing test**

```python
# tests/conftest.py
import pytest

from app import create_app
from app.config import Config


@pytest.fixture
def app(tmp_path):
    class TestConfig(Config):
        STORAGE_ROOT = tmp_path
        BASE_URL = "http://testserver"

    application = create_app(TestConfig)
    application.config["TESTING"] = True
    return application


@pytest.fixture
def client(app):
    return app.test_client()
```

```python
# tests/test_app_factory.py
from app.storage import FOLDERS


def test_create_app_creates_all_storage_folders(app):
    root = app.config["STORAGE_ROOT"]

    for name in FOLDERS:
        assert (root / name).is_dir()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_app_factory.py -v`
Expected: FAIL (`app/__init__.py` has no `create_app`, since it's currently an empty placeholder from Task 1)

- [ ] **Step 3: Write minimal implementation**

```python
# app/__init__.py
from flask import Flask

from .config import Config
from .storage import ensure_folders


def create_app(config_class=Config):
    app = Flask(__name__)
    app.config.from_object(config_class)
    ensure_folders(app.config["STORAGE_ROOT"])
    return app
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_app_factory.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add app/__init__.py tests/conftest.py tests/test_app_factory.py
git commit -m "feat: add create_app factory with folder auto-creation"
```

---

### Task 10: `GET /image` endpoint

**Files:**
- Create: `app/routes.py`
- Modify: `app/__init__.py`
- Test: `tests/test_routes.py` (create)

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_routes.py
def test_get_image_returns_204_when_no_new_capture(client):
    response = client.get("/image")

    assert response.status_code == 204


def test_get_image_promotes_capture_and_returns_url(client, app):
    captures = app.config["STORAGE_ROOT"] / "captures"
    (captures / "DSC0001.jpg").write_bytes(b"x")

    response = client.get("/image")

    assert response.status_code == 200
    data = response.get_json()
    assert data["image_url"].startswith("http://testserver/files/photos/")
    assert data["image_url"].endswith(".jpg")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_routes.py -v`
Expected: FAIL with `404 != 204` / `ModuleNotFoundError: No module named 'app.routes'` (no blueprint registered yet)

- [ ] **Step 3: Write minimal implementation**

```python
# app/routes.py
from flask import Blueprint, current_app, jsonify

from . import storage

bp = Blueprint("main", __name__)


@bp.get("/image")
def get_image():
    root = current_app.config["STORAGE_ROOT"]
    dest = storage.promote_latest_capture(root / "captures", root / "photos")
    if dest is None:
        return "", 204

    base_url = current_app.config["BASE_URL"].rstrip("/")
    image_url = f"{base_url}/files/photos/{dest.name}"
    return jsonify({"image_url": image_url})
```

```python
# app/__init__.py (modify create_app body)
from flask import Flask

from .config import Config
from .storage import ensure_folders


def create_app(config_class=Config):
    app = Flask(__name__)
    app.config.from_object(config_class)
    ensure_folders(app.config["STORAGE_ROOT"])

    from .routes import bp
    app.register_blueprint(bp)

    return app
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_routes.py -v`
Expected: PASS (2 passed)

- [ ] **Step 5: Commit**

```bash
git add app/routes.py app/__init__.py tests/test_routes.py
git commit -m "feat: add GET /image endpoint"
```

---

### Task 11: `POST /discard` endpoint

**Files:**
- Modify: `app/routes.py`
- Test: `tests/test_routes.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_routes.py (append)
def test_post_discard_returns_404_when_no_photo(client):
    response = client.post("/discard")

    assert response.status_code == 404
    assert response.get_json() == {
        "success": False,
        "message": "Nenhuma foto para descartar",
    }


def test_post_discard_moves_latest_photo(client, app):
    photos = app.config["STORAGE_ROOT"] / "photos"
    (photos / "20260921_143201.jpg").write_bytes(b"x")

    response = client.post("/discard")

    assert response.status_code == 200
    assert response.get_json() == {"success": True, "message": "Foto descartada"}
    discards = app.config["STORAGE_ROOT"] / "discards"
    assert (discards / "20260921_143201.jpg").exists()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_routes.py -k discard -v`
Expected: FAIL with `404 != <no route>` (405/404 Method Not Allowed, route doesn't exist yet)

- [ ] **Step 3: Write minimal implementation**

```python
# app/routes.py (append)
@bp.post("/discard")
def discard_image():
    root = current_app.config["STORAGE_ROOT"]
    dest = storage.discard_latest_photo(root / "photos", root / "discards")
    if dest is None:
        return jsonify({"success": False, "message": "Nenhuma foto para descartar"}), 404
    return jsonify({"success": True, "message": "Foto descartada"})
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_routes.py -k discard -v`
Expected: PASS (2 passed)

- [ ] **Step 5: Commit**

```bash
git add app/routes.py tests/test_routes.py
git commit -m "feat: add POST /discard endpoint"
```

---

### Task 12: `POST /print` endpoint

**Files:**
- Modify: `app/routes.py`
- Test: `tests/test_routes.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_routes.py (append)
import io


def test_post_print_saves_file_and_returns_success(client, app):
    data = {
        "image": (io.BytesIO(b"final-image-bytes"), "final.jpg"),
    }

    response = client.post("/print", data=data, content_type="multipart/form-data")

    assert response.status_code == 200
    body = response.get_json()
    assert body["success"] is True
    back_covers = app.config["STORAGE_ROOT"] / "back-covers"
    assert len(list(back_covers.iterdir())) == 1


def test_post_print_rejects_disallowed_extension(client):
    data = {
        "image": (io.BytesIO(b"x"), "final.gif"),
    }

    response = client.post("/print", data=data, content_type="multipart/form-data")

    assert response.status_code == 400
    assert response.get_json()["success"] is False


def test_post_print_rejects_missing_file(client):
    response = client.post("/print", data={}, content_type="multipart/form-data")

    assert response.status_code == 400
    assert response.get_json()["success"] is False
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_routes.py -k print -v`
Expected: FAIL (no `/print` route registered)

- [ ] **Step 3: Write minimal implementation**

```python
# app/routes.py (top of file, add import)
from flask import request

# app/routes.py (append)
from . import printing


@bp.post("/print")
def print_image_route():
    root = current_app.config["STORAGE_ROOT"]
    file_storage = request.files.get("image")

    try:
        dest = storage.save_uploaded_image(file_storage, root / "back-covers")
    except ValueError as exc:
        return jsonify({"success": False, "message": str(exc)}), 400

    printing.print_image(dest)
    return jsonify({
        "success": True,
        "message": "Imagem salva em back-covers; impressão ainda não implementada (stub)",
    })
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_routes.py -k print -v`
Expected: PASS (3 passed)

- [ ] **Step 5: Commit**

```bash
git add app/routes.py tests/test_routes.py
git commit -m "feat: add POST /print endpoint"
```

---

### Task 13: `GET /files/<folder>/<filename>` endpoint

**Files:**
- Modify: `app/routes.py`
- Test: `tests/test_routes.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_routes.py (append)
def test_serve_file_returns_file_from_allowed_folder(client, app):
    photos = app.config["STORAGE_ROOT"] / "photos"
    (photos / "20260921_143201.jpg").write_bytes(b"image-bytes")

    response = client.get("/files/photos/20260921_143201.jpg")

    assert response.status_code == 200
    assert response.data == b"image-bytes"


def test_serve_file_returns_404_for_disallowed_folder(client):
    response = client.get("/files/secrets/anything.jpg")

    assert response.status_code == 404
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_routes.py -k serve_file -v`
Expected: FAIL (no `/files/<folder>/<filename>` route)

- [ ] **Step 3: Write minimal implementation**

```python
# app/routes.py (top of file, add import)
from flask import abort, send_from_directory

# app/routes.py (append)
ALLOWED_FOLDERS = {"captures", "photos", "discards", "back-covers"}


@bp.get("/files/<folder>/<filename>")
def serve_file(folder, filename):
    if folder not in ALLOWED_FOLDERS:
        abort(404)
    root = current_app.config["STORAGE_ROOT"]
    return send_from_directory(root / folder, filename)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_routes.py -k serve_file -v`
Expected: PASS (2 passed)

- [ ] **Step 5: Commit**

```bash
git add app/routes.py tests/test_routes.py
git commit -m "feat: add GET /files/<folder>/<filename> endpoint"
```

---

### Task 14: Entrypoint and full test suite verification

**Files:**
- Create: `run.py`

- [ ] **Step 1: Create `run.py`**

```python
from app import create_app

app = create_app()

if __name__ == "__main__":
    app.run(host=app.config["HOST"], port=app.config["PORT"])
```

- [ ] **Step 2: Run the full test suite**

Run: `pytest -v`
Expected: all tests pass (storage, printing, app factory, routes).

- [ ] **Step 3: Manual smoke test of the running server**

Run:
```bash
python run.py
```
In another terminal:
```bash
curl -i http://localhost:5000/image
```
Expected: `204 No Content` (storage/captures is empty at this point).

Then:
```bash
cp storage/photos/.gitkeep storage/captures/test.jpg 2>/dev/null || echo "fake-jpg-bytes" > storage/captures/test.jpg
curl -i http://localhost:5000/image
```
Expected: `200` with `{"image_url": "http://localhost:5000/files/photos/<timestamp>.jpg"}`.

Stop the server (Ctrl+C) when done.

- [ ] **Step 4: Commit**

```bash
git add run.py
git commit -m "feat: add run.py entrypoint"
```

---

## Notes for whoever picks this up

- The `/print` printing step is intentionally a stub (`app/printing.py`) — hardware (printer/driver for A4) wasn't available to define the real PowerShell command during design. Replace `print_image`'s body per the comment in Task 8 once that's known.
- `GET /image` always deletes any capture files other than the most recent one it finds in `captures/` — this was an explicit design decision (see spec), not an oversight.
- `POST /discard` always acts on the most recent file in `photos/` — no filename parameter by design.
