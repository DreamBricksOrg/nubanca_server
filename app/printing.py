import logging
import subprocess
from pathlib import Path

from flask import current_app
from PIL import Image

logger = logging.getLogger(__name__)

A4_WIDTH_MM = 210
A4_HEIGHT_MM = 297


class PrintError(Exception):
    """Raised when SumatraPDF fails to print the image."""


def _mm_to_px(mm: float, dpi: int) -> int:
    return round(mm / 25.4 * dpi)


def _load_rgb(path: Path) -> Image.Image:
    img = Image.open(path)
    img.load()
    if img.mode in ("RGBA", "LA") or (img.mode == "P" and "transparency" in img.info):
        rgba = img.convert("RGBA")
        background = Image.new("RGB", rgba.size, "white")
        background.paste(rgba, mask=rgba.split()[-1])
        return background
    return img.convert("RGB")


def compose_a4_canvas(source_path: Path, dest_path: Path, dpi: int, margin_mm: float) -> None:
    """Scale `source_path` to fit inside an A4 canvas with a safety margin and save it to `dest_path`.

    SumatraPDF's own page-fitting (`fit`/`shrink`) scales to whatever "printable
    area" the printer driver reports, which isn't reliable across drivers and can
    end up clipping a full-bleed image against the printer's real, physical
    unprintable border. Pre-rendering onto a known A4 canvas with our own margin
    and printing it 1:1 (`noscale`) removes that guesswork entirely.
    """
    canvas_w = _mm_to_px(A4_WIDTH_MM, dpi)
    canvas_h = _mm_to_px(A4_HEIGHT_MM, dpi)
    margin_px = _mm_to_px(margin_mm, dpi)
    max_w = max(1, canvas_w - 2 * margin_px)
    max_h = max(1, canvas_h - 2 * margin_px)

    image = _load_rgb(source_path)
    scale = min(max_w / image.width, max_h / image.height)
    new_size = (max(1, round(image.width * scale)), max(1, round(image.height * scale)))
    resized = image.resize(new_size, Image.LANCZOS)

    canvas = Image.new("RGB", (canvas_w, canvas_h), "white")
    offset = ((canvas_w - resized.width) // 2, (canvas_h - resized.height) // 2)
    canvas.paste(resized, offset)
    canvas.save(dest_path, dpi=(dpi, dpi))


def print_image(path: Path) -> dict:
    """Print `path` in portrait mode via SumatraPDF.

    The image is first composed onto an A4 canvas at a fixed DPI with a safety
    margin (see `compose_a4_canvas`), then sent to SumatraPDF at 1:1 (`noscale`)
    so the physical printout always matches exactly what was composed.
    """
    config = current_app.config
    if not config.get("PRINT_ENABLED", True):
        logger.info("Impressão desabilitada via PRINT_ENABLED; ignorando: %s", path)
        return {"printed": False, "message": "Impressão desabilitada"}

    sumatra_path = config["SUMATRA_PATH"]
    printer_name = config.get("PRINTER_NAME") or ""
    print_settings = config.get("PRINT_SETTINGS") or "noscale,paper=A4,center"
    timeout = config.get("PRINT_TIMEOUT", 60)
    dpi = config.get("PRINT_DPI", 300)
    margin_mm = config.get("PRINT_MARGIN_MM", 6)

    print_ready_path = path.with_name(f"{path.stem}_a4print{path.suffix}")

    try:
        try:
            compose_a4_canvas(path, print_ready_path, dpi=dpi, margin_mm=margin_mm)
        except Exception as exc:
            raise PrintError(f"Falha ao preparar imagem para impressão: {exc}") from exc

        args = [sumatra_path]
        args += ["-print-to", printer_name] if printer_name else ["-print-to-default"]
        args += ["-print-settings", print_settings, "-silent", "-exit-when-done", str(print_ready_path)]

        try:
            subprocess.run(args, check=True, timeout=timeout, capture_output=True, text=True)
        except FileNotFoundError as exc:
            raise PrintError(f"SumatraPDF não encontrado em '{sumatra_path}'") from exc
        except subprocess.TimeoutExpired as exc:
            raise PrintError(f"Impressão excedeu o tempo limite de {timeout}s") from exc
        except subprocess.CalledProcessError as exc:
            detail = (exc.stderr or exc.stdout or "").strip()
            message = f"SumatraPDF retornou código {exc.returncode}"
            if detail:
                message += f": {detail}"
            raise PrintError(message) from exc
    finally:
        print_ready_path.unlink(missing_ok=True)

    logger.info("Imagem impressa com sucesso via SumatraPDF: %s", path)
    return {"printed": True, "message": "Imagem enviada para impressão"}
