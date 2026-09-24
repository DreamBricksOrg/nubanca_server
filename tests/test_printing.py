import subprocess

import pytest

from app.printing import PrintError, print_image


def test_print_image_invokes_sumatra_in_portrait_mode(app, monkeypatch, tmp_path):
    fake_file = tmp_path / "cover.jpg"
    fake_file.write_bytes(b"x")

    calls = []

    def fake_run(args, **kwargs):
        calls.append(args)
        return subprocess.CompletedProcess(args, 0)

    monkeypatch.setattr(subprocess, "run", fake_run)
    app.config["SUMATRA_PATH"] = "SumatraPDF.exe"
    app.config["PRINTER_NAME"] = ""

    with app.app_context():
        result = print_image(fake_file)

    assert result == {"printed": True, "message": "Imagem enviada para impressão"}
    assert len(calls) == 1
    args = calls[0]
    assert args[0] == "SumatraPDF.exe"
    assert "-print-to-default" in args
    assert "-print-settings" in args
    assert args[args.index("-print-settings") + 1] == "fit,portrait,paper=A4"
    assert "portrait" in args[args.index("-print-settings") + 1]
    assert "-silent" in args
    assert "-exit-when-done" in args
    assert args[-1] == str(fake_file)


def test_print_image_uses_configured_printer_name(app, monkeypatch, tmp_path):
    fake_file = tmp_path / "cover.jpg"
    fake_file.write_bytes(b"x")

    calls = []
    monkeypatch.setattr(subprocess, "run", lambda args, **kwargs: calls.append(args) or subprocess.CompletedProcess(args, 0))
    app.config["PRINTER_NAME"] = "Canon SELPHY"

    with app.app_context():
        print_image(fake_file)

    args = calls[0]
    assert "-print-to" in args
    assert args[args.index("-print-to") + 1] == "Canon SELPHY"
    assert "-print-to-default" not in args


def test_print_image_raises_print_error_when_sumatra_is_missing(app, monkeypatch, tmp_path):
    fake_file = tmp_path / "cover.jpg"
    fake_file.write_bytes(b"x")

    def fake_run(args, **kwargs):
        raise FileNotFoundError()

    monkeypatch.setattr(subprocess, "run", fake_run)

    with app.app_context(), pytest.raises(PrintError):
        print_image(fake_file)


def test_print_image_raises_print_error_on_nonzero_exit(app, monkeypatch, tmp_path):
    fake_file = tmp_path / "cover.jpg"
    fake_file.write_bytes(b"x")

    def fake_run(args, **kwargs):
        raise subprocess.CalledProcessError(1, args, output="", stderr="driver not ready")

    monkeypatch.setattr(subprocess, "run", fake_run)

    with app.app_context():
        with pytest.raises(PrintError, match="driver not ready"):
            print_image(fake_file)


def test_print_image_raises_print_error_on_timeout(app, monkeypatch, tmp_path):
    fake_file = tmp_path / "cover.jpg"
    fake_file.write_bytes(b"x")

    def fake_run(args, **kwargs):
        raise subprocess.TimeoutExpired(args, kwargs.get("timeout", 60))

    monkeypatch.setattr(subprocess, "run", fake_run)

    with app.app_context(), pytest.raises(PrintError):
        print_image(fake_file)
