import io
import logging
from datetime import datetime, timedelta, timezone

import boto3
import pytest
from boto3.exceptions import RetriesExceededError
from botocore.exceptions import BotoCoreError, ClientError

from app import routes
from app.printing import PrintError


@pytest.fixture(autouse=True)
def isolate_print_side_effects(app, monkeypatch):
    app.extensions["logcenter"] = None
    app.extensions["logcenterv3"] = None
    app.config["PRINT_ENABLED"] = True

    def unexpected_print(path):
        raise AssertionError("Printer dispatch must be substituted explicitly")

    monkeypatch.setattr(routes.printing, "print_image", unexpected_print)


def s3_client(app):
    return boto3.client("s3", region_name=app.config["AWS_REGION"])


@pytest.mark.parametrize("location", ["", "sp"])
@pytest.mark.parametrize("print_mode", [None, "true"])
def test_upload_reports_dispatch_time_not_completion_or_upload_time(
    client, app, monkeypatch, caplog, location, print_mode
):
    app.config["EVENT_LOCATION"] = location
    caplog.set_level(logging.INFO)
    queued = datetime(2026, 10, 31, 12, 34, 56, 123456, tzinfo=timezone.utc)
    events = []
    paths = []
    original_upload = routes.s3_storage.upload_file

    class Clock:
        @classmethod
        def now(cls, tz):
            assert tz is timezone.utc
            events.append("queued_at")
            return queued

    def fake_print(path):
        events.append("print")
        paths.append(path)
        assert path.read_bytes() == b"final-image"
        return {"printed": True, "message": "Imagem enviada para impressão"}

    def upload(path, key):
        events.append("upload")
        original_upload(path, key)

    monkeypatch.setattr(routes, "datetime", Clock, raising=False)
    monkeypatch.setattr(routes.printing, "print_image", fake_print)
    monkeypatch.setattr(routes.s3_storage, "upload_file", upload)
    data: dict[str, object] = {"image": (io.BytesIO(b"final-image"), "client-original.jpg")}
    if print_mode is not None:
        data["print"] = print_mode

    response = client.post("/print", data=data, content_type="multipart/form-data")

    assert response.status_code == 200
    body = response.get_json()
    filename = body["page_url"].rsplit("/", 1)[-1]
    key = f"back-covers/{location + '/' if location else ''}{filename}"
    assert body == {
        "success": True,
        "message": "Imagem salva em back-covers e enviada para impressão",
        "page_url": f"http://testserver/view/{filename}",
        "filename": filename,
        "photo_key": key,
        "printed": True,
        "queued_at": queued.isoformat(),
    }
    assert datetime.fromisoformat(body["queued_at"]).utcoffset() == timedelta(0)
    assert events == ["queued_at", "print", "upload"]
    assert len(paths) == 1 and not paths[0].exists()
    obj = s3_client(app).get_object(Bucket=app.config["AWS_S3_BUCKET"], Key=body["photo_key"])
    assert obj["Body"].read() == b"final-image"
    assert "imprimir_imagem_sucesso" in caplog.messages


@pytest.mark.parametrize("location", ["", "sp"])
def test_gallery_dispatch_returns_existing_key_and_time_after_download(
    client, app, monkeypatch, caplog, location
):
    app.config["EVENT_LOCATION"] = location
    key = f"back-covers/{location + '/' if location else ''}nested/photo with spaces.PNG"
    s3 = s3_client(app)
    s3.put_object(Bucket=app.config["AWS_S3_BUCKET"], Key=key, Body=b"stored-original")
    queued = datetime(2026, 10, 31, 12, 34, 56, 123456, tzinfo=timezone.utc)
    events = []
    paths = []
    caplog.set_level(logging.INFO)
    original_download = routes.s3_storage.download_file

    class Clock:
        @classmethod
        def now(cls, tz):
            assert tz is timezone.utc
            events.append("queued_at")
            return queued

    def download(path, photo_key):
        events.append("download")
        original_download(path, photo_key)

    def fake_print(path):
        events.append("print")
        paths.append(path)
        assert path.read_bytes() == b"stored-original"
        return {"printed": True, "message": "Imagem enviada para impressão"}

    def unexpected_upload(*args):
        raise AssertionError("Gallery reprinting must not upload or rename the stored photo")

    monkeypatch.setattr(routes, "datetime", Clock, raising=False)
    monkeypatch.setattr(routes.s3_storage, "download_file", download)
    monkeypatch.setattr(routes.s3_storage, "upload_file", unexpected_upload)
    monkeypatch.setattr(routes.printing, "print_image", fake_print)

    response = client.post("/photos/print", json={"key": key})

    assert response.status_code == 200
    body = response.get_json()
    assert body == {
        "success": True,
        "message": "Imagem enviada para impressão",
        "filename": "photo with spaces.PNG",
        "photo_key": key,
        "printed": True,
        "queued_at": queued.isoformat(),
    }
    assert datetime.fromisoformat(body["queued_at"]).utcoffset() == timedelta(0)
    assert events == ["download", "queued_at", "print"]
    assert len(paths) == 1
    assert not paths[0].exists() and not paths[0].parent.exists()
    objects = s3.list_objects_v2(Bucket=app.config["AWS_S3_BUCKET"])["Contents"]
    assert [obj["Key"] for obj in objects] == [key]
    assert "reimprimir_imagem_sucesso" in caplog.messages


@pytest.mark.parametrize("mode", ["digital", "disabled", "print_error", "not_dispatched"])
@pytest.mark.parametrize("location", ["", "sp"])
def test_upload_storage_only_success_never_claims_a_print(
    client, app, monkeypatch, caplog, mode, location
):
    app.config["EVENT_LOCATION"] = location
    app.config["PRINT_ENABLED"] = mode != "disabled"
    caplog.set_level(logging.INFO)
    calls = []

    def fake_print(path):
        calls.append(path)
        assert path.read_bytes() == b"edited-image"
        if mode == "digital":
            raise AssertionError("Digital-only uploads must not call the printer")
        if mode == "print_error":
            raise PrintError("printer-offline")
        return {"printed": False, "message": "Impressão desabilitada" if mode == "disabled" else "not-dispatched"}

    monkeypatch.setattr(routes.printing, "print_image", fake_print)
    data: dict[str, object] = {"image": (io.BytesIO(b"edited-image"), "client-original.png")}
    if mode == "digital":
        data["print"] = "false"

    response = client.post("/print", data=data, content_type="multipart/form-data")

    assert response.status_code == 200
    body = response.get_json()
    assert body["success"] is True
    filename = body["page_url"].rsplit("/", 1)[-1]
    key = f"back-covers/{location + '/' if location else ''}{filename}"
    assert body["filename"] == filename
    assert "/" not in body["filename"] and "\\" not in body["filename"]
    assert filename.endswith(".png")
    assert body["photo_key"] == key
    assert body["printed"] is False
    assert body["queued_at"] is None
    assert body["page_url"] == f"http://testserver/view/{filename}"
    stored = s3_client(app).get_object(Bucket=app.config["AWS_S3_BUCKET"], Key=key)
    assert stored["Body"].read() == b"edited-image"
    assert "imprimir_imagem_sucesso" not in caplog.messages
    assert len(calls) == (0 if mode == "digital" else 1)
    assert all(not path.exists() for path in calls)
    if mode == "digital":
        assert body["message"] == "Imagem salva em back-covers; apenas QR Code"
        assert "apenas_qrcode_gerado" in caplog.messages
    else:
        assert body["message"].startswith("Imagem salva em back-covers; falha ao imprimir (")
    if mode == "print_error":
        assert "imprimir_imagem_falhou" in caplog.messages


@pytest.mark.parametrize("failure_mode", ["disabled", "missing", "download", "printer", "not_dispatched"])
def test_gallery_without_dispatch_never_returns_success_metadata(
    client, app, monkeypatch, caplog, failure_mode
):
    app.config["PRINT_ENABLED"] = failure_mode != "disabled"
    caplog.set_level(logging.INFO)
    paths = []

    def download(path, key):
        if failure_mode == "disabled":
            raise AssertionError("Disabled printing must not download")
        paths.append(path)
        path.write_bytes(b"photo")
        if failure_mode in ("missing", "download"):
            code = "NoSuchKey" if failure_mode == "missing" else "AccessDenied"
            raise ClientError({"Error": {"Code": code}}, "GetObject")

    def fake_print(path):
        assert failure_mode in ("printer", "not_dispatched")
        if failure_mode == "printer":
            raise PrintError("offline")
        return {"printed": False, "message": "not-dispatched"}

    monkeypatch.setattr(routes.s3_storage, "download_file", download)
    monkeypatch.setattr(routes.printing, "print_image", fake_print)

    response = client.post("/photos/print", json={"key": "back-covers/photo.jpg"})

    expected_status = {"disabled": 409, "missing": 404, "download": 502, "printer": 502, "not_dispatched": 409}
    assert response.status_code == expected_status[failure_mode]
    body = response.get_json()
    assert body["success"] is False and body["printed"] is False
    assert body.get("queued_at") is None
    assert "filename" not in body and "photo_key" not in body
    assert "reimprimir_imagem_sucesso" not in caplog.messages
    assert len(paths) == (0 if failure_mode == "disabled" else 1)
    assert all(not path.exists() and not path.parent.exists() for path in paths)


def test_gallery_exhausted_download_retries_return_json_502_log_and_clean_tempdir(
    client, app, monkeypatch, caplog
):
    key = "back-covers/photo.jpg"
    paths = []
    debug_logs = []
    caplog.set_level(logging.INFO)
    failure = RetriesExceededError(OSError("private-download-detail"))
    assert not isinstance(failure, (BotoCoreError, ClientError, OSError))

    class LogSender:
        def send_debug(self, message):
            debug_logs.append(message)

    app.extensions["logcenterv3"] = LogSender()

    def failed_download(path, photo_key):
        assert photo_key == key
        paths.append(path)
        path.write_bytes(b"partial-download")
        raise failure

    monkeypatch.setattr(routes.s3_storage, "download_file", failed_download)

    response = client.post("/photos/print", json={"key": key})

    assert response.status_code == 502
    assert response.is_json
    assert response.get_json() == {
        "success": False,
        "printed": False,
        "message": "Não foi possível imprimir a foto. Verifique o S3 e a impressora.",
    }
    assert "private-download-detail" not in response.get_data(as_text=True)
    failures = [record for record in caplog.records if record.message == "reimprimir_imagem_falhou"]
    assert len(failures) == 1 and failures[0].levelno == logging.ERROR
    assert "reimprimir_imagem_sucesso" not in caplog.messages
    assert any("reimprimir_imagem_falhou" in message and key in message for message in debug_logs)
    assert len(paths) == 1
    assert not paths[0].exists() and not paths[0].parent.exists()
