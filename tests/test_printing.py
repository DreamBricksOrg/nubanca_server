import subprocess
from pathlib import Path

import pytest
from PIL import Image

from app.printing import A4_HEIGHT_MM, A4_WIDTH_MM, PrintError, compose_a4_canvas, print_image


def _make_image(path, size=(600, 900), mode="RGB", color="red"):
    Image.new(mode, size, color).save(path)
    return path


def test_compose_a4_canvas_fits_image_within_margin(tmp_path):
    source = _make_image(tmp_path / "source.jpg", size=(600, 900))
    dest = tmp_path / "out.png"

    compose_a4_canvas(source, dest, dpi=150, margin_mm=6)

    with Image.open(dest) as canvas:
        expected_w = round(A4_WIDTH_MM / 25.4 * 150)
        expected_h = round(A4_HEIGHT_MM / 25.4 * 150)
        assert canvas.size == (expected_w, expected_h)
        assert canvas.mode == "RGB"

        margin_px = round(6 / 25.4 * 150)
        # the safety margin band must stay pure white - nothing gets pasted over it
        assert canvas.getpixel((margin_px // 2, canvas.height // 2)) == (255, 255, 255)
        assert canvas.getpixel((canvas.width // 2, margin_px // 2)) == (255, 255, 255)


def test_compose_a4_canvas_flattens_transparent_png_onto_white(tmp_path):
    source = tmp_path / "source.png"
    Image.new("RGBA", (400, 400), (255, 0, 0, 0)).save(source)  # fully transparent
    dest = tmp_path / "out.png"

    compose_a4_canvas(source, dest, dpi=150, margin_mm=6)

    with Image.open(dest) as canvas:
        assert canvas.mode == "RGB"
        # fully transparent source composited onto white must stay all white
        assert canvas.getpixel((canvas.width // 2, canvas.height // 2)) == (255, 255, 255)


def test_print_image_composes_onto_a4_canvas_and_prints_with_noscale(app, monkeypatch, tmp_path):
    source = _make_image(tmp_path / "cover.jpg")

    calls = []

    def fake_run(args, **kwargs):
        calls.append(args)
        return subprocess.CompletedProcess(args, 0)

    monkeypatch.setattr(subprocess, "run", fake_run)
    app.config["SUMATRA_PATH"] = "SumatraPDF.exe"
    app.config["PRINTER_NAME"] = ""

    with app.app_context():
        result = print_image(source)

    assert result == {"printed": True, "message": "Imagem enviada para impressão"}
    assert len(calls) == 1
    args = calls[0]
    assert args[0] == "SumatraPDF.exe"
    assert "-print-to-default" in args
    assert args[args.index("-print-settings") + 1] == "noscale,paper=A4,center"
    assert "-silent" in args
    assert "-exit-when-done" in args

    printed_path = Path(args[-1])
    assert printed_path != source
    assert not printed_path.exists()  # composed print-only file is cleaned up after printing


def test_print_image_uses_configured_printer_name(app, monkeypatch, tmp_path):
    source = _make_image(tmp_path / "cover.jpg")

    calls = []
    monkeypatch.setattr(subprocess, "run", lambda args, **kwargs: calls.append(args) or subprocess.CompletedProcess(args, 0))
    app.config["PRINTER_NAME"] = "Canon SELPHY"

    with app.app_context():
        print_image(source)

    args = calls[0]
    assert "-print-to" in args
    assert args[args.index("-print-to") + 1] == "Canon SELPHY"
    assert "-print-to-default" not in args


def test_print_image_raises_print_error_when_sumatra_is_missing(app, monkeypatch, tmp_path):
    source = _make_image(tmp_path / "cover.jpg")

    def fake_run(args, **kwargs):
        raise FileNotFoundError()

    monkeypatch.setattr(subprocess, "run", fake_run)

    with app.app_context(), pytest.raises(PrintError):
        print_image(source)


def test_print_image_raises_print_error_on_nonzero_exit(app, monkeypatch, tmp_path):
    source = _make_image(tmp_path / "cover.jpg")

    def fake_run(args, **kwargs):
        raise subprocess.CalledProcessError(1, args, output="", stderr="driver not ready")

    monkeypatch.setattr(subprocess, "run", fake_run)

    with app.app_context():
        with pytest.raises(PrintError, match="driver not ready"):
            print_image(source)


def test_print_image_raises_print_error_on_timeout(app, monkeypatch, tmp_path):
    source = _make_image(tmp_path / "cover.jpg")

    def fake_run(args, **kwargs):
        raise subprocess.TimeoutExpired(args, kwargs.get("timeout", 60))

    monkeypatch.setattr(subprocess, "run", fake_run)

    with app.app_context(), pytest.raises(PrintError):
        print_image(source)


def test_print_image_cleans_up_composed_file_even_on_failure(app, monkeypatch, tmp_path):
    source = _make_image(tmp_path / "cover.jpg")

    def fake_run(args, **kwargs):
        raise subprocess.CalledProcessError(1, args, output="", stderr="offline")

    monkeypatch.setattr(subprocess, "run", fake_run)

    with app.app_context():
        with pytest.raises(PrintError):
            print_image(source)

    leftovers = list(tmp_path.glob("*_a4print*"))
    assert leftovers == []
