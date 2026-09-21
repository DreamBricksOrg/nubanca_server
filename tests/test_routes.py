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
