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
