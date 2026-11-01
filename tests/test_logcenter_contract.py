"""Characterization of both LogCenter adapters; no external logging or printing."""
import io
from copy import deepcopy
from datetime import datetime, timedelta
from uuid import UUID

import boto3
import pytest

from app import logcenter
from app.config import Config
from app.printing import PrintError


@pytest.fixture(scope="module", autouse=True)
def disable_external_logcenter():
    # Run before the app fixture derives TestConfig and calls create_app.
    # Initialization tests explicitly re-enable only their mocked senders.
    with pytest.MonkeyPatch.context() as monkeypatch:
        monkeypatch.setattr(Config, "LOGCENTER_ENABLED", False)
        monkeypatch.setattr(Config, "LOGCENTERV3_ENABLED", False)
        yield


class SenderRecorder:
    def __init__(self):
        self.sync = []
        self.debug = []

    def send_sync(self, *args, **kwargs):
        self.sync.append(deepcopy((args, kwargs)))

    def send_debug(self, message):
        self.debug.append(message)

    def stop_background_flush_thread(self):
        pass


@pytest.fixture
def senders(app, monkeypatch):
    legacy, v3 = SenderRecorder(), SenderRecorder()
    app.extensions["logcenter"] = legacy
    app.extensions["logcenterv3"] = v3
    app.config["EVENT_LOCATION"] = "sp"
    app.config["PRINT_ENABLED"] = True

    def unexpected_print(path):
        raise AssertionError("Audit tests must substitute printer dispatch")

    monkeypatch.setattr("app.routes.printing.print_image", unexpected_print)
    return legacy, v3


def structured_events(sender):
    return [args[0] for args, kwargs in sender.sync]


def assert_event(event, event_type_id):
    assert set(event) == {"event_id", "event_type_id", "occurred_at", "data"}
    assert UUID(event["event_id"]).version == 4
    assert event["event_type_id"] == event_type_id
    assert datetime.fromisoformat(event["occurred_at"]).utcoffset() == timedelta(0)
    assert "{datetime}" not in event["occurred_at"]


def put_photo(app, filename="photo.png"):
    s3 = boto3.client("s3", region_name=app.config["AWS_REGION"])
    key = f"back-covers/sp/{filename}"
    s3.put_object(Bucket=app.config["AWS_S3_BUCKET"], Key=key, Body=b"audit-photo")
    return key


@pytest.mark.parametrize("status, expected", [(200, "success"), (204, "no_content"), (302, "found"), (400, "bad_request"), (404, "not_found"), (502, "bad_gateway")])
def test_legacy_adapter_preserves_tags_payload_and_status(app, senders, status, expected):
    legacy, v3 = senders
    original = {"file": "photo.png"}
    with app.app_context():
        logcenter.log_event("info", "audit_event", data=original, status=status)
    assert legacy.sync == [(("INFO", "audit_event"), {
        "tags": ["server", "sp"], "data": {"file": "photo.png", "event_location": "sp"}, "status": expected,
    })]
    assert original == {"file": "photo.png"}
    assert not v3.sync and not v3.debug


def test_print_success_keeps_legacy_event_and_v3_type_two(client, app, senders, monkeypatch):
    legacy, v3 = senders
    monkeypatch.setattr("app.routes.printing.print_image", lambda path: {"printed": True, "message": "sent"})
    response = client.post("/print", data={"image": (io.BytesIO(b"audit-photo"), "photo.png")})
    assert response.status_code == 200
    filename = response.get_json()["filename"]
    assert legacy.sync == [
        (("INFO", "imprimir_imagem_sucesso"), {"tags": ["server", "sp"], "data": {"file": filename, "event_location": "sp"}, "status": "success"}),
        (("DEBUG", "imprimir_imagem_chamada"), {"tags": ["server", "sp"], "data": {"event_location": "sp"}, "status": "success"}),
    ]
    events = structured_events(v3)
    assert len(events) == 1
    assert_event(events[0], 2)
    assert events[0]["data"] == {"file": filename}
    assert v3.debug == ["sp DEBUG: imprimir_imagem_chamada | status=200"]


def test_digital_only_is_logged_without_false_print_success(client, senders):
    legacy, v3 = senders
    response = client.post("/print", data={"image": (io.BytesIO(b"digital"), "photo.png"), "print": "false"})
    assert response.status_code == 200
    filename = response.get_json()["filename"]
    assert [args[1] for args, kwargs in legacy.sync] == ["apenas_qrcode_gerado", "imprimir_imagem_chamada"]
    assert not v3.sync
    assert v3.debug == [f'sp INFO: apenas_qrcode_gerado | "file": {filename}', "sp DEBUG: imprimir_imagem_chamada | status=200"]


def test_print_failure_keeps_both_error_paths_without_success_event(client, senders, monkeypatch):
    legacy, v3 = senders

    def fail(path):
        raise PrintError("audit-printer-failure")

    monkeypatch.setattr("app.routes.printing.print_image", fail)
    response = client.post("/print", data={"image": (io.BytesIO(b"audit-photo"), "photo.png")})
    assert response.status_code == 200
    assert response.get_json()["printed"] is False
    assert [args[:2] for args, kwargs in legacy.sync] == [("ERROR", "imprimir_imagem_falhou"), ("DEBUG", "imprimir_imagem_chamada")]
    assert legacy.sync[0][1]["data"]["error"] == "audit-printer-failure"
    assert not v3.sync
    assert len(v3.debug) == 2
    assert v3.debug[0].startswith('sp ERROR: imprimir_imagem_falhou | "file": ')
    assert "audit-printer-failure" in v3.debug[0]


def test_invalid_upload_keeps_debug_400_in_both_senders(client, senders):
    legacy, v3 = senders
    assert client.post("/print").status_code == 400
    assert legacy.sync == [(("DEBUG", "imprimir_imagem_chamada"), {"tags": ["server", "sp"], "data": {"event_location": "sp"}, "status": "bad_request"})]
    assert not v3.sync
    assert v3.debug == ["sp DEBUG: imprimir_imagem_chamada | status=400"]


@pytest.mark.parametrize("route, method, message, event_id, status", [
    ("/view/photo.png", "get", "visualizar_foto_acessada", 3, "success"),
    ("/view/photo.png/share", "post", "compartilhar_imagem", 4, "no_content"),
    ("/view/photo.png/download", "get", "baixar_imagem", 5, "found"),
])
def test_view_share_download_keep_original_structured_ids(client, app, senders, route, method, message, event_id, status):
    legacy, v3 = senders
    put_photo(app)
    response = getattr(client, method)(route, headers={"User-Agent": "LogCenterAudit/1.0"})
    assert response.status_code in (200, 204, 302)
    assert len(legacy.sync) == 1
    args, kwargs = legacy.sync[0]
    assert args == ("INFO", message)
    assert kwargs["status"] == status
    assert kwargs["tags"] == ["server", "sp"]
    assert kwargs["data"]["event_location"] == "sp"
    events = structured_events(v3)
    assert len(events) == 1
    assert_event(events[0], event_id)
    assert set(events[0]["data"]) == {"filename", "user_agent", "browser", "platform", "ip"}
    assert events[0]["data"]["filename"] == "photo.png"
    assert events[0]["data"]["user_agent"] == "LogCenterAudit/1.0"
    assert events[0]["data"]["ip"] == "127.0.0.1"
    assert not v3.debug


def test_gallery_reprint_current_contract_is_legacy_info_and_v3_debug_only(client, app, senders, monkeypatch):
    legacy, v3 = senders
    key = put_photo(app)
    monkeypatch.setattr("app.routes.printing.print_image", lambda path: {"printed": True, "message": "sent"})
    assert client.post("/photos/print", json={"key": key}).status_code == 200
    assert legacy.sync == [(("INFO", "reimprimir_imagem_sucesso"), {"tags": ["server", "sp"], "data": {"file": key, "event_location": "sp"}, "status": "success"})]
    assert not v3.sync
    assert v3.debug == [f'sp INFO: reimprimir_imagem_sucesso | "file": {key}']


def test_gallery_print_failure_is_logged_in_both_senders(client, app, senders, monkeypatch):
    legacy, v3 = senders
    key = put_photo(app)

    def fail(path):
        raise PrintError("audit-reprint-failure")

    monkeypatch.setattr("app.routes.printing.print_image", fail)
    assert client.post("/photos/print", json={"key": key}).status_code == 502
    assert [args[:2] for args, kwargs in legacy.sync] == [("ERROR", "reimprimir_imagem_falhou")]
    assert legacy.sync[0][1]["status"] == "bad_gateway"
    assert not v3.sync
    assert len(v3.debug) == 1 and "reimprimir_imagem_falhou" in v3.debug[0]


@pytest.mark.parametrize("legacy_enabled, v3_enabled", [(False, False), (True, False), (False, True), (True, True)])
def test_sender_initialization_is_independent_and_preserves_config(app, monkeypatch, legacy_enabled, v3_enabled):
    constructed = {}
    registered = []

    def factory(name):
        def create(config):
            sender = SenderRecorder()
            constructed[name] = (config, sender)
            return sender
        return create

    monkeypatch.setattr(logcenter, "LogCenterSender", factory("legacy"))
    monkeypatch.setattr(logcenter, "LogCenterV3Sender", factory("v3"))
    monkeypatch.setattr(logcenter.atexit, "register", lambda callback: registered.append(callback))
    app.config.update(
        LOGCENTER_ENABLED=legacy_enabled, LOGCENTER_BASE_URL="https://legacy.invalid", LOGCENTER_PROJECT_ID="audit-project",
        LOGCENTERV3_ENABLED=v3_enabled, LOGCENTERV3_BASE_URL="https://v3.invalid",
        LOGCENTER_SPOOL_DIR=app.config["STORAGE_ROOT"] / "legacy-spool",
        LOGCENTERV3_SPOOL_DIR=app.config["STORAGE_ROOT"] / "v3-spool",
    )
    logcenter.init_logcenter(app)
    assert ("legacy" in constructed) is legacy_enabled
    assert ("v3" in constructed) is v3_enabled
    assert len(registered) == int(legacy_enabled) + int(v3_enabled)
    if legacy_enabled:
        config, sender = constructed["legacy"]
        assert config.project_id == "audit-project"
        assert app.extensions["logcenter"] is sender
    if v3_enabled:
        config, sender = constructed["v3"]
        assert app.extensions["logcenterv3"] is sender
