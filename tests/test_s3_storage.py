import boto3


def test_mock_bucket_is_ready(app):
    client = boto3.client("s3", region_name=app.config["AWS_REGION"])

    buckets = {b["Name"] for b in client.list_buckets()["Buckets"]}

    assert app.config["AWS_S3_BUCKET"] in buckets


from app import s3_storage


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
