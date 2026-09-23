import os
from pathlib import Path


class Config:
    STORAGE_ROOT = Path(os.environ.get("STORAGE_ROOT", "storage")).resolve()
    HOST = os.environ.get("HOST", "0.0.0.0")
    PORT = int(os.environ.get("PORT", "5000"))
    BASE_URL = os.environ.get("BASE_URL") or f"http://localhost:{PORT}"

    AWS_ACCESS_KEY_ID = os.environ.get("AWS_ACCESS_KEY_ID")
    AWS_SECRET_ACCESS_KEY = os.environ.get("AWS_SECRET_ACCESS_KEY")
    AWS_REGION = os.environ.get("AWS_REGION", "us-east-1")
    AWS_S3_BUCKET = os.environ.get("AWS_S3_BUCKET")
    S3_PRESIGNED_URL_EXPIRES = int(os.environ.get("S3_PRESIGNED_URL_EXPIRES", "86400"))
    EVENT_LOCATION = os.environ.get("EVENT_LOCATION", "")
