import re
import time
from datetime import datetime, timezone

import boto3
from botocore.stub import Stubber


def test_mock_bucket_is_ready(app):
    client = boto3.client("s3", region_name=app.config["AWS_REGION"])

    buckets = {b["Name"] for b in client.list_buckets()["Buckets"]}

    assert app.config["AWS_S3_BUCKET"] in buckets


from app import s3_storage


def test_back_cover_key_without_event_location(app):
    with app.app_context():
        assert s3_storage.back_cover_key("photo.jpg") == "back-covers/photo.jpg"


def test_back_cover_key_with_event_location(app, monkeypatch):
    monkeypatch.setitem(app.config, "EVENT_LOCATION", "sp")
    with app.app_context():
        assert s3_storage.back_cover_key("photo.jpg") == "back-covers/sp/photo.jpg"


def test_upload_file_puts_object_in_bucket(app, tmp_path):
    local_file = tmp_path / "photo.jpg"
    local_file.write_bytes(b"image-bytes")

    with app.app_context():
        s3_storage.upload_file(local_file, "back-covers/photo.jpg")

    client = boto3.client("s3", region_name=app.config["AWS_REGION"])
    body = client.get_object(Bucket=app.config["AWS_S3_BUCKET"], Key="back-covers/photo.jpg")["Body"].read()
    assert body == b"image-bytes"


def test_object_exists_returns_false_for_missing_key(app):
    with app.app_context():
        assert s3_storage.object_exists("back-covers/missing.jpg") is False


def test_object_exists_returns_true_for_existing_key(app, tmp_path):
    local_file = tmp_path / "photo.jpg"
    local_file.write_bytes(b"x")

    with app.app_context():
        s3_storage.upload_file(local_file, "back-covers/photo.jpg")
        assert s3_storage.object_exists("back-covers/photo.jpg") is True


def test_generate_presigned_url_points_to_the_key(app, tmp_path):
    local_file = tmp_path / "photo.jpg"
    local_file.write_bytes(b"x")

    with app.app_context():
        s3_storage.upload_file(local_file, "back-covers/photo.jpg")
        url = s3_storage.generate_presigned_url("back-covers/photo.jpg", "photo.jpg", 3600)

    assert "back-covers/photo.jpg" in url
    assert app.config["AWS_S3_BUCKET"] in url


def test_generate_presigned_url_with_download_forces_attachment(app, tmp_path):
    local_file = tmp_path / "photo.jpg"
    local_file.write_bytes(b"x")

    with app.app_context():
        s3_storage.upload_file(local_file, "back-covers/photo.jpg")
        url = s3_storage.generate_presigned_url("back-covers/photo.jpg", "photo.jpg", 3600, download=True)

    assert "response-content-disposition=attachment" in url


def test_generate_presigned_url_without_download_has_no_content_disposition(app, tmp_path):
    local_file = tmp_path / "photo.jpg"
    local_file.write_bytes(b"x")

    with app.app_context():
        s3_storage.upload_file(local_file, "back-covers/photo.jpg")
        url = s3_storage.generate_presigned_url("back-covers/photo.jpg", "photo.jpg", 3600)

    assert "response-content-disposition" not in url


def _expires_param(url: str) -> int:
    # This environment's boto3 client signs S3 presigned URLs with SigV2
    # (region us-east-1), which encodes expiry as an absolute Unix
    # timestamp in an `Expires` query param, not SigV4's `X-Amz-Expires`
    # duration param. Either way, the value must reflect the (clamped)
    # expires_in added to "now".
    match = re.search(r"[?&]Expires=(\d+)", url)
    assert match, f"no Expires param in {url!r}"
    return int(match.group(1))


def test_generate_presigned_url_clamps_expires_in_to_s3_max(app, tmp_path):
    local_file = tmp_path / "photo.jpg"
    local_file.write_bytes(b"x")

    with app.app_context():
        s3_storage.upload_file(local_file, "back-covers/photo.jpg")
        before = int(time.time())
        url_over_max = s3_storage.generate_presigned_url("back-covers/photo.jpg", "photo.jpg", 999999999)
        url_at_max = s3_storage.generate_presigned_url("back-covers/photo.jpg", "photo.jpg", 604800)
        after = int(time.time())

    # Both an over-the-cap request and an at-the-cap request must expire
    # at "now + S3's 7-day (604800s) SigV4 hard cap", not further out.
    assert before + 604800 <= _expires_param(url_over_max) <= after + 604800
    assert before + 604800 <= _expires_param(url_at_max) <= after + 604800


def test_list_back_covers_reads_every_s3_page_and_sorts_newest_first(app, monkeypatch):
    client = boto3.client("s3", region_name=app.config["AWS_REGION"])
    app.config["EVENT_LOCATION"] = ""
    bucket = app.config["AWS_S3_BUCKET"]
    with Stubber(client) as stubber:
        stubber.add_response("list_objects_v2", {
            "IsTruncated": True,
            "Contents": [
                {"Key": "back-covers/old.jpg", "LastModified": datetime(2026, 1, 1, tzinfo=timezone.utc)},
                {"Key": "back-covers/ignored.txt", "LastModified": datetime(2026, 1, 4, tzinfo=timezone.utc)},
            ],
            "NextContinuationToken": "next-page",
        }, {"Bucket": bucket, "Prefix": "back-covers/"})
        stubber.add_response("list_objects_v2", {
            "IsTruncated": False,
            "Contents": [
                {"Key": "back-covers/new.jpg", "LastModified": datetime(2026, 1, 3, tzinfo=timezone.utc)},
                {"Key": "back-covers/middle.png", "LastModified": datetime(2026, 1, 2, tzinfo=timezone.utc)},
            ],
        }, {"Bucket": bucket, "Prefix": "back-covers/", "ContinuationToken": "next-page"})
        monkeypatch.setattr(s3_storage, "_client", lambda: client)

        with app.app_context():
            photos = s3_storage.list_back_covers()

        assert [photo["filename"] for photo in photos] == ["new.jpg", "middle.png", "old.jpg"]
        assert [photo["key"] for photo in photos] == [
            "back-covers/new.jpg", "back-covers/middle.png", "back-covers/old.jpg"
        ]
        stubber.assert_no_pending_responses()
