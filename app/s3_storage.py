from pathlib import Path

import boto3
from flask import current_app


def _client():
    return boto3.client(
        "s3",
        region_name=current_app.config["AWS_REGION"],
        aws_access_key_id=current_app.config["AWS_ACCESS_KEY_ID"],
        aws_secret_access_key=current_app.config["AWS_SECRET_ACCESS_KEY"],
    )


def _bucket() -> str:
    return current_app.config["AWS_S3_BUCKET"]


def upload_file(local_path: Path, key: str) -> None:
    _client().upload_file(str(local_path), _bucket(), key)
