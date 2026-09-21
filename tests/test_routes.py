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
