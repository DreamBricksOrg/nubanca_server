# Back-covers via S3 Presigned URL Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Move `back-covers` off local disk storage and onto S3, serving `/view/<filename>` (viewing and downloading) through presigned URLs instead of the local `/files/back-covers/<filename>` route.

**Architecture:** New `app/s3_storage.py` module wraps `boto3` (upload, existence check, presigned URL generation). `POST /print` writes the uploaded image to a temp file (kept for the future PowerShell print step), uploads that temp file to S3 under `back-covers/<filename>`, then deletes the temp file. `GET /view/<filename>` checks existence in S3 (`head_object`) and renders the page with two presigned URLs: one for viewing, one (with `Content-Disposition: attachment`) for downloading. `captures`, `photos`, `discards` are untouched — still local disk, unchanged behavior.

**Tech Stack:** Flask, boto3 (S3 client), moto (S3 mocking in tests), pytest.

See design doc: `docs/superpowers/specs/2026-09-23-s3-backcovers-design.md`

---

### Task 1: AWS config settings

**Files:**
- Modify: `app/config.py`
- Modify: `.env.example`
- Test: `tests/test_config.py` (new file)

- [ ] **Step 1: Write the failing test**

Create `tests/test_config.py`:

```python
from app.config import Config


def test_config_has_s3_settings_with_sane_defaults():
    assert Config.AWS_REGION == "us-east-1"
    assert Config.S3_PRESIGNED_URL_EXPIRES == 86400
    assert hasattr(Config, "AWS_ACCESS_KEY_ID")
    assert hasattr(Config, "AWS_SECRET_ACCESS_KEY")
    assert hasattr(Config, "AWS_S3_BUCKET")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_config.py -v`
Expected: FAIL with `AttributeError: type object 'Config' has no attribute 'AWS_REGION'`

- [ ] **Step 3: Add the settings to `Config`**

In `app/config.py`, add these lines at the end of the `Config` class (after the existing `BASE_URL` line):

```python
    AWS_ACCESS_KEY_ID = os.environ.get("AWS_ACCESS_KEY_ID")
    AWS_SECRET_ACCESS_KEY = os.environ.get("AWS_SECRET_ACCESS_KEY")
    AWS_REGION = os.environ.get("AWS_REGION", "us-east-1")
    AWS_S3_BUCKET = os.environ.get("AWS_S3_BUCKET")
    S3_PRESIGNED_URL_EXPIRES = int(os.environ.get("S3_PRESIGNED_URL_EXPIRES", "86400"))
```

The full file becomes:

```python
import os
from pathlib import Path


class Config:
    STORAGE_ROOT = Path(os.environ.get("STORAGE_ROOT", "storage")).resolve()
    HOST = os.environ.get("HOST", "0.0.0.0")
    PORT = int(os.environ.get("PORT", "5000"))
    BASE_URL = os.environ.get("BASE_URL") or f"http://localhost:{PORT}"

    AWS_ACCESS_KEY_ID = os.environ.get("AWS_ACCESS_KEY_ID")
    AWS_SECRET_ACCESS_KEY = os.environ.get("AWS_SECRET_ACCESS_KEY")
    AWS_REGION = os.environ.get("AWS_REGION", "us-east-1")
    AWS_S3_BUCKET = os.environ.get("AWS_S3_BUCKET")
    S3_PRESIGNED_URL_EXPIRES = int(os.environ.get("S3_PRESIGNED_URL_EXPIRES", "86400"))
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_config.py -v`
Expected: PASS

- [ ] **Step 5: Update `.env.example`**

Replace the contents of `.env.example` with:

```
STORAGE_ROOT=storage
HOST=0.0.0.0
PORT=5000
BASE_URL=http://localhost:5000
AWS_ACCESS_KEY_ID=
AWS_SECRET_ACCESS_KEY=
AWS_REGION=us-east-1
AWS_S3_BUCKET=
S3_PRESIGNED_URL_EXPIRES=86400
```

- [ ] **Step 6: Commit**

```bash
git add app/config.py .env.example tests/test_config.py
git commit -m "feat: add AWS/S3 config settings"
```

---

### Task 2: Add boto3 and moto dependencies

**Files:**
- Modify: `requirements.txt`
- Modify: `requirements-dev.txt`

- [ ] **Step 1: Add boto3 to `requirements.txt`**

Append to `requirements.txt`:

```
boto3==1.35.99
```

Full file:

```
Flask==3.0.3
python-dotenv==1.0.1
flasgger==0.9.7.1
boto3==1.35.99
```

- [ ] **Step 2: Add moto to `requirements-dev.txt`**

Append to `requirements-dev.txt`:

```
moto[s3]==5.2.3
```

Full file:

```
-r requirements.txt
pytest==8.3.3
moto[s3]==5.2.3
```

- [ ] **Step 3: Install**

Run: `./venv/Scripts/python -m pip install -r requirements-dev.txt`
Expected: boto3, botocore and moto install successfully. If either exact pin is unavailable by the time this runs, install the latest available compatible version and update the pin in the requirements file to match what actually got installed.

- [ ] **Step 4: Commit**

```bash
git add requirements.txt requirements-dev.txt
git commit -m "chore: add boto3 and moto dependencies"
```

---

### Task 3: S3 mock test fixture

**Files:**
- Modify: `tests/conftest.py`
- Test: `tests/test_s3_storage.py` (new file)

- [ ] **Step 1: Update `tests/conftest.py`**

Replace the full contents of `tests/conftest.py` with:

```python
import boto3
import pytest
from moto import mock_aws

from app import create_app
from app.config import Config

TEST_S3_BUCKET = "test-bucket"


@pytest.fixture
def app(tmp_path):
    class TestConfig(Config):
        STORAGE_ROOT = tmp_path
        BASE_URL = "http://testserver"
        AWS_ACCESS_KEY_ID = "testing"
        AWS_SECRET_ACCESS_KEY = "testing"
        AWS_REGION = "us-east-1"
        AWS_S3_BUCKET = TEST_S3_BUCKET
        S3_PRESIGNED_URL_EXPIRES = 3600

    with mock_aws():
        s3 = boto3.client("s3", region_name=TestConfig.AWS_REGION)
        s3.create_bucket(Bucket=TEST_S3_BUCKET)

        application = create_app(TestConfig)
        application.config["TESTING"] = True
        yield application


@pytest.fixture
def client(app):
    return app.test_client()
```

- [ ] **Step 2: Write a sanity test**

Create `tests/test_s3_storage.py`:

```python
import boto3


def test_mock_bucket_is_ready(app):
    client = boto3.client("s3", region_name=app.config["AWS_REGION"])

    buckets = {b["Name"] for b in client.list_buckets()["Buckets"]}

    assert app.config["AWS_S3_BUCKET"] in buckets
```

- [ ] **Step 3: Run full suite to confirm nothing broke and the sanity test passes**

Run: `pytest -v`
Expected: All existing tests still PASS (conftest change is backward compatible — it only adds config keys and wraps app creation in `mock_aws()`), and `test_mock_bucket_is_ready` PASSES.

- [ ] **Step 4: Commit**

```bash
git add tests/conftest.py tests/test_s3_storage.py
git commit -m "test: add S3 mock fixture for tests"
```

---

### Task 4: `s3_storage.upload_file`

**Files:**
- Create: `app/s3_storage.py`
- Test: `tests/test_s3_storage.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_s3_storage.py`:

```python
from app import s3_storage


def test_upload_file_puts_object_in_bucket(app, tmp_path):
    local_file = tmp_path / "photo.jpg"
    local_file.write_bytes(b"image-bytes")

    with app.app_context():
        s3_storage.upload_file(local_file, "back-covers/photo.jpg")

    client = boto3.client("s3", region_name=app.config["AWS_REGION"])
    body = client.get_object(Bucket=app.config["AWS_S3_BUCKET"], Key="back-covers/photo.jpg")["Body"].read()
    assert body == b"image-bytes"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_s3_storage.py::test_upload_file_puts_object_in_bucket -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.s3_storage'`

- [ ] **Step 3: Create `app/s3_storage.py`**

```python
from pathlib import Path

import boto3
from botocore.exceptions import ClientError
from flask import current_app


def _client():
    return boto3.client(
        "s3",
        region_name=current_app.config["AWS_REGION"],
        aws_access_key_id=current_app.config["AWS_ACCESS_KEY_ID"],
        aws_secret_access_key=current_app.config["AWS_SECRET_ACCESS_KEY"],
    )


def _bucket() -> str:
    return current_app.config["AWS_S3_BUCKET"]


def upload_file(local_path: Path, key: str) -> None:
    _client().upload_file(str(local_path), _bucket(), key)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_s3_storage.py::test_upload_file_puts_object_in_bucket -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add app/s3_storage.py tests/test_s3_storage.py
git commit -m "feat: add s3_storage.upload_file"
```

---

### Task 5: `s3_storage.object_exists`

**Files:**
- Modify: `app/s3_storage.py`
- Test: `tests/test_s3_storage.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_s3_storage.py`:

```python
def test_object_exists_returns_false_for_missing_key(app):
    with app.app_context():
        assert s3_storage.object_exists("back-covers/missing.jpg") is False


def test_object_exists_returns_true_for_existing_key(app, tmp_path):
    local_file = tmp_path / "photo.jpg"
    local_file.write_bytes(b"x")

    with app.app_context():
        s3_storage.upload_file(local_file, "back-covers/photo.jpg")
        assert s3_storage.object_exists("back-covers/photo.jpg") is True
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_s3_storage.py -k object_exists -v`
Expected: FAIL with `AttributeError: module 'app.s3_storage' has no attribute 'object_exists'`

- [ ] **Step 3: Add `object_exists` to `app/s3_storage.py`**

Append to `app/s3_storage.py`:

```python
def object_exists(key: str) -> bool:
    try:
        _client().head_object(Bucket=_bucket(), Key=key)
    except ClientError as exc:
        error_code = exc.response.get("Error", {}).get("Code")
        if error_code in ("404", "NoSuchKey"):
            return False
        raise
    return True
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_s3_storage.py -k object_exists -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add app/s3_storage.py tests/test_s3_storage.py
git commit -m "feat: add s3_storage.object_exists"
```

---

### Task 6: `s3_storage.generate_presigned_url`

**Files:**
- Modify: `app/s3_storage.py`
- Test: `tests/test_s3_storage.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_s3_storage.py`:

```python
def test_generate_presigned_url_points_to_the_key(app, tmp_path):
    local_file = tmp_path / "photo.jpg"
    local_file.write_bytes(b"x")

    with app.app_context():
        s3_storage.upload_file(local_file, "back-covers/photo.jpg")
        url = s3_storage.generate_presigned_url("back-covers/photo.jpg", "photo.jpg", 3600)

    assert "back-covers/photo.jpg" in url
    assert app.config["AWS_S3_BUCKET"] in url


def test_generate_presigned_url_with_download_forces_attachment(app, tmp_path):
    local_file = tmp_path / "photo.jpg"
    local_file.write_bytes(b"x")

    with app.app_context():
        s3_storage.upload_file(local_file, "back-covers/photo.jpg")
        url = s3_storage.generate_presigned_url("back-covers/photo.jpg", "photo.jpg", 3600, download=True)

    assert "response-content-disposition=attachment" in url


def test_generate_presigned_url_without_download_has_no_content_disposition(app, tmp_path):
    local_file = tmp_path / "photo.jpg"
    local_file.write_bytes(b"x")

    with app.app_context():
        s3_storage.upload_file(local_file, "back-covers/photo.jpg")
        url = s3_storage.generate_presigned_url("back-covers/photo.jpg", "photo.jpg", 3600)

    assert "response-content-disposition" not in url
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_s3_storage.py -k generate_presigned_url -v`
Expected: FAIL with `AttributeError: module 'app.s3_storage' has no attribute 'generate_presigned_url'`

- [ ] **Step 3: Add `generate_presigned_url` to `app/s3_storage.py`**

Append to `app/s3_storage.py`:

```python
def generate_presigned_url(key: str, filename: str, expires_in: int, download: bool = False) -> str:
    params = {"Bucket": _bucket(), "Key": key}
    if download:
        params["ResponseContentDisposition"] = f'attachment; filename="{filename}"'
    return _client().generate_presigned_url("get_object", Params=params, ExpiresIn=expires_in)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_s3_storage.py -k generate_presigned_url -v`
Expected: PASS

- [ ] **Step 5: Run the whole `s3_storage` test file**

Run: `pytest tests/test_s3_storage.py -v`
Expected: All PASS (7 tests: mock bucket sanity + upload + 2x object_exists + 3x generate_presigned_url)

- [ ] **Step 6: Commit**

```bash
git add app/s3_storage.py tests/test_s3_storage.py
git commit -m "feat: add s3_storage.generate_presigned_url"
```

---

### Task 7: `storage.build_unique_filename`

**Files:**
- Modify: `app/storage.py`
- Test: `tests/test_storage.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_storage.py`:

```python
import re

from app.storage import build_unique_filename


def test_build_unique_filename_matches_expected_shape():
    name = build_unique_filename(".jpg")

    assert re.match(r"^\d{8}_\d{6}_[0-9a-f]{8}\.jpg$", name)


def test_build_unique_filename_generates_different_names_each_call():
    first = build_unique_filename(".jpg")
    second = build_unique_filename(".jpg")

    assert first != second
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_storage.py -k build_unique_filename -v`
Expected: FAIL with `ImportError: cannot import name 'build_unique_filename' from 'app.storage'`

- [ ] **Step 3: Add `build_unique_filename` to `app/storage.py`**

Add `import uuid` to the imports at the top of `app/storage.py` (alongside the existing `import shutil` / `from datetime import datetime` / `from pathlib import Path`), then append this function near `build_timestamped_filename`:

```python
def build_unique_filename(ext: str) -> str:
    ext = ext.lower()
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    suffix = uuid.uuid4().hex[:8]
    return f"{timestamp}_{suffix}{ext}"
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_storage.py -k build_unique_filename -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add app/storage.py tests/test_storage.py
git commit -m "feat: add storage.build_unique_filename"
```

---

### Task 8: `storage.save_uploaded_image_to_tempfile`

**Files:**
- Modify: `app/storage.py`
- Test: `tests/test_storage.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_storage.py`:

```python
from app.storage import save_uploaded_image_to_tempfile


def test_save_uploaded_image_to_tempfile_raises_for_missing_file():
    try:
        save_uploaded_image_to_tempfile(None)
        assert False, "expected ValueError"
    except ValueError:
        pass


def test_save_uploaded_image_to_tempfile_raises_for_disallowed_extension():
    upload = FileStorage(stream=io.BytesIO(b"x"), filename="final.gif")

    try:
        save_uploaded_image_to_tempfile(upload)
        assert False, "expected ValueError"
    except ValueError:
        pass


def test_save_uploaded_image_to_tempfile_writes_content_and_returns_path():
    upload = FileStorage(stream=io.BytesIO(b"binary-image-data"), filename="final.jpg")

    temp_path = save_uploaded_image_to_tempfile(upload)

    try:
        assert temp_path.exists()
        assert temp_path.suffix == ".jpg"
        assert temp_path.read_bytes() == b"binary-image-data"
    finally:
        temp_path.unlink(missing_ok=True)
```

(`io` and `FileStorage` are already imported near the bottom of `tests/test_storage.py` for the existing `save_uploaded_image` tests — no new imports needed.)

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_storage.py -k save_uploaded_image_to_tempfile -v`
Expected: FAIL with `ImportError: cannot import name 'save_uploaded_image_to_tempfile' from 'app.storage'`

- [ ] **Step 3: Add `save_uploaded_image_to_tempfile` to `app/storage.py`**

Add `import os` and `import tempfile` to the imports at the top of `app/storage.py`, then append this function after `save_uploaded_image`:

```python
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_storage.py -k save_uploaded_image_to_tempfile -v`
Expected: PASS

- [ ] **Step 5: Run the whole storage test file**

Run: `pytest tests/test_storage.py -v`
Expected: All PASS

- [ ] **Step 6: Commit**

```bash
git add app/storage.py tests/test_storage.py
git commit -m "feat: add storage.save_uploaded_image_to_tempfile"
```

---

### Task 9: Remove `back-covers` from `storage.FOLDERS`

**Files:**
- Modify: `app/storage.py`
- Test: `tests/test_storage.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_storage.py`:

```python
def test_folders_no_longer_includes_back_covers():
    assert "back-covers" not in FOLDERS
    assert FOLDERS == ("captures", "photos", "discards")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_storage.py -k folders_no_longer_includes_back_covers -v`
Expected: FAIL — `FOLDERS` currently includes `"back-covers"`

- [ ] **Step 3: Update `FOLDERS` in `app/storage.py`**

Change:

```python
FOLDERS = ("captures", "photos", "discards", "back-covers")
```

to:

```python
FOLDERS = ("captures", "photos", "discards")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_storage.py -k folders_no_longer_includes_back_covers -v`
Expected: PASS

- [ ] **Step 5: Run the whole storage test file**

Run: `pytest tests/test_storage.py -v`
Expected: All PASS (`test_ensure_folders_creates_all_expected_subfolders` iterates `FOLDERS` dynamically, so it still passes with 3 folders instead of 4)

- [ ] **Step 6: Commit**

```bash
git add app/storage.py tests/test_storage.py
git commit -m "feat: remove back-covers from local storage folders"
```

---

### Task 10: Rewire `POST /print` to upload to S3

**Files:**
- Modify: `app/routes.py`
- Modify: `tests/test_routes.py`

- [ ] **Step 1: Update the failing/outdated tests first**

In `tests/test_routes.py`, add `import boto3` at the top of the file (alongside `import io`), then replace these three tests:

Replace `test_post_print_saves_file_and_returns_success`:

```python
def test_post_print_saves_file_and_returns_success(client, app):
    data = {
        "image": (io.BytesIO(b"final-image-bytes"), "final.jpg"),
    }

    response = client.post("/print", data=data, content_type="multipart/form-data")

    assert response.status_code == 200
    body = response.get_json()
    assert body["success"] is True

    filename = body["page_url"].rsplit("/", 1)[-1]
    s3 = boto3.client("s3", region_name=app.config["AWS_REGION"])
    obj = s3.get_object(Bucket=app.config["AWS_S3_BUCKET"], Key=f"back-covers/{filename}")
    assert obj["Body"].read() == b"final-image-bytes"
    assert body["page_url"] == f"http://testserver/view/{filename}"
```

Replace `test_post_print_calls_print_image`:

```python
def test_post_print_calls_print_image(client, app, monkeypatch):
    calls = []

    def fake_print_image(path):
        calls.append((path, path.exists()))
        return {"printed": False, "message": "stub"}

    monkeypatch.setattr("app.routes.printing.print_image", fake_print_image)
    data = {
        "image": (io.BytesIO(b"final-image-bytes"), "final.jpg"),
    }

    response = client.post("/print", data=data, content_type="multipart/form-data")

    assert response.status_code == 200
    assert len(calls) == 1
    path, existed_during_call = calls[0]
    assert existed_during_call is True
    assert path.suffix == ".jpg"
    assert not path.exists()
```

Replace `test_full_capture_to_print_flow`:

```python
def test_full_capture_to_print_flow(client, app):
    captures = app.config["STORAGE_ROOT"] / "captures"
    (captures / "DSC0001.jpg").write_bytes(b"raw-capture-bytes")

    image_response = client.get("/image")
    assert image_response.status_code == 200
    image_url = image_response.get_json()["image_url"]
    served_path = image_url[len("http://testserver"):]

    served_response = client.get(served_path)
    assert served_response.status_code == 200
    assert served_response.data == b"raw-capture-bytes"

    print_response = client.post(
        "/print",
        data={"image": (io.BytesIO(b"treated-collage-bytes"), "collage.jpg")},
        content_type="multipart/form-data",
    )
    assert print_response.status_code == 200
    body = print_response.get_json()
    assert body["success"] is True

    filename = body["page_url"].rsplit("/", 1)[-1]
    s3 = boto3.client("s3", region_name=app.config["AWS_REGION"])
    obj = s3.get_object(Bucket=app.config["AWS_S3_BUCKET"], Key=f"back-covers/{filename}")
    assert obj["Body"].read() == b"treated-collage-bytes"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_routes.py -k "post_print or full_capture_to_print_flow" -v`
Expected: FAIL — current `/print` still writes to `storage/back-covers/` on disk, not S3, so `s3.get_object` raises `NoSuchKey` / `botocore.exceptions.ClientError`.

- [ ] **Step 3: Rewire `POST /print` in `app/routes.py`**

Change the top import line from:

```python
from . import printing, storage
```

to:

```python
from . import printing, s3_storage, storage
```

Replace the body of `print_image_route` (keep the existing docstring above `"""` unchanged) with:

```python
    file_storage = request.files.get("image")

    try:
        temp_path = storage.save_uploaded_image_to_tempfile(file_storage)
    except ValueError as exc:
        return jsonify({"success": False, "message": str(exc)}), 400

    try:
        printing.print_image(temp_path)
        filename = storage.build_unique_filename(temp_path.suffix)
        s3_storage.upload_file(temp_path, f"back-covers/{filename}")
    finally:
        temp_path.unlink(missing_ok=True)

    base_url = current_app.config["BASE_URL"].rstrip("/")
    return jsonify({
        "success": True,
        "message": "Imagem salva em back-covers; impressão ainda não implementada (stub)",
        "page_url": f"{base_url}/view/{filename}",
    })
```

Note this drops the `root = current_app.config["STORAGE_ROOT"]` line that used to be the first line of the function body — it's no longer used here.

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_routes.py -k "post_print or full_capture_to_print_flow" -v`
Expected: PASS

- [ ] **Step 5: Run the whole routes test file**

Run: `pytest tests/test_routes.py -v`
Expected: `test_post_print_rejects_disallowed_extension`, `test_post_print_rejects_missing_file`, `test_post_print_rejects_empty_filename` still PASS unchanged. `test_view_photo_renders_page_for_existing_back_cover` and `test_view_photo_returns_404_for_unknown_file` are expected to FAIL at this point — they're fixed in Task 11.

- [ ] **Step 6: Commit**

```bash
git add app/routes.py tests/test_routes.py
git commit -m "feat: upload back-covers to S3 in POST /print"
```

---

### Task 11: Rewire `GET /view/<filename>` to use S3 presigned URLs

**Files:**
- Modify: `app/routes.py`
- Modify: `app/templates/view.html`
- Modify: `tests/test_routes.py`

- [ ] **Step 1: Update the failing/outdated test first**

In `tests/test_routes.py`, replace `test_view_photo_renders_page_for_existing_back_cover`:

```python
def test_view_photo_renders_page_for_existing_back_cover(client, app):
    s3 = boto3.client("s3", region_name=app.config["AWS_REGION"])
    s3.put_object(
        Bucket=app.config["AWS_S3_BUCKET"],
        Key="back-covers/20260922_143201.jpg",
        Body=b"final-bytes",
    )

    response = client.get("/view/20260922_143201.jpg")

    assert response.status_code == 200
    assert response.content_type.startswith("text/html")
    body = response.get_data(as_text=True)
    assert "back-covers/20260922_143201.jpg" in body
    assert "share-btn" in body
    assert "download-btn" in body
```

`test_view_photo_returns_404_for_unknown_file` stays as-is (it already just checks for a 404 on an unknown filename — no S3 setup needed since the key won't exist in the mock bucket either).

- [ ] **Step 2: Run tests to verify the renders test fails**

Run: `pytest tests/test_routes.py -k view_photo -v`
Expected: `test_view_photo_renders_page_for_existing_back_cover` FAILS (current code checks `storage.list_image_files` on local disk, finds nothing, returns 404 instead of 200). `test_view_photo_returns_404_for_unknown_file` still PASSES (it was already returning 404, just for a different reason).

- [ ] **Step 3: Rewire `view_photo` in `app/routes.py`**

Replace the body of `view_photo` (keep the docstring) with:

```python
    key = f"back-covers/{filename}"
    if not s3_storage.object_exists(key):
        abort(404)

    expires_in = current_app.config["S3_PRESIGNED_URL_EXPIRES"]
    image_url = s3_storage.generate_presigned_url(key, filename, expires_in)
    download_url = s3_storage.generate_presigned_url(key, filename, expires_in, download=True)
    return render_template("view.html", filename=filename, image_url=image_url, download_url=download_url)
```

Remove `url_for` from the `flask` import line at the top of the file (it's no longer used anywhere in `routes.py`). The import line becomes:

```python
from flask import Blueprint, abort, current_app, jsonify, render_template, request, send_from_directory
```

- [ ] **Step 4: Update `app/templates/view.html`**

Change the download button line from:

```html
        <a id="download-btn" class="btn btn-secondary" href="{{ image_url }}" download="{{ filename }}">Download</a>
```

to:

```html
        <a id="download-btn" class="btn btn-secondary" href="{{ download_url }}">Download</a>
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest tests/test_routes.py -k view_photo -v`
Expected: PASS

- [ ] **Step 6: Run the whole routes test file**

Run: `pytest tests/test_routes.py -v`
Expected: All PASS except the two `serve_file`-related tests touched in Task 12 (`test_serve_file_returns_404_for_disallowed_folder` should still pass; there's no back-covers-specific serve_file test yet — that's added next).

- [ ] **Step 7: Commit**

```bash
git add app/routes.py app/templates/view.html tests/test_routes.py
git commit -m "feat: serve /view via S3 presigned URLs"
```

---

### Task 12: Confirm `/files/back-covers/<filename>` no longer serves anything

**Files:**
- Modify: `app/routes.py` (docstring only)
- Modify: `tests/test_routes.py`

- [ ] **Step 1: Write the new test**

Append to `tests/test_routes.py`:

```python
def test_serve_file_returns_404_for_back_covers_folder(client, app):
    s3 = boto3.client("s3", region_name=app.config["AWS_REGION"])
    s3.put_object(
        Bucket=app.config["AWS_S3_BUCKET"],
        Key="back-covers/20260922_143201.jpg",
        Body=b"x",
    )

    response = client.get("/files/back-covers/20260922_143201.jpg")

    assert response.status_code == 404
```

- [ ] **Step 2: Run test to verify it already passes**

Run: `pytest tests/test_routes.py::test_serve_file_returns_404_for_back_covers_folder -v`
Expected: PASS already — `storage.FOLDERS` no longer contains `"back-covers"` (Task 9), so the existing `if folder not in storage.FOLDERS: abort(404)` check in `serve_file` already covers this. This step is a regression-proofing test, not new production code.

- [ ] **Step 3: Update the `serve_file` swagger docstring in `app/routes.py`**

In the `enum` list under the `folder` parameter of `serve_file`'s docstring, change:

```yaml
        enum: [captures, photos, discards, back-covers]
```

to:

```yaml
        enum: [captures, photos, discards]
```

- [ ] **Step 4: Run the whole routes test file**

Run: `pytest tests/test_routes.py -v`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add app/routes.py tests/test_routes.py
git commit -m "test: confirm /files no longer serves back-covers"
```

---

### Task 13: Update README

**Files:**
- Modify: `README.md`

- [ ] **Step 1: Update the folder diagram**

Change:

```
storage/
├── captures/     # fotos cruas da câmera (entrada)
├── photos/       # fotos promovidas, aguardando tratamento no tablet
├── discards/     # fotos descartadas
└── back-covers/  # imagens finais tratadas, prontas para impressão
```

to:

```
storage/
├── captures/     # fotos cruas da câmera (entrada)
├── photos/       # fotos promovidas, aguardando tratamento no tablet
└── discards/     # fotos descartadas
```

And in the paragraph right above it, change:

```
3. O tablet pode descartar a foto (`POST /discard`) ou tratá-la (colagem) e enviar o resultado final (`POST /print`), que salva a imagem em `storage/back-covers/` e aciona a impressão.
```

to:

```
3. O tablet pode descartar a foto (`POST /discard`) ou tratá-la (colagem) e enviar o resultado final (`POST /print`), que envia a imagem para o bucket S3 (prefixo `back-covers/`) e aciona a impressão.
```

- [ ] **Step 2: Update the env vars section**

Change:

```
Copie `.env.example` para `.env` e ajuste se necessário:

```
STORAGE_ROOT=storage       # pasta raiz onde captures/photos/discards/back-covers são criadas
HOST=0.0.0.0
PORT=5000
BASE_URL=http://localhost:5000   # usado para montar as URLs retornadas por /image
```

As 4 subpastas de `STORAGE_ROOT` são criadas automaticamente ao iniciar o servidor, se não existirem.
```

to:

```
Copie `.env.example` para `.env` e ajuste se necessário:

```
STORAGE_ROOT=storage       # pasta raiz onde captures/photos/discards são criadas
HOST=0.0.0.0
PORT=5000
BASE_URL=http://localhost:5000   # usado para montar as URLs retornadas por /image
AWS_ACCESS_KEY_ID=               # credenciais AWS usadas para enviar back-covers ao S3
AWS_SECRET_ACCESS_KEY=
AWS_REGION=us-east-1
AWS_S3_BUCKET=                   # bucket onde back-covers/<arquivo> é salvo
S3_PRESIGNED_URL_EXPIRES=86400   # validade (segundos) das URLs presigned usadas em /view
```

As 3 subpastas de `STORAGE_ROOT` são criadas automaticamente ao iniciar o servidor, se não existirem. `back-covers` não é mais uma pasta local — as imagens finais vão direto para o S3.
```

- [ ] **Step 3: Update the `POST /print` section**

Change:

```
Recebe a imagem final tratada (colagem feita pelo tablet) como upload `multipart/form-data`, salva em `back-covers/` e aciona a impressão.
```

to:

```
Recebe a imagem final tratada (colagem feita pelo tablet) como upload `multipart/form-data`, envia para o bucket S3 (prefixo `back-covers/`) e aciona a impressão.
```

- [ ] **Step 4: Update the `GET /view/<filename>` section**

Change:

```
Página HTML (não JSON) para o cliente final ver a foto impressa no celular, com botões de **Compartilhar** (via `navigator.share` do navegador) e **Download**. `<filename>` é o nome do arquivo em `back-covers/` (normalmente obtido do `page_url` retornado por `POST /print`).

Mostra uma splashscreen com a animação do logo (roxo/branco, seguindo o brand guideline da Nubank) enquanto a página e a foto carregam, evitando qualquer flash de conteúdo sem estilo.

| Status | Quando |
|---|---|
| `200` | Retorna a página HTML. |
| `404` | Não existe arquivo com esse nome em `back-covers/`. |
```

to:

```
Página HTML (não JSON) para o cliente final ver a foto impressa no celular, com botões de **Compartilhar** (via `navigator.share` do navegador) e **Download**. `<filename>` é o nome do objeto salvo no S3 sob o prefixo `back-covers/` (normalmente obtido do `page_url` retornado por `POST /print`). A imagem em si é servida via presigned URL do S3 — a página faz um `head_object` no S3 para confirmar que o arquivo existe antes de renderizar.

Mostra uma splashscreen com a animação do logo (roxo/branco, seguindo o brand guideline da Nubank) enquanto a página e a foto carregam, evitando qualquer flash de conteúdo sem estilo.

| Status | Quando |
|---|---|
| `200` | Retorna a página HTML. |
| `404` | Não existe objeto com essa chave em `back-covers/` no S3. |
```

- [ ] **Step 5: Update the `GET /files/<folder>/<filename>` section**

Change:

```
Serve um arquivo salvo em uma das 4 pastas de armazenamento. `<folder>` deve ser exatamente `captures`, `photos`, `discards` ou `back-covers` — qualquer outro valor retorna `404`.
```

to:

```
Serve um arquivo salvo em uma das 3 pastas de armazenamento local. `<folder>` deve ser exatamente `captures`, `photos` ou `discards` — qualquer outro valor (incluindo `back-covers`, que agora vive no S3, não em disco) retorna `404`.
```

- [ ] **Step 6: Commit**

```bash
git add README.md
git commit -m "docs: document S3-backed back-covers"
```

---

### Task 14: Full suite verification

**Files:** none (verification only)

- [ ] **Step 1: Run the full test suite**

Run: `pytest -v`
Expected: All tests PASS.

- [ ] **Step 2: Manually sanity-check `.env.example` against `app/config.py`**

Confirm every `Config` attribute added in Task 1 has a matching line in `.env.example` (already true from Task 1, this is just a final read-through).

- [ ] **Step 3: If everything passes, this plan is complete.**

No commit needed for this task — it's verification only.
