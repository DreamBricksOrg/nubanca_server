import logging
import subprocess
from pathlib import Path

from flask import current_app

logger = logging.getLogger(__name__)


class PrintError(Exception):
    """Raised when SumatraPDF fails to print the image."""


def print_image(path: Path) -> dict:
    """Send the original file to SumatraPDF without image treatment or layout overrides."""
    config = current_app.config
    if not config.get("PRINT_ENABLED", True):
        logger.info("Impressão desabilitada via PRINT_ENABLED; ignorando: %s", path)
        return {"printed": False, "message": "Impressão desabilitada"}

    sumatra_path = config["SUMATRA_PATH"]
    printer_name = config.get("PRINTER_NAME") or ""
    timeout = config.get("PRINT_TIMEOUT", 60)

    args = [sumatra_path]
    args += ["-print-to", printer_name] if printer_name else ["-print-to-default"]
    args += ["-silent", "-exit-when-done", str(path)]

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
