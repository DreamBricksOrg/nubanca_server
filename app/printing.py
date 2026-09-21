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
