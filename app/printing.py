import logging
import subprocess
from pathlib import Path

from flask import current_app

logger = logging.getLogger(__name__)


class PrintError(Exception):
    """Raised when SumatraPDF fails to print the image."""


def print_image(path: Path) -> dict:
    """Print `path` in portrait mode via SumatraPDF.

    SumatraPDF opens .jpg/.png files like single-page documents, so the same
    command-line printing flags used for PDFs apply to images.
    """
    config = current_app.config
    sumatra_path = config["SUMATRA_PATH"]
    printer_name = config.get("PRINTER_NAME") or ""
    print_settings = config.get("PRINT_SETTINGS") or "fit,portrait"
    timeout = config.get("PRINT_TIMEOUT", 60)

    args = [sumatra_path]
    args += ["-print-to", printer_name] if printer_name else ["-print-to-default"]
    args += ["-print-settings", print_settings, "-silent", "-exit-when-done", str(path)]

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

    logger.info("Imagem impressa com sucesso via SumatraPDF: %s", path)
    return {"printed": True, "message": "Imagem enviada para impressão"}
