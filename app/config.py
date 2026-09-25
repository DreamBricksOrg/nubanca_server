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

    PRINT_ENABLED = os.environ.get("PRINT_ENABLED", "true").strip().lower() not in ("false", "0", "")
    SUMATRA_PATH = os.environ.get("SUMATRA_PATH", "SumatraPDF.exe")
    PRINTER_NAME = os.environ.get("PRINTER_NAME", "")
    PRINT_SETTINGS = os.environ.get("PRINT_SETTINGS", "noscale,paper=A4,center")
    PRINT_TIMEOUT = int(os.environ.get("PRINT_TIMEOUT", "60"))
    PRINT_DPI = int(os.environ.get("PRINT_DPI", "300"))
    PRINT_MARGIN_MM = float(os.environ.get("PRINT_MARGIN_MM", "6"))

    IMAGEMAGICK_ENABLED = os.environ.get("IMAGEMAGICK_ENABLED", "true").strip().lower() not in ("false", "0", "")
    IMAGEMAGICK_PATH = os.environ.get("IMAGEMAGICK_PATH", "magick")
    IMAGEMAGICK_ARGS = os.environ.get("IMAGEMAGICK_ARGS", "")
    IMAGEMAGICK_TIMEOUT = int(os.environ.get("IMAGEMAGICK_TIMEOUT", "60"))


    TIMEOUT_QRCODE = os.environ.get("TIMEOUT_QRCODE", "30")
    TIMER_POOLING = os.environ.get("TIMER_POOLING", "5")