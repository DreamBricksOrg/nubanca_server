import logging
import re
import subprocess
from pathlib import Path

import boto3
import pytest
from botocore.exceptions import ClientError, EndpointConnectionError

from app.printing import PrintError, print_image as send_to_printer


@pytest.fixture(autouse=True)
def isolate_gallery_side_effects(app, monkeypatch):
    app.extensions["logcenter"] = None
    app.extensions["logcenterv3"] = None

    def unexpected_print(path):
        raise AssertionError("A impressão deve ser substituída explicitamente no teste")

    monkeypatch.setattr("app.routes.printing.print_image", unexpected_print)


def put_photo(app, key, body=b"photo-bytes"):
    s3 = boto3.client("s3", region_name=app.config["AWS_REGION"])
    s3.put_object(Bucket=app.config["AWS_S3_BUCKET"], Key=key, Body=body)
    return s3


def test_gallery_lists_configured_folder_with_print_button_under_each_photo(client, app):
    app.config["EVENT_LOCATION"] = "sp"
    put_photo(app, "back-covers/sp/first.jpg")
    put_photo(app, "back-covers/sp/subfolder/second.PNG")
    put_photo(app, "back-covers/rj/other.jpg")
    put_photo(app, "back-covers/spy/not-this-folder.jpg")
    put_photo(app, "back-covers/sp/notes.txt")
    put_photo(app, "back-covers/sp/")
    put_photo(app, "photos/not-a-back-cover.jpg")

    response = client.get("/photos")

    assert response.status_code == 200
    html = response.get_data(as_text=True)
    cards = re.findall(r'<article class="photo-card">(.*?)</article>', html, re.S)
    assert len(cards) == 2
    for card in cards:
        assert card.index("<img") < card.index("<button")
        assert ">Imprimir</button>" in card
        assert 'loading="lazy"' in card
        assert 'data-key="back-covers/sp/' in card
    assert "first.jpg" in html
    assert "second.PNG" in html
    assert "other.jpg" not in html
    assert "not-this-folder.jpg" not in html
    assert "notes.txt" not in html
    assert "not-a-back-cover.jpg" not in html
    assert 'data-print-url="/photos/print"' in html
    assert "s3.amazonaws.com" in html


def test_print_stored_photo_downloads_original_and_uses_configured_printer(client, app, monkeypatch, caplog):
    app.config["EVENT_LOCATION"] = "sp"
    app.config["PRINT_ENABLED"] = True
    app.config["SUMATRA_PATH"] = "test-sumatra.exe"
    app.config["PRINTER_NAME"] = "Test printer"
    key = "back-covers/sp/subfolder/photo with spaces.png"
    s3 = put_photo(app, key, b"original-s3-image")
    calls = []
    caplog.set_level(logging.INFO)

    def fake_run(args, **kwargs):
        local_path = Path(args[-1])
        calls.append((args, local_path))
        assert local_path.read_bytes() == b"original-s3-image"
        return subprocess.CompletedProcess(args, 0)

    monkeypatch.setattr("app.routes.printing.print_image", send_to_printer)
    monkeypatch.setattr("app.printing.subprocess.run", fake_run)

    response = client.post("/photos/print", json={"key": key})

    assert response.status_code == 200
    assert response.get_json() == {
        "success": True,
        "printed": True,
        "message": "Imagem enviada para impressão",
    }
    assert len(calls) == 1
    args, local_path = calls[0]
    assert args[:3] == ["test-sumatra.exe", "-print-to", "Test printer"]
    assert not local_path.exists()
    assert not local_path.parent.exists()
    objects = s3.list_objects_v2(Bucket=app.config["AWS_S3_BUCKET"])["Contents"]
    assert [obj["Key"] for obj in objects] == [key]
    assert "reimprimir_imagem_sucesso" in caplog.messages


@pytest.mark.parametrize("payload", [
    None, [], {}, {"key": None}, {"key": 123}, {"key": ""},
    {"key": "back-covers/rj/other.jpg"},
    {"key": "back-covers/spy/other.jpg"},
    {"key": "back-covers/sp/../other.jpg"},
    {"key": "back-covers/sp/photo\\other.jpg"},
    {"key": "back-covers/sp/notes.txt"},
])
def test_print_rejects_invalid_or_out_of_scope_keys_before_download(client, app, monkeypatch, payload):
    app.config["EVENT_LOCATION"] = "sp"

    def unexpected_download(*args):
        raise AssertionError("Chave inválida não deve acessar o S3")

    monkeypatch.setattr("app.routes.s3_storage.download_file", unexpected_download)
    response = client.post("/photos/print", json=payload)

    assert response.status_code == 400
    assert response.get_json()["success"] is False


def test_print_is_post_only(client):
    assert client.get("/photos/print").status_code == 405


def test_missing_photo_returns_json_404_without_printing(client, app):
    app.config["PRINT_ENABLED"] = True
    response = client.post("/photos/print", json={"key": "back-covers/missing.jpg"})

    assert response.status_code == 404
    assert response.get_json()["success"] is False


def test_disabled_printing_does_not_download_or_claim_success(client, app, monkeypatch):
    app.config["PRINT_ENABLED"] = False

    def unexpected_download(*args):
        raise AssertionError("Não deve baixar uma foto com impressão desabilitada")

    monkeypatch.setattr("app.routes.s3_storage.download_file", unexpected_download)
    response = client.post("/photos/print", json={"key": "back-covers/photo.jpg"})

    assert response.status_code == 409
    assert response.get_json()["success"] is False
    assert response.get_json()["printed"] is False


@pytest.mark.parametrize("failure", ["download", "printer"])
def test_print_failure_cleans_temporary_files_and_does_not_log_success(client, app, monkeypatch, caplog, failure):
    app.config["PRINT_ENABLED"] = True
    key = "back-covers/photo.jpg"
    put_photo(app, key)
    paths = []
    caplog.set_level(logging.INFO)

    def failed_download(path, key):
        paths.append(path)
        path.write_bytes(b"partial-download")
        raise ClientError({"Error": {"Code": "AccessDenied", "Message": "private-detail"}}, "GetObject")

    def failed_print(path):
        paths.append(path)
        assert path.read_bytes() == b"photo-bytes"
        raise PrintError("printer-offline")

    if failure == "download":
        monkeypatch.setattr("app.routes.s3_storage.download_file", failed_download)
    else:
        monkeypatch.setattr("app.routes.printing.print_image", failed_print)
    response = client.post("/photos/print", json={"key": key})

    assert response.status_code == 502
    assert response.get_json()["success"] is False
    assert response.get_json()["printed"] is False
    assert "private-detail" not in response.get_data(as_text=True)
    assert "reimprimir_imagem_sucesso" not in caplog.messages
    assert "reimprimir_imagem_falhou" in caplog.messages
    assert len(paths) == 1
    assert not paths[0].exists()
    assert not paths[0].parent.exists()


def test_gallery_reports_s3_failure_without_leaking_details(client, monkeypatch):
    def failed_list():
        raise EndpointConnectionError(endpoint_url="https://private-detail.test")

    monkeypatch.setattr("app.routes.s3_storage.list_back_covers", failed_list)
    response = client.get("/photos")

    assert response.status_code == 502
    html = response.get_data(as_text=True)
    assert "Não foi possível carregar as fotos" in html
    assert "private-detail" not in html
    assert "Nenhuma foto encontrada" not in html


def test_empty_gallery_shows_empty_state(client):
    response = client.get("/photos")

    assert response.status_code == 200
    assert "Nenhuma foto encontrada na pasta configurada" in response.get_data(as_text=True)


def test_default_folder_includes_nested_photos_and_escapes_filenames(client, app):
    app.config["EVENT_LOCATION"] = ""
    put_photo(app, 'back-covers/<script>"&.png')
    put_photo(app, "back-covers/sp/nested.jpeg")
    put_photo(app, "elsewhere/hidden.jpg")

    response = client.get("/photos")

    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert "nested.jpeg" in html
    assert "hidden.jpg" not in html
    assert '<script>"&.png' not in html
    assert "&lt;script&gt;&#34;&amp;.png" in html
    assert html.count('class="photo-card"') == 2


def test_gallery_assets_and_documented_routes_are_available(client):
    assert client.get("/static/css/photos.css").status_code == 200
    assert client.get("/static/js/photos.js").status_code == 200
    spec = client.get("/apispec.json").get_json()
    assert "get" in spec["paths"]["/photos"]
    assert "post" in spec["paths"]["/photos/print"]
