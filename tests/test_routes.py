import io

import boto3

from app import imagemagick


def test_get_image_returns_404_when_no_new_capture(client):
    response = client.get("/image")

    assert response.status_code == 404
    assert response.get_json() == {
        "success": False,
        "message": "Nenhuma imagem nova disponível",
    }


def test_get_image_promotes_capture_and_returns_url(client, app):
    captures = app.config["STORAGE_ROOT"] / "captures"
    (captures / "DSC0001.jpg").write_bytes(b"x")

    response = client.get("/image")

    assert response.status_code == 200
    data = response.get_json()
    assert data["image_url"].startswith("http://testserver/files/photos/")
    assert data["image_url"].endswith(".jpg")
    assert not (captures / "DSC0001.jpg").exists()
    photos = app.config["STORAGE_ROOT"] / "photos"
    assert len(list(photos.iterdir())) == 1


def test_post_discard_returns_404_when_no_photo(client):
    response = client.post("/discard")

    assert response.status_code == 404
    assert response.get_json() == {
        "success": False,
        "message": "Nenhuma foto para descartar",
    }


def test_post_discard_moves_latest_photo(client, app):
    photos = app.config["STORAGE_ROOT"] / "photos"
    (photos / "20260921_143201.jpg").write_bytes(b"x")

    response = client.post("/discard")

    assert response.status_code == 200
    assert response.get_json() == {"success": True, "message": "Foto descartada"}
    discards = app.config["STORAGE_ROOT"] / "discards"
    assert (discards / "20260921_143201.jpg").exists()


def test_post_print_saves_file_and_returns_success(client, app):
    data = {
        "image": (io.BytesIO(b"final-image-bytes"), "final.jpg"),
    }

    response = client.post("/print", data=data, content_type="multipart/form-data")

    assert response.status_code == 200
    body = response.get_json()
    assert body["success"] is True

    filename = body["page_url"].rsplit("/", 1)[-1]
    s3 = boto3.client("s3", region_name=app.config["AWS_REGION"])
    obj = s3.get_object(Bucket=app.config["AWS_S3_BUCKET"], Key=f"back-covers/{filename}")
    assert obj["Body"].read() == b"final-image-bytes"
    assert body["page_url"] == f"http://testserver/view/{filename}"


def test_post_print_rejects_disallowed_extension(client):
    data = {
        "image": (io.BytesIO(b"x"), "final.gif"),
    }

    response = client.post("/print", data=data, content_type="multipart/form-data")

    assert response.status_code == 400
    assert response.get_json()["success"] is False


def test_post_print_rejects_missing_file(client):
    response = client.post("/print", data={}, content_type="multipart/form-data")

    assert response.status_code == 400
    assert response.get_json()["success"] is False


def test_post_print_rejects_empty_filename(client):
    data = {
        "image": (io.BytesIO(b"x"), ""),
    }

    response = client.post("/print", data=data, content_type="multipart/form-data")

    assert response.status_code == 400
    assert response.get_json()["success"] is False


def test_post_print_calls_print_image(client, app, monkeypatch):
    calls = []

    def fake_print_image(path):
        calls.append((path, path.exists()))
        return {"printed": False, "message": "stub"}

    monkeypatch.setattr("app.routes.printing.print_image", fake_print_image)
    data = {
        "image": (io.BytesIO(b"final-image-bytes"), "final.jpg"),
    }

    response = client.post("/print", data=data, content_type="multipart/form-data")

    assert response.status_code == 200
    assert len(calls) == 1
    path, existed_during_call = calls[0]
    assert existed_during_call is True
    assert path.suffix == ".jpg"
    assert not path.exists()


def test_serve_file_returns_file_from_allowed_folder(client, app):
    photos = app.config["STORAGE_ROOT"] / "photos"
    (photos / "20260921_143201.jpg").write_bytes(b"image-bytes")

    response = client.get("/files/photos/20260921_143201.jpg")

    assert response.status_code == 200
    assert response.data == b"image-bytes"


def test_serve_file_returns_404_for_disallowed_folder(client):
    response = client.get("/files/secrets/anything.jpg")

    assert response.status_code == 404


def test_full_capture_to_print_flow(client, app):
    captures = app.config["STORAGE_ROOT"] / "captures"
    (captures / "DSC0001.jpg").write_bytes(b"raw-capture-bytes")

    image_response = client.get("/image")
    assert image_response.status_code == 200
    image_url = image_response.get_json()["image_url"]
    served_path = image_url[len("http://testserver"):]

    served_response = client.get(served_path)
    assert served_response.status_code == 200
    assert served_response.data == b"raw-capture-bytes"

    print_response = client.post(
        "/print",
        data={"image": (io.BytesIO(b"treated-collage-bytes"), "collage.jpg")},
        content_type="multipart/form-data",
    )
    assert print_response.status_code == 200
    body = print_response.get_json()
    assert body["success"] is True

    filename = body["page_url"].rsplit("/", 1)[-1]
    s3 = boto3.client("s3", region_name=app.config["AWS_REGION"])
    obj = s3.get_object(Bucket=app.config["AWS_S3_BUCKET"], Key=f"back-covers/{filename}")
    assert obj["Body"].read() == b"treated-collage-bytes"


def test_view_photo_renders_page_for_existing_back_cover(client, app):
    s3 = boto3.client("s3", region_name=app.config["AWS_REGION"])
    s3.put_object(
        Bucket=app.config["AWS_S3_BUCKET"],
        Key="back-covers/20260922_143201.jpg",
        Body=b"final-bytes",
    )

    response = client.get("/view/20260922_143201.jpg")

    assert response.status_code == 200
    assert response.content_type.startswith("text/html")
    body = response.get_data(as_text=True)
    assert "back-covers/20260922_143201.jpg" in body
    assert "share-btn" in body
    assert "download-btn" in body

    import re
    img_src_match = re.search(r'id="photo"[^>]*\bsrc="([^"]+)"', body)
    download_href_match = re.search(r'id="download-btn"[^>]*\bhref="([^"]+)"', body)
    assert img_src_match and download_href_match
    assert img_src_match.group(1) != download_href_match.group(1)
    assert "response-content-disposition" in download_href_match.group(1)


def test_view_photo_returns_404_for_unknown_file(client):
    response = client.get("/view/does-not-exist.jpg")

    assert response.status_code == 404


def test_serve_file_returns_404_for_back_covers_folder(client, app):
    s3 = boto3.client("s3", region_name=app.config["AWS_REGION"])
    s3.put_object(
        Bucket=app.config["AWS_S3_BUCKET"],
        Key="back-covers/20260922_143201.jpg",
        Body=b"x",
    )

    response = client.get("/files/back-covers/20260922_143201.jpg")

    assert response.status_code == 404


def test_post_print_uses_event_location_prefix_when_configured(client, app, monkeypatch):
    monkeypatch.setitem(app.config, "EVENT_LOCATION", "sp")
    data = {
        "image": (io.BytesIO(b"final-image-bytes"), "final.jpg"),
    }

    response = client.post("/print", data=data, content_type="multipart/form-data")

    assert response.status_code == 200
    body = response.get_json()
    filename = body["page_url"].rsplit("/", 1)[-1]
    s3 = boto3.client("s3", region_name=app.config["AWS_REGION"])
    obj = s3.get_object(Bucket=app.config["AWS_S3_BUCKET"], Key=f"back-covers/sp/{filename}")
    assert obj["Body"].read() == b"final-image-bytes"


def test_view_photo_uses_event_location_prefix_when_configured(client, app, monkeypatch):
    monkeypatch.setitem(app.config, "EVENT_LOCATION", "rj")
    s3 = boto3.client("s3", region_name=app.config["AWS_REGION"])
    s3.put_object(
        Bucket=app.config["AWS_S3_BUCKET"],
        Key="back-covers/rj/20260922_143201.jpg",
        Body=b"final-bytes",
    )

    response = client.get("/view/20260922_143201.jpg")

    assert response.status_code == 200
    body = response.get_data(as_text=True)
    assert "back-covers/rj/20260922_143201.jpg" in body


def test_get_image_calls_imagemagick_treatment_and_survives_failure(client, app, monkeypatch):
    captures = app.config["STORAGE_ROOT"] / "captures"
    (captures / "DSC0001.jpg").write_bytes(b"x")

    calls = []

    def fake_apply_treatment(path):
        calls.append(path)
        raise imagemagick.TreatmentError("boom")

    app.config["IMAGEMAGICK_ENABLED"] = True
    monkeypatch.setattr("app.routes.imagemagick.apply_treatment", fake_apply_treatment)

    response = client.get("/image")

    assert response.status_code == 200
    assert len(calls) == 1
    assert calls[0].name == "DSC0001.jpg" or calls[0].exists()
    data = response.get_json()
    assert data["image_url"].startswith("http://testserver/files/photos/")
