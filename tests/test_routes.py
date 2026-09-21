import io


def test_get_image_returns_204_when_no_new_capture(client):
    response = client.get("/image")

    assert response.status_code == 204


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
    back_covers = app.config["STORAGE_ROOT"] / "back-covers"
    assert len(list(back_covers.iterdir())) == 1


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
    monkeypatch.setattr(
        "app.routes.printing.print_image",
        lambda path: calls.append(path) or {"printed": False, "message": "stub"},
    )
    data = {
        "image": (io.BytesIO(b"final-image-bytes"), "final.jpg"),
    }

    response = client.post("/print", data=data, content_type="multipart/form-data")

    assert response.status_code == 200
    assert len(calls) == 1
    back_covers = app.config["STORAGE_ROOT"] / "back-covers"
    assert calls[0].parent == back_covers


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
    assert print_response.get_json()["success"] is True

    back_covers = app.config["STORAGE_ROOT"] / "back-covers"
    saved_files = list(back_covers.iterdir())
    assert len(saved_files) == 1
    assert saved_files[0].read_bytes() == b"treated-collage-bytes"
