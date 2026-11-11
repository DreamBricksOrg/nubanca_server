"""Export a privacy-minimized LogCenter snapshot for the static report.

Run with the project's Python interpreter: python scripts/export_report.py
The generated dist/report/ directory is intended for upload to a static origin.
"""

import argparse
import hashlib
import hmac
import json
import os
import secrets
import shutil
from datetime import datetime, timezone
from pathlib import Path

import boto3
from bson import ObjectId
from dotenv import load_dotenv
from pymongo import MongoClient

EVENTS = (
    "imprimir_imagem_sucesso", "apenas_qrcode_gerado", "reimprimir_imagem_sucesso",
    "visualizar_foto_acessada", "compartilhar_imagem", "baixar_imagem",
)
LOCATIONS = ("sp", "rj")
ROOT = Path(__file__).resolve().parents[1]


def _utc_timestamp(value):
    try:
        value = datetime.fromisoformat(value.replace("Z", "+00:00")) if isinstance(value, str) else value
        if not isinstance(value, datetime):
            return None
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
    except ValueError:
        return None


def list_existing_cover_keys(s3, bucket):
    """Read all generated-cover keys, including later S3 listing pages."""
    keys = set()
    for location in LOCATIONS:
        prefix = f"back-covers/{location}/"
        for page in s3.get_paginator("list_objects_v2").paginate(Bucket=bucket, Prefix=prefix):
            keys.update(item["Key"] for item in page.get("Contents", []))
    return keys


def export_events(collection, output, project_id, existing_keys, *, hash_key=None):
    """Read only report events; never export IPs, filenames or Mongo identifiers."""
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    hash_key = hash_key if hash_key is not None else secrets.token_bytes(32)
    query = {"project_id": project_id, "data.event_location": {"$in": LOCATIONS},
             "message": {"$in": EVENTS}}
    projection = {"_id": 0, "timestamp": 1, "message": 1, "data.event_location": 1,
                  "data.file": 1, "data.filename": 1}
    temp = output.with_name(output.name + ".partial")
    count = 0
    try:
        with temp.open("w", encoding="utf-8", newline="\n") as stream:
            for source in collection.find(query, projection):
                data = source.get("data")
                if not isinstance(data, dict):
                    continue
                message = source.get("message")
                location = data.get("event_location")
                timestamp = _utc_timestamp(source.get("timestamp"))
                if message not in EVENTS or location not in LOCATIONS or timestamp is None:
                    continue
                photo = (data.get("filename") if message == "visualizar_foto_acessada"
                         else data.get("file") if message in EVENTS[:2] else None)
                token = (hmac.new(hash_key, f"{location}\0{photo}".encode("utf-8"), hashlib.sha256).hexdigest()
                         if isinstance(photo, str) and photo else None)
                removed = (f"back-covers/{location}/{photo}" not in existing_keys
                           if message in EVENTS[:2] and token else None)
                row = {"timestamp": timestamp, "message": message, "location": location,
                       "photo_id": token, "removed": removed}
                stream.write(json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n")
                count += 1
        temp.replace(output)
    finally:
        temp.unlink(missing_ok=True)
    return count


def build_bundle(destination):
    """Copy the self-contained static dashboard alongside the exported JSONL."""
    destination = Path(destination)
    sources = {
        "index.html": ROOT / "static-report" / "index.html",
        "js/report.js": ROOT / "static-report" / "report.js",
        "css/reports.css": ROOT / "app" / "static" / "css" / "reports.css",
        "img/logo-white.png": ROOT / "app" / "static" / "img" / "logo-white.png",
        "fonts/NuSansText-Regular.ttf": ROOT / "app" / "static" / "fonts" / "NuSansText-Regular.ttf",
        "fonts/NuSansText-Bold.ttf": ROOT / "app" / "static" / "fonts" / "NuSansText-Bold.ttf",
    }
    for name, source in sources.items():
        target = destination / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)


def main():
    parser = argparse.ArgumentParser(description="Export sanitized LogCenter logs and a static report bundle")
    parser.add_argument("--output-dir", type=Path, default=ROOT / "dist" / "report")
    args = parser.parse_args()
    load_dotenv(ROOT / ".env", override=True)
    url = os.environ.get("LOGCENTER_MONGOURL")
    project = os.environ.get("LOGCENTER_PROJECT_ID")
    if not url or not project:
        parser.error("LOGCENTER_MONGOURL and LOGCENTER_PROJECT_ID must be configured")
    if not ObjectId.is_valid(project):
        parser.error("LOGCENTER_PROJECT_ID is not a valid MongoDB ObjectId")
    bucket = os.environ.get("AWS_S3_BUCKET")
    if not bucket:
        parser.error("AWS_S3_BUCKET is required to check removed files")
    try:
        s3 = boto3.client("s3", region_name=os.environ.get("AWS_REGION", "us-east-1"),
                          aws_access_key_id=os.environ.get("AWS_ACCESS_KEY_ID") or None,
                          aws_secret_access_key=os.environ.get("AWS_SECRET_ACCESS_KEY") or None)
        existing_keys = list_existing_cover_keys(s3, bucket)
        client = MongoClient(url, serverSelectionTimeoutMS=4000,
                             connectTimeoutMS=4000, socketTimeoutMS=5000)
        try:
            database = os.environ.get("LOGCENTER_MONGO_DB", "logcenter_prod")
            db = client[database] if database else client.get_default_database()
            collection = os.environ.get("LOGCENTER_MONGO_COLLECTION", "logs")
            count = export_events(db[collection], args.output_dir / "logs.jsonl", ObjectId(project), existing_keys)
        finally:
            client.close()
    except Exception as exc:
        parser.error(f"export failed ({type(exc).__name__}); verify MongoDB access and output directory")
    build_bundle(args.output_dir)
    print(f"Exported {count} sanitized events to {args.output_dir.resolve()}")


if __name__ == "__main__":
    main()
