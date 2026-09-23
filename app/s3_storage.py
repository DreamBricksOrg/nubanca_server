from pathlib import Path

import boto3
from botocore.exceptions import ClientError
from flask import current_app


S3_MAX_PRESIGNED_EXPIRES = 604800  # S3 SigV4 hard cap: 7 days, in seconds


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


def object_exists(key: str) -> bool:
    try:
        _client().head_object(Bucket=_bucket(), Key=key)
    except ClientError as exc:
        error_code = exc.response.get("Error", {}).get("Code")
        if error_code in ("404", "NoSuchKey"):
            return False
        raise
    return True


def generate_presigned_url(key: str, filename: str, expires_in: int, download: bool = False) -> str:
    expires_in = min(expires_in, S3_MAX_PRESIGNED_EXPIRES)
    params = {"Bucket": _bucket(), "Key": key}
    if download:
        params["ResponseContentDisposition"] = f'attachment; filename="{filename}"'
    return _client().generate_presigned_url("get_object", Params=params, ExpiresIn=expires_in)
