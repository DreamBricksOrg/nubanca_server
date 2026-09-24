def test_unmatched_route_returns_branded_404_page(client):
    response = client.get("/this-route-does-not-exist")

    assert response.status_code == 404
    assert response.content_type.startswith("text/html")
    body = response.get_data(as_text=True)
    assert "Ops!" in body


def test_view_photo_missing_file_returns_branded_404_page(client):
    response = client.get("/view/does-not-exist.jpg")

    assert response.status_code == 404
    assert response.content_type.startswith("text/html")
    body = response.get_data(as_text=True)
    assert "Ops!" in body


def test_get_image_404_stays_json_not_html(client):
    response = client.get("/image")

    assert response.status_code == 404
    assert response.content_type.startswith("application/json")
    assert response.get_json() == {
        "success": False,
        "message": "Nenhuma imagem nova disponível",
    }


def test_post_discard_404_stays_json_not_html(client):
    response = client.post("/discard")

    assert response.status_code == 404
    assert response.content_type.startswith("application/json")
    assert response.get_json() == {
        "success": False,
        "message": "Nenhuma foto para descartar",
    }
