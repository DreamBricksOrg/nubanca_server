# ImageMagick Treatment Hook in /image — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Wire a configurable ImageMagick command into the `/image` capture flow so the tool is fully integrated (config, execution, error handling, tests) even though the actual treatment (`IMAGEMAGICK_ARGS`) is left empty/no-op for now.

**Architecture:** A new `app/imagemagick.py` module (mirroring `app/printing.py`) exposes `apply_treatment(path)`, which runs `magick <path> [extra-args] <path>` via `subprocess.run`, reading all settings from `current_app.config`. `app/routes.py:get_image()` calls it right after `storage.promote_latest_capture` and swallows failures (log + continue), the same way `POST /print` already handles `PrintError`.

**Tech Stack:** Flask, Python `subprocess`, `shlex`, pytest + `monkeypatch` (existing project conventions).

Spec: `docs/superpowers/specs/2026-09-25-imagemagick-treatment-design.md`

---

### Task 1: Config settings for ImageMagick

**Files:**
- Modify: `app/config.py`
- Modify: `.env.example`
- Test: `tests/test_config.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_config.py`:

```python
def test_config_has_imagemagick_settings_with_sane_defaults():
    assert Config.IMAGEMAGICK_ENABLED is True
    assert Config.IMAGEMAGICK_PATH == "magick"
    assert Config.IMAGEMAGICK_ARGS == ""
    assert Config.IMAGEMAGICK_TIMEOUT == 60
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_config.py -v`
Expected: FAIL with `AttributeError: type object 'Config' has no attribute 'IMAGEMAGICK_ENABLED'`

- [ ] **Step 3: Implement the config settings**

In `app/config.py`, add after the existing `PRINT_MARGIN_MM` line:

```python
    IMAGEMAGICK_ENABLED = os.environ.get("IMAGEMAGICK_ENABLED", "true").strip().lower() not in ("false", "0", "")
    IMAGEMAGICK_PATH = os.environ.get("IMAGEMAGICK_PATH", "magick")
    IMAGEMAGICK_ARGS = os.environ.get("IMAGEMAGICK_ARGS", "")
    IMAGEMAGICK_TIMEOUT = int(os.environ.get("IMAGEMAGICK_TIMEOUT", "60"))
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_config.py -v`
Expected: PASS (all tests in the file)

- [ ] **Step 5: Update `.env.example`**

In `.env.example`, add after the existing `PRINT_MARGIN_MM=6` line:

```
IMAGEMAGICK_ENABLED=true
IMAGEMAGICK_PATH=magick
IMAGEMAGICK_ARGS=
IMAGEMAGICK_TIMEOUT=60
```

- [ ] **Step 6: Commit**

```bash
git add app/config.py .env.example tests/test_config.py
git commit -m "feat: add ImageMagick config settings"
```

---

### Task 2: `app/imagemagick.py` module

**Files:**
- Create: `app/imagemagick.py`
- Test: `tests/test_imagemagick.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_imagemagick.py`:

```python
import subprocess
from pathlib import Path

import pytest
from PIL import Image

from app.imagemagick import TreatmentError, apply_treatment


def _make_image(path, size=(600, 900), color="red"):
    Image.new("RGB", size, color).save(path)
    return path


def test_apply_treatment_runs_magick_in_place_with_no_extra_args(app, monkeypatch, tmp_path):
    photo = _make_image(tmp_path / "photo.jpg")

    calls = []
    monkeypatch.setattr(subprocess, "run", lambda args, **kwargs: calls.append((args, kwargs)) or subprocess.CompletedProcess(args, 0))
    app.config["IMAGEMAGICK_ENABLED"] = True
    app.config["IMAGEMAGICK_PATH"] = "magick"
    app.config["IMAGEMAGICK_ARGS"] = ""

    with app.app_context():
        result = apply_treatment(photo)

    assert result == {"treated": True, "message": "Imagem tratada com sucesso"}
    assert len(calls) == 1
    args, kwargs = calls[0]
    assert args == ["magick", str(photo), str(photo)]
    assert kwargs["check"] is True
    assert kwargs["timeout"] == 60


def test_apply_treatment_includes_extra_args_when_configured(app, monkeypatch, tmp_path):
    photo = _make_image(tmp_path / "photo.jpg")

    calls = []
    monkeypatch.setattr(subprocess, "run", lambda args, **kwargs: calls.append(args) or subprocess.CompletedProcess(args, 0))
    app.config["IMAGEMAGICK_ENABLED"] = True
    app.config["IMAGEMAGICK_ARGS"] = "-auto-orient -strip"

    with app.app_context():
        apply_treatment(photo)

    args = calls[0]
    assert args == ["magick", str(photo), "-auto-orient", "-strip", str(photo)]


def test_apply_treatment_skips_when_disabled(app, monkeypatch, tmp_path):
    photo = _make_image(tmp_path / "photo.jpg")

    calls = []
    monkeypatch.setattr(subprocess, "run", lambda args, **kwargs: calls.append(args) or subprocess.CompletedProcess(args, 0))
    app.config["IMAGEMAGICK_ENABLED"] = False

    with app.app_context():
        result = apply_treatment(photo)

    assert result == {"treated": False, "message": "Tratamento desabilitado"}
    assert calls == []


def test_apply_treatment_raises_treatment_error_when_magick_missing(app, monkeypatch, tmp_path):
    photo = _make_image(tmp_path / "photo.jpg")

    def fake_run(args, **kwargs):
        raise FileNotFoundError()

    monkeypatch.setattr(subprocess, "run", fake_run)
    app.config["IMAGEMAGICK_ENABLED"] = True

    with app.app_context(), pytest.raises(TreatmentError, match="não encontrado"):
        apply_treatment(photo)


def test_apply_treatment_raises_treatment_error_on_nonzero_exit(app, monkeypatch, tmp_path):
    photo = _make_image(tmp_path / "photo.jpg")

    def fake_run(args, **kwargs):
        raise subprocess.CalledProcessError(1, args, output="", stderr="unable to open image")

    monkeypatch.setattr(subprocess, "run", fake_run)
    app.config["IMAGEMAGICK_ENABLED"] = True

    with app.app_context():
        with pytest.raises(TreatmentError, match="unable to open image"):
            apply_treatment(photo)


def test_apply_treatment_raises_treatment_error_on_timeout(app, monkeypatch, tmp_path):
    photo = _make_image(tmp_path / "photo.jpg")

    def fake_run(args, **kwargs):
        raise subprocess.TimeoutExpired(args, kwargs.get("timeout", 60))

    monkeypatch.setattr(subprocess, "run", fake_run)
    app.config["IMAGEMAGICK_ENABLED"] = True

    with app.app_context(), pytest.raises(TreatmentError):
        apply_treatment(photo)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_imagemagick.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.imagemagick'`

- [ ] **Step 3: Implement `app/imagemagick.py`**

```python
import logging
import shlex
import subprocess
from pathlib import Path

from flask import current_app

logger = logging.getLogger(__name__)


class TreatmentError(Exception):
    """Raised when the ImageMagick treatment command fails."""


def apply_treatment(path: Path) -> dict:
    """Run the configured ImageMagick command over `path`, in place.

    With `IMAGEMAGICK_ARGS` empty, this is a plain `magick <path> <path>` —
    a real decode/encode round-trip that proves the integration works
    without changing the image, until a concrete treatment is configured.
    """
    config = current_app.config
    if not config.get("IMAGEMAGICK_ENABLED", True):
        logger.info("Tratamento ImageMagick desabilitado via IMAGEMAGICK_ENABLED; ignorando: %s", path)
        return {"treated": False, "message": "Tratamento desabilitado"}

    magick_path = config["IMAGEMAGICK_PATH"]
    extra_args = shlex.split(config.get("IMAGEMAGICK_ARGS") or "")
    timeout = config.get("IMAGEMAGICK_TIMEOUT", 60)

    args = [magick_path, str(path), *extra_args, str(path)]

    try:
        subprocess.run(args, check=True, timeout=timeout, capture_output=True, text=True)
    except FileNotFoundError as exc:
        raise TreatmentError(f"ImageMagick não encontrado em '{magick_path}'") from exc
    except subprocess.TimeoutExpired as exc:
        raise TreatmentError(f"Tratamento excedeu o tempo limite de {timeout}s") from exc
    except subprocess.CalledProcessError as exc:
        detail = (exc.stderr or exc.stdout or "").strip()
        message = f"ImageMagick retornou código {exc.returncode}"
        if detail:
            message += f": {detail}"
        raise TreatmentError(message) from exc

    logger.info("Imagem tratada com sucesso via ImageMagick: %s", path)
    return {"treated": True, "message": "Imagem tratada com sucesso"}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_imagemagick.py -v`
Expected: PASS (all 6 tests)

- [ ] **Step 5: Commit**

```bash
git add app/imagemagick.py tests/test_imagemagick.py
git commit -m "feat: add ImageMagick treatment module"
```

---

### Task 3: Wire treatment into GET /image

**Files:**
- Modify: `app/routes.py:1` (import) and `app/routes.py:8-42` (`get_image`)
- Modify: `tests/conftest.py`
- Test: `tests/test_routes.py`

- [ ] **Step 1: Disable ImageMagick by default in the test app config**

In `tests/conftest.py`, add a line to `TestConfig` (after `S3_PRESIGNED_URL_EXPIRES = 3600`):

```python
        IMAGEMAGICK_ENABLED = False
```

This keeps existing `/image` tests (which write fake, non-image bytes as `.jpg` files) from trying to run a real `magick` binary. Tests that need the treatment active opt back in per-test via `app.config["IMAGEMAGICK_ENABLED"] = True`.

- [ ] **Step 2: Write the failing test**

Append to `tests/test_routes.py`:

```python
def test_get_image_calls_imagemagick_treatment_and_survives_failure(client, app, monkeypatch):
    captures = app.config["STORAGE_ROOT"] / "captures"
    (captures / "DSC0001.jpg").write_bytes(b"x")

    calls = []

    def fake_apply_treatment(path):
        calls.append(path)
        raise imagemagick.TreatmentError("boom")

    app.config["IMAGEMAGICK_ENABLED"] = True
    monkeypatch.setattr("app.routes.imagemagick.apply_treatment", fake_apply_treatment)

    response = client.get("/image")

    assert response.status_code == 200
    assert len(calls) == 1
    assert calls[0].name == "DSC0001.jpg" or calls[0].exists()
    data = response.get_json()
    assert data["image_url"].startswith("http://testserver/files/photos/")
```

Add the needed import at the top of `tests/test_routes.py`:

```python
from app import imagemagick
```

- [ ] **Step 3: Run test to verify it fails**

Run: `python -m pytest tests/test_routes.py::test_get_image_calls_imagemagick_treatment_and_survives_failure -v`
Expected: FAIL with `AttributeError: <module 'app.routes' ...> does not have the attribute 'imagemagick'` (routes.py doesn't import or call it yet)

- [ ] **Step 4: Wire `imagemagick.apply_treatment` into `get_image`**

In `app/routes.py`, change the import line (currently line 3):

```python
from . import imagemagick, printing, s3_storage, storage
```

Then in `get_image()` (currently lines 35-38), insert the treatment call between promoting the capture and building the URL:

```python
    root = current_app.config["STORAGE_ROOT"]
    dest = storage.promote_latest_capture(root / "captures", root / "photos")
    if dest is None:
        return jsonify({"success": False, "message": "Nenhuma imagem nova disponível"}), 404

    try:
        imagemagick.apply_treatment(dest)
    except imagemagick.TreatmentError as exc:
        current_app.logger.error("Falha ao tratar imagem %s: %s", dest, exc)

    base_url = current_app.config["BASE_URL"].rstrip("/")
    image_url = f"{base_url}/files/photos/{dest.name}"
    return jsonify({"image_url": image_url})
```

- [ ] **Step 5: Run test to verify it passes**

Run: `python -m pytest tests/test_routes.py::test_get_image_calls_imagemagick_treatment_and_survives_failure -v`
Expected: PASS

- [ ] **Step 6: Run the full test suite to check for regressions**

Run: `python -m pytest -q`
Expected: All tests pass (existing `/image` tests still pass because `IMAGEMAGICK_ENABLED` defaults to `False` in `TestConfig`)

- [ ] **Step 7: Commit**

```bash
git add app/routes.py tests/conftest.py tests/test_routes.py
git commit -m "feat: run ImageMagick treatment after promoting a capture"
```

---

## Self-Review Notes

- **Spec coverage:** hook point (Task 3), no-op default command (Task 2 Step 3 docstring + Step 1 test asserting `["magick", path, path]`), config knobs (Task 1), fail-soft error handling (Task 3 Step 2/4 test + implementation), test plan (Tasks 1-3 tests) — all covered.
- **Placeholder scan:** no TBD/TODO; every step has literal code and exact commands.
- **Type consistency:** `apply_treatment(path: Path) -> dict` and `TreatmentError` names match across Task 2 and Task 3 usage (`imagemagick.apply_treatment`, `imagemagick.TreatmentError`).
