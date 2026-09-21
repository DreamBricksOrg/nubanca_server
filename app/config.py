import os
from pathlib import Path


class Config:
    STORAGE_ROOT = Path(os.environ.get("STORAGE_ROOT", "storage")).resolve()
    HOST = os.environ.get("HOST", "0.0.0.0")
    PORT = int(os.environ.get("PORT", "5000"))
    BASE_URL = os.environ.get("BASE_URL") or f"http://localhost:{PORT}"
