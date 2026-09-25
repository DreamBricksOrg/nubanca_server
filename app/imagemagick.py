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
