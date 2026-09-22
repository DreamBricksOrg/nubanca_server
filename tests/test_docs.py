def test_docs_ui_is_served(client):
    response = client.get("/docs/")

    assert response.status_code == 200
    assert b"swagger" in response.data.lower()


def test_openapi_spec_lists_all_endpoints(client):
    response = client.get("/apispec.json")

    assert response.status_code == 200
    spec = response.get_json()
    assert spec["info"]["title"] == "Photo Print API"
    paths = set(spec["paths"].keys())
    assert paths == {
        "/image",
        "/discard",
        "/print",
        "/view/{filename}",
        "/files/{folder}/{filename}",
    }
