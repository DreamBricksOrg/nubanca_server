import io
import logging

import boto3
import pytest


def test_editor_has_qrcode_only_button_below_save(client):
    response = client.get("/editor")

    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert 'id="qrcodeOnly"' in html
    assert html.index('id="saveImage"') < html.index('id="qrcodeOnly"')
    assert '>Apenas Digital</button>' in html


def test_qrcode_only_saves_image_and_logs_without_printing(client, app, monkeypatch, caplog):
    def unexpected_print(path):
        raise AssertionError("O modo apenas qrcode não deve chamar a impressão")

    monkeypatch.setattr("app.routes.printing.print_image", unexpected_print)
    app.config["PRINT_ENABLED"] = True
    caplog.set_level(logging.INFO)
    debug_logs = []

    class LogSender:
        def send_debug(self, message):
            debug_logs.append(message)

    app.extensions["logcenterv3"] = LogSender()
    response = client.post(
        "/print",
        data={
            "image": (io.BytesIO(b"edited-image-bytes"), "edited.png"),
            "print": "false",
        },
        content_type="multipart/form-data",
    )

    assert response.status_code == 200
    body = response.get_json()
    assert body["success"] is True
    assert body["message"] == "Imagem salva em back-covers; apenas QR Code"
    filename = body["page_url"].rsplit("/", 1)[-1]
    assert body["page_url"] == f"http://testserver/view/{filename}"
    s3 = boto3.client("s3", region_name=app.config["AWS_REGION"])
    obj = s3.get_object(Bucket=app.config["AWS_S3_BUCKET"], Key=f"back-covers/{filename}")
    assert obj["Body"].read() == b"edited-image-bytes"
    assert "apenas_qrcode_gerado" in caplog.messages
    assert "imprimir_imagem_sucesso" not in caplog.messages
    assert "imprimir_imagem_falhou" not in caplog.messages
    assert any("apenas_qrcode_gerado" in message and filename in message for message in debug_logs)
    app.extensions["logcenterv3"] = None
    assert client.get(f"/view/{filename}").status_code == 200


@pytest.mark.parametrize("filename", [None, "", "edited.gif"])
def test_qrcode_only_rejects_invalid_upload(client, monkeypatch, caplog, filename):
    def unexpected_print(path):
        raise AssertionError("Não deve imprimir um upload inválido")

    monkeypatch.setattr("app.routes.printing.print_image", unexpected_print)
    caplog.set_level(logging.INFO)
    data: dict[str, object] = {"print": "false"}
    if filename is not None:
        data["image"] = (io.BytesIO(b"image-bytes"), filename)

    response = client.post("/print", data=data, content_type="multipart/form-data")

    assert response.status_code == 400
    assert response.get_json()["success"] is False
    assert "apenas_qrcode_gerado" not in caplog.messages
