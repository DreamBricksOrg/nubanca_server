from pathlib import Path

import boto3
from botocore.exceptions import ClientError
from flask import current_app

from .storage import is_allowed_extension

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


def back_cover_key(filename: str) -> str:
    location = current_app.config.get("EVENT_LOCATION") or ""
    if location:
        return f"back-covers/{location}/{filename}"
    return f"back-covers/{filename}"


def upload_file(local_path: Path, key: str) -> None:
    _client().upload_file(str(local_path), _bucket(), key)


def download_file(local_path: Path, key: str) -> None:
    _client().download_file(_bucket(), key, str(local_path))


def is_back_cover_image_key(key: str) -> bool:
    return (
        key.startswith(back_cover_key(""))
        and "\\" not in key
        and not any(part in (".", "..") for part in key.split("/"))
        and not any(ord(char) < 32 for char in key)
        and is_allowed_extension(key)
    )


def list_back_covers() -> list[dict]:
    pages = _client().get_paginator("list_objects_v2").paginate(
        Bucket=_bucket(), Prefix=back_cover_key("")
    )
    objects = [
        obj
        for page in pages
        for obj in page.get("Contents", [])
        if is_back_cover_image_key(obj["Key"])
    ]
    objects.sort(key=lambda obj: (obj["LastModified"], obj["Key"]), reverse=True)
    return [
        {"key": obj["Key"], "filename": obj["Key"].rsplit("/", 1)[-1]}
        for obj in objects
    ]


def list_back_cover_keys(location: str) -> set[str]:
    """List every stored cover for the selected report location."""
    prefix = f"back-covers/{location}/"
    pages = _client().get_paginator("list_objects_v2").paginate(Bucket=_bucket(), Prefix=prefix)
    return {obj["Key"] for page in pages for obj in page.get("Contents", [])}


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
