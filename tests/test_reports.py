from datetime import date, datetime, timedelta, timezone
import re

import boto3
import mongomock
import pytest
from bson import ObjectId
from pymongo.errors import ServerSelectionTimeoutError

from app import reports


def test_report_uses_brasilia_day_boundaries_and_attributes_cross_midnight_access(app, client, monkeypatch):
    mongo = mongomock.MongoClient()
    project_id = ObjectId()
    mongo.logcenter_prod.logs.insert_many([
        {"project_id": project_id, "message": "imprimir_imagem_sucesso", "timestamp": "2026-11-01T02:59:59Z", "data": {"event_location": "sp", "file": "previous.jpg"}},
        {"project_id": project_id, "message": "imprimir_imagem_sucesso", "timestamp": "2026-11-01T03:00:00Z", "data": {"event_location": "sp", "file": "today.jpg"}},
        {"project_id": project_id, "message": "apenas_qrcode_gerado", "timestamp": "2026-11-02T02:59:30Z", "data": {"event_location": "sp", "file": "late.jpg"}},
        {"project_id": project_id, "message": "visualizar_foto_acessada", "timestamp": "2026-11-02T03:00:10Z", "data": {"event_location": "sp", "filename": "late.jpg"}},
        {"project_id": project_id, "message": "apenas_qrcode_gerado", "timestamp": "2026-11-02T03:00:00Z", "data": {"event_location": "sp", "file": "tomorrow.jpg"}},
    ])
    monkeypatch.setattr(reports, "MongoClient", lambda *args, **kwargs: mongo)
    app.config.update(LOGCENTER_MONGOURL="mongodb://unused", LOGCENTER_MONGO_DB="logcenter_prod",
                      LOGCENTER_MONGO_COLLECTION="logs", LOGCENTER_PROJECT_ID=str(project_id), EVENT_LOCATION="sp")

    response = client.get("/relatorio?inicio=2026-11-01&fim=2026-11-01&event_location=sp")

    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert "Brasília (GMT-3)" in html
    assert 'data-metric="generated" data-count="2"' in html
    assert 'data-event="imprimir_imagem_sucesso" data-count="1"' in html
    assert 'data-event="apenas_qrcode_gerado" data-count="1"' in html
    assert '<td data-metric="digital-opened" data-count="1">1</td>' in html


def test_hourly_chart_shows_brasilia_activity_from_10_through_23(app, client, monkeypatch):
    mongo = mongomock.MongoClient()
    project_id = ObjectId()
    mongo.logcenter_prod.logs.insert_many([
        {"project_id": project_id, "message": kind, "timestamp": at,
         "data": {"event_location": "rj"}}
        for kind, at in (
            ("apenas_qrcode_gerado", "2026-11-01T12:59:00Z"),  # 09:59
            ("imprimir_imagem_sucesso", "2026-11-01T13:00:00Z"),  # 10:00
            ("apenas_qrcode_gerado", "2026-11-01T13:30:00Z"),  # 10:30
            ("imprimir_imagem_sucesso", "2026-11-01T13:50:00Z"),  # 10:50
            ("reimprimir_imagem_sucesso", "2026-11-01T13:45:00Z"),  # no new cover
            ("apenas_qrcode_gerado", "2026-11-02T02:00:00Z"),  # 23:00
            ("imprimir_imagem_sucesso", "2026-11-02T03:30:00Z"),  # next day 00:30
        )
    ])
    monkeypatch.setattr(reports, "MongoClient", lambda *args, **kwargs: mongo)
    app.config.update(LOGCENTER_MONGOURL="mongodb://unused", LOGCENTER_MONGO_DB="logcenter_prod",
                      LOGCENTER_MONGO_COLLECTION="logs", LOGCENTER_PROJECT_ID=str(project_id), EVENT_LOCATION="sp")

    response = client.get("/relatorio?inicio=2026-11-01&fim=2026-11-01&event_location=rj")

    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert re.findall(r'data-hour="(\d+)"', html) == [str(hour) for hour in range(10, 24)]
    assert 'data-hour="10" data-printed="2" data-digital="1" data-count="3"' in html
    assert 'data-hour="23" data-printed="0" data-digital="1" data-count="1"' in html
    assert 'Pico: 10:00' in html
    assert 'data-metric="generated" data-count="5"' in html
    assert 'Fora do intervalo exibido: 1' in html


def test_daily_chart_includes_zero_days_and_brasilia_dates(app, client, monkeypatch):
    mongo = mongomock.MongoClient()
    project_id = ObjectId()
    mongo.logcenter_prod.logs.insert_many([
        {"project_id": project_id, "message": kind, "timestamp": at,
         "data": {"event_location": "sp"}}
        for kind, at in (
            ("imprimir_imagem_sucesso", "2026-10-31T13:00:00Z"),
            ("apenas_qrcode_gerado", "2026-11-01T01:00:00Z"),  # still Oct 31 locally
            ("imprimir_imagem_sucesso", "2026-11-01T13:00:00Z"),
            ("imprimir_imagem_sucesso", "2026-11-01T15:00:00Z"),
            ("apenas_qrcode_gerado", "2026-11-02T02:00:00Z"),  # still Nov 1 locally
        )
    ])
    monkeypatch.setattr(reports, "MongoClient", lambda *args, **kwargs: mongo)
    app.config.update(LOGCENTER_MONGOURL="mongodb://unused", LOGCENTER_MONGO_DB="logcenter_prod",
                      LOGCENTER_MONGO_COLLECTION="logs", LOGCENTER_PROJECT_ID=str(project_id), EVENT_LOCATION="sp")

    response = client.get("/relatorio?inicio=2026-10-31&fim=2026-11-02")

    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert "Capas por dia" in html
    assert re.findall(r'data-day="(\d{4}-\d{2}-\d{2})"', html) == ["2026-10-31", "2026-11-01", "2026-11-02"]
    assert 'data-day="2026-10-31" data-printed="1" data-digital="1" data-count="2"' in html
    assert 'data-day="2026-11-01" data-printed="2" data-digital="1" data-count="3"' in html
    assert 'data-day="2026-11-02" data-printed="0" data-digital="0" data-count="0"' in html


def test_report_default_dates_follow_brasilia_even_before_utc_midnight(app, monkeypatch):
    class FixedDatetime(datetime):
        @classmethod
        def now(cls, tz=None):
            return datetime(2026, 11, 2, 2, 30, tzinfo=timezone.utc).astimezone(tz)

    monkeypatch.setattr(reports, "datetime", FixedDatetime)
    with app.test_request_context("/relatorio"):
        assert reports._dates() == (date(2026, 11, 1) - timedelta(days=6), date(2026, 11, 1))


def test_empty_report_renders_zero_activity_in_both_charts(app, client, monkeypatch):
    mongo = mongomock.MongoClient()
    monkeypatch.setattr(reports, "MongoClient", lambda *args, **kwargs: mongo)
    app.config.update(LOGCENTER_MONGOURL="mongodb://unused", LOGCENTER_MONGO_DB="logcenter_prod",
                      LOGCENTER_MONGO_COLLECTION="logs", LOGCENTER_PROJECT_ID=str(ObjectId()), EVENT_LOCATION="sp")

    response = client.get("/relatorio?inicio=2026-11-01&fim=2026-11-01")

    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert len(re.findall(r'data-hour="\d+" data-printed="0" data-digital="0" data-count="0"', html)) == 14
    assert 'data-day="2026-11-01" data-printed="0" data-digital="0" data-count="0"' in html
    assert "Pico:" not in html


def test_hourly_peak_tie_uses_earliest_hour(app, client, monkeypatch):
    mongo = mongomock.MongoClient()
    project_id = ObjectId()
    mongo.logcenter_prod.logs.insert_many([
        {"project_id": project_id, "message": "imprimir_imagem_sucesso",
         "timestamp": timestamp, "data": {"event_location": "sp"}}
        for timestamp in ("2026-11-01T13:00:00Z", "2026-11-01T14:00:00Z")
    ])
    monkeypatch.setattr(reports, "MongoClient", lambda *args, **kwargs: mongo)
    app.config.update(LOGCENTER_MONGOURL="mongodb://unused", LOGCENTER_MONGO_DB="logcenter_prod",
                      LOGCENTER_MONGO_COLLECTION="logs", LOGCENTER_PROJECT_ID=str(project_id), EVENT_LOCATION="sp")

    response = client.get("/relatorio?inicio=2026-11-01&fim=2026-11-01")

    assert response.status_code == 200
    assert "Pico: 10:00 · 1 capa" in response.get_data(as_text=True)


def test_report_header_uses_white_logo_asset(app, client, monkeypatch):
    mongo = mongomock.MongoClient()
    monkeypatch.setattr(reports, "MongoClient", lambda *args, **kwargs: mongo)
    app.config.update(LOGCENTER_MONGOURL="mongodb://unused", LOGCENTER_MONGO_DB="logcenter_prod",
                      LOGCENTER_MONGO_COLLECTION="logs", LOGCENTER_PROJECT_ID=str(ObjectId()), EVENT_LOCATION="sp")

    response = client.get("/relatorio?inicio=2026-11-01&fim=2026-11-01")

    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert 'class="brand-mark"><img src="/static/img/logo-white.png" alt="" /></span>' in html
    assert '<span class="brand-mark">N</span>' not in html
    assert "css/reports.css?v=charts-1" in html
    assert client.get("/static/img/logo-white.png").status_code == 200


def test_report_separates_generated_covers_from_reprints_by_day(app, client, monkeypatch):
    mongo = mongomock.MongoClient()
    project_id = ObjectId()
    other_project = ObjectId()
    mongo.logcenter_prod.logs.insert_many([
        {"project_id": project_id, "message": "imprimir_imagem_sucesso", "timestamp": "2026-10-31T10:00:00Z", "data": {"event_location": "rj", "file": "one.jpg"}},
        {"project_id": project_id, "message": "apenas_qrcode_gerado", "timestamp": "2026-10-31T11:00:00Z", "data": {"event_location": "rj", "file": "two.jpg"}},
        {"project_id": project_id, "message": "imprimir_imagem_sucesso", "timestamp": "2026-11-01T11:00:00Z", "data": {"event_location": "rj", "file": "three.jpg"}},
        {"project_id": project_id, "message": "reimprimir_imagem_sucesso", "timestamp": "2026-11-01T12:00:00Z", "data": {"event_location": "rj", "file": "back-covers/rj/one.jpg"}},
        {"project_id": project_id, "message": "imprimir_imagem_sucesso", "timestamp": "2026-11-01T13:00:00Z", "data": {"event_location": "sp", "file": "sp.jpg"}},
        {"project_id": other_project, "message": "apenas_qrcode_gerado", "timestamp": "2026-11-01T14:00:00Z", "data": {"event_location": "rj", "file": "other.jpg"}},
        {"project_id": project_id, "message": "reimprimir_imagem_sucesso", "timestamp": "2026-11-02T03:00:00Z", "data": {"event_location": "rj", "file": "back-covers/rj/two.jpg"}},
    ])
    monkeypatch.setattr(reports, "MongoClient", lambda *args, **kwargs: mongo)
    app.config.update(LOGCENTER_MONGOURL="mongodb://unused", LOGCENTER_MONGO_DB="logcenter_prod",
                      LOGCENTER_MONGO_COLLECTION="logs", LOGCENTER_PROJECT_ID=str(project_id), EVENT_LOCATION="sp")

    response = client.get("/relatorio?inicio=2026-10-31&fim=2026-11-01&event_location=rj")

    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert '<article class="card card-1" data-metric="generated" data-count="3">' in html
    assert 'data-event="imprimir_imagem_sucesso" data-count="2"' in html
    assert 'data-event="apenas_qrcode_gerado" data-count="1"' in html
    assert 'data-event="reimprimir_imagem_sucesso" data-count="1"' in html
    assert '2026-10-31</th><td data-metric="generated" data-count="2">2</td><td>1</td><td>1</td><td>0</td>' in html
    assert '2026-11-01</th><td data-metric="generated" data-count="1">1</td><td>1</td><td>0</td><td>1</td>' in html


def test_report_counts_distinct_removed_cover_files_in_selected_location_and_period(app, client, monkeypatch):
    mongo = mongomock.MongoClient()
    project = ObjectId()
    mongo.logcenter_prod.logs.insert_many([
        {"project_id": project, "message": message, "timestamp": timestamp,
         "data": {"event_location": location, "file": filename}}
        for message, timestamp, location, filename in (
            ("imprimir_imagem_sucesso", "2026-11-01T17:57:45Z", "rj", "removed.png"),
            ("imprimir_imagem_sucesso", "2026-11-01T17:57:46Z", "rj", "removed.png"),
            ("apenas_qrcode_gerado", "2026-11-01T18:00:00Z", "rj", "present.png"),
            ("reimprimir_imagem_sucesso", "2026-11-01T18:01:00Z", "rj", "back-covers/rj/gone.png"),
            ("apenas_qrcode_gerado", "2026-11-01T18:02:00Z", "sp", "gone.png"),
            ("apenas_qrcode_gerado", "2026-11-02T03:00:00Z", "rj", "tomorrow.png"),
        )
    ])
    monkeypatch.setattr(reports, "MongoClient", lambda *args, **kwargs: mongo)
    app.config.update(LOGCENTER_MONGOURL="mongodb://unused", LOGCENTER_MONGO_DB="logcenter_prod",
                      LOGCENTER_MONGO_COLLECTION="logs", LOGCENTER_PROJECT_ID=str(project), EVENT_LOCATION="sp")
    s3 = boto3.client("s3", region_name=app.config["AWS_REGION"])
    s3.put_object(Bucket=app.config["AWS_S3_BUCKET"], Key="back-covers/rj/present.png", Body=b"x")

    response = client.get("/relatorio?inicio=2026-10-31&fim=2026-11-01&event_location=rj")

    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert 'data-metric="generated" data-count="3"' in html
    assert 'data-metric="removed" data-count="1"' in html
    assert "removed.png" not in html


def test_report_reads_legacy_logcenter_logs_without_authentication(app, client, monkeypatch):
    mongo = mongomock.MongoClient()
    project_id = ObjectId()
    other_project = ObjectId()
    mongo.logcenter_prod.logs.insert_many([
        {"project_id": project_id, "message": "imprimir_imagem_sucesso", "timestamp": "2026-11-01T09:00:00Z", "data": {"event_location": "sp"}},
        {"project_id": project_id, "message": "reimprimir_imagem_sucesso", "timestamp": "2026-11-01T10:00:00Z", "data": {"event_location": "sp"}},
        {"project_id": project_id, "message": "visualizar_foto_acessada", "timestamp": "2026-11-02T11:00:00.000001Z", "data": {"event_location": "sp"}},
        {"project_id": project_id, "message": "compartilhar_imagem", "timestamp": "2026-11-02T12:00:00Z", "data": {"event_location": "sp"}},
        {"project_id": project_id, "message": "baixar_imagem", "timestamp": "2026-11-02T13:00:00Z", "data": {"event_location": "sp"}},
        {"project_id": other_project, "message": "visualizar_foto_acessada", "timestamp": "2026-11-02T14:00:00Z", "data": {"event_location": "sp"}},
        {"project_id": project_id, "message": "visualizar_foto_acessada", "timestamp": "2026-11-02T15:00:00Z", "data": {"event_location": "rj"}},
        {"project_id": project_id, "message": "baixar_imagem", "timestamp": "2026-11-03T00:00:00Z", "data": {"event_location": "sp"}},
    ])
    monkeypatch.setattr(reports, "MongoClient", lambda *args, **kwargs: mongo)
    app.config.update(REPORT_USERNAME="", REPORT_PASSWORD="", LOGCENTER_MONGOURL="mongodb://unused",
                      LOGCENTER_MONGO_DB="logcenter_prod", LOGCENTER_MONGO_COLLECTION="logs",
                      LOGCENTER_PROJECT_ID=str(project_id), EVENT_LOCATION="sp")

    response = client.get("/relatorio?inicio=2026-11-01&fim=2026-11-02")

    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert 'data-metric="generated" data-count="1"' in html
    assert 'data-event="imprimir_imagem_sucesso" data-count="1"' in html
    assert 'data-event="reimprimir_imagem_sucesso" data-count="1"' in html
    assert "2026-11-03" not in html


def test_report_filters_by_selected_event_location(app, client, monkeypatch):
    mongo = mongomock.MongoClient()
    project_id = ObjectId()
    mongo.logcenter_prod.logs.insert_many([
        {"project_id": project_id, "message": "visualizar_foto_acessada", "timestamp": "2026-11-01T12:00:00Z", "data": {"event_location": "sp"}},
        {"project_id": project_id, "message": "visualizar_foto_acessada", "timestamp": "2026-11-01T13:00:00Z", "data": {"event_location": "sp"}},
        {"project_id": project_id, "message": "visualizar_foto_acessada", "timestamp": "2026-11-01T14:00:00Z", "data": {"event_location": "rj"}},
    ])
    monkeypatch.setattr(reports, "MongoClient", lambda *args, **kwargs: mongo)
    app.config.update(LOGCENTER_MONGOURL="mongodb://unused", LOGCENTER_MONGO_DB="logcenter_prod",
                      LOGCENTER_MONGO_COLLECTION="logs", LOGCENTER_PROJECT_ID=str(project_id), EVENT_LOCATION="sp")

    response = client.get("/relatorio?inicio=2026-11-01&fim=2026-11-01&event_location=rj")

    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert '<option value="rj" selected>RJ</option>' in html
    assert '<option value="sp">SP</option>' in html
    assert 'data-count="1"' in html
    assert 'data-count="2"' not in html


def test_report_shows_qrcode_only_counts_in_selected_location(app, client, monkeypatch):
    mongo = mongomock.MongoClient()
    project_id = ObjectId()
    mongo.logcenter_prod.logs.insert_many([
        {"project_id": project_id, "message": "apenas_qrcode_gerado", "timestamp": "2026-11-01T10:00:00Z", "data": {"event_location": "sp", "file": "sp.jpg"}},
        {"project_id": project_id, "message": "apenas_qrcode_gerado", "timestamp": "2026-11-01T11:00:00Z", "data": {"event_location": "rj", "file": "rj-a.jpg"}},
        {"project_id": project_id, "message": "apenas_qrcode_gerado", "timestamp": "2026-11-02T12:00:00Z", "data": {"event_location": "rj", "file": "rj-b.jpg"}},
    ])
    monkeypatch.setattr(reports, "MongoClient", lambda *args, **kwargs: mongo)
    app.config.update(LOGCENTER_MONGOURL="mongodb://unused", LOGCENTER_MONGO_DB="logcenter_prod",
                      LOGCENTER_MONGO_COLLECTION="logs", LOGCENTER_PROJECT_ID=str(project_id), EVENT_LOCATION="sp")

    response = client.get("/relatorio?inicio=2026-11-01&fim=2026-11-02&event_location=rj")

    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert "Apenas QR Code" in html
    assert '<th scope="col">Apenas QR Code</th>' in html
    assert 'data-count="2"' in html
    assert 'data-count="3"' not in html


def test_daily_detail_matches_editor_photos_opened_within_one_minute(app, client, monkeypatch):
    mongo = mongomock.MongoClient()
    project_id = ObjectId()
    other_project = ObjectId()

    def event(message, timestamp, filename, *, location="sp", project=project_id):
        key = "filename" if message == "visualizar_foto_acessada" else "file"
        return {"project_id": project, "message": message, "timestamp": timestamp,
                "data": {"event_location": location, key: filename}}

    mongo.logcenter_prod.logs.insert_many([
        event("imprimir_imagem_sucesso", "2026-11-01T12:00:00Z", "printed.jpg"),
        event("visualizar_foto_acessada", "2026-11-01T12:00:59Z", "printed.jpg"),
        event("visualizar_foto_acessada", "2026-11-01T12:01:00Z", "printed.jpg"),
        event("apenas_qrcode_gerado", "2026-11-01T23:59:30Z", "digital.jpg"),
        event("visualizar_foto_acessada", "2026-11-02T00:00:30Z", "digital.jpg"),
        event("imprimir_imagem_sucesso", "2026-11-01T10:00:00Z", "too-late.jpg"),
        event("visualizar_foto_acessada", "2026-11-01T09:59:59Z", "too-late.jpg"),
        event("visualizar_foto_acessada", "2026-11-01T10:01:01Z", "too-late.jpg"),
        event("apenas_qrcode_gerado", "2026-11-01T14:00:00Z", "wrong-site.jpg"),
        event("visualizar_foto_acessada", "2026-11-01T14:00:10Z", "wrong-site.jpg", location="rj"),
        event("visualizar_foto_acessada", "2026-11-01T14:00:20Z", "wrong-site.jpg", project=other_project),
        event("reimprimir_imagem_sucesso", "2026-11-01T16:00:00Z", "reprint.jpg"),
        event("visualizar_foto_acessada", "2026-11-01T16:00:10Z", "reprint.jpg"),
    ])
    monkeypatch.setattr(reports, "MongoClient", lambda *args, **kwargs: mongo)
    app.config.update(LOGCENTER_MONGOURL="mongodb://unused", LOGCENTER_MONGO_DB="logcenter_prod",
                      LOGCENTER_MONGO_COLLECTION="logs", LOGCENTER_PROJECT_ID=str(project_id), EVENT_LOCATION="sp")

    response = client.get("/relatorio?inicio=2026-11-01&fim=2026-11-01&event_location=sp")

    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert "Fotos apenas QR Code" not in html
    assert '<td data-metric="printed-opened" data-count="1">1</td>' in html
    assert '<td data-metric="digital-opened" data-count="1">1</td>' in html


def test_report_omits_qrcode_photo_list_but_preserves_daily_counts(app, client, monkeypatch):
    mongo = mongomock.MongoClient()
    project_id = ObjectId()
    mongo.logcenter_prod.logs.insert_many([
        {"project_id": project_id, "message": "apenas_qrcode_gerado", "timestamp": "2026-11-01T11:00:00Z", "data": {"event_location": "rj", "file": "foto-antiga.jpg"}},
        {"project_id": project_id, "message": "apenas_qrcode_gerado", "timestamp": "2026-11-02T12:30:00Z", "data": {"event_location": "rj", "file": "<foto-nova>.jpg"}},
        {"project_id": project_id, "message": "apenas_qrcode_gerado", "timestamp": "2026-11-02T13:00:00Z", "data": {"event_location": "sp", "file": "foto-sp.jpg"}},
        {"project_id": project_id, "message": "apenas_qrcode_gerado", "timestamp": "2026-11-03T12:30:00Z", "data": {"event_location": "rj", "file": "fora-do-periodo.jpg"}},
    ])
    monkeypatch.setattr(reports, "MongoClient", lambda *args, **kwargs: mongo)
    app.config.update(LOGCENTER_MONGOURL="mongodb://unused", LOGCENTER_MONGO_DB="logcenter_prod",
                      LOGCENTER_MONGO_COLLECTION="logs", LOGCENTER_PROJECT_ID=str(project_id), EVENT_LOCATION="sp")

    response = client.get("/relatorio?inicio=2026-11-01&fim=2026-11-02&event_location=rj")

    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert "Fotos apenas QR Code" not in html
    assert 'data-count="2"' in html
    assert "foto-antiga.jpg" not in html
    assert "foto-nova" not in html
    assert "foto-sp.jpg" not in html
    assert "fora-do-periodo.jpg" not in html


def test_report_rejects_unknown_location_before_querying(app, client, monkeypatch):
    app.config.update(LOGCENTER_MONGOURL="mongodb://unused", LOGCENTER_PROJECT_ID=str(ObjectId()))
    monkeypatch.setattr(reports, "MongoClient", lambda *args, **kwargs: pytest.fail("Should not connect"))

    response = client.get("/relatorio?event_location=outro")

    assert response.status_code == 400


def test_report_uses_configured_rj_as_default(app, client, monkeypatch):
    mongo = mongomock.MongoClient()
    project_id = ObjectId()
    mongo.logcenter_prod.logs.insert_many([
        {"project_id": project_id, "message": "apenas_qrcode_gerado", "timestamp": "2026-11-01T10:00:00Z", "data": {"event_location": "sp", "file": "sp.jpg"}},
        {"project_id": project_id, "message": "apenas_qrcode_gerado", "timestamp": "2026-11-01T10:00:00Z", "data": {"event_location": "rj", "file": "rj.jpg"}},
    ])
    monkeypatch.setattr(reports, "MongoClient", lambda *args, **kwargs: mongo)
    app.config.update(LOGCENTER_MONGOURL="mongodb://unused", LOGCENTER_MONGO_DB="logcenter_prod",
                      LOGCENTER_MONGO_COLLECTION="logs", LOGCENTER_PROJECT_ID=str(project_id), EVENT_LOCATION="rj")

    response = client.get("/relatorio?inicio=2026-11-01&fim=2026-11-01")

    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert '<option value="rj" selected>RJ</option>' in html
    assert 'data-count="1"' in html
    assert "rj.jpg" not in html
    assert "sp.jpg" not in html


def test_report_counts_all_qrcode_views_without_listing_files(app, client, monkeypatch):
    mongo = mongomock.MongoClient()
    project_id = ObjectId()
    generations = [
        {"project_id": project_id, "message": "apenas_qrcode_gerado", "timestamp": "2026-11-01T10:00:00Z",
         "data": {"event_location": "sp", "file": f"foto-{index:03}.jpg"}}
        for index in range(201)
    ]
    views = [
        {"project_id": project_id, "message": "visualizar_foto_acessada", "timestamp": "2026-11-01T10:00:59Z",
         "data": {"event_location": "sp", "filename": f"foto-{index:03}.jpg"}}
        for index in range(201)
    ]
    mongo.logcenter_prod.logs.insert_many(generations + views)
    monkeypatch.setattr(reports, "MongoClient", lambda *args, **kwargs: mongo)
    app.config.update(LOGCENTER_MONGOURL="mongodb://unused", LOGCENTER_MONGO_DB="logcenter_prod",
                      LOGCENTER_MONGO_COLLECTION="logs", LOGCENTER_PROJECT_ID=str(project_id), EVENT_LOCATION="sp")

    response = client.get("/relatorio?inicio=2026-11-01&fim=2026-11-01")

    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert 'data-count="201"' in html
    assert '<td data-metric="digital-opened" data-count="201">201</td>' in html
    assert "foto-" not in html


def test_report_counts_events_in_inclusive_utc_dates(app, client, monkeypatch):
    mongo = mongomock.MongoClient()
    project_id = ObjectId()
    mongo.logcenter.events.insert_many([
        {"project_id": project_id, "message": "imprimir_imagem_sucesso", "timestamp": "2026-11-01T00:00:00Z", "data": {"event_location": "sp"}},
        {"project_id": project_id, "message": "visualizar_foto_acessada", "timestamp": "2026-11-01T10:00:00Z", "data": {"event_location": "sp"}},
        {"project_id": project_id, "message": "visualizar_foto_acessada", "timestamp": "2026-11-02T12:00:00Z", "data": {"event_location": "sp"}},
        {"project_id": project_id, "message": "compartilhar_imagem", "timestamp": "2026-11-02T16:00:00Z", "data": {"event_location": "sp"}},
        {"project_id": project_id, "message": "baixar_imagem", "timestamp": "2026-11-02T23:59:59Z", "data": {"event_location": "sp"}},
        {"project_id": project_id, "message": "imprimir_imagem_sucesso", "timestamp": "2026-11-03T00:00:00Z", "data": {"event_location": "sp"}},
        {"project_id": project_id, "message": "imprimir_imagem_sucesso", "timestamp": "2026-10-31T23:59:59Z", "data": {"event_location": "sp"}},
        {"project_id": project_id, "message": "some_other_event", "timestamp": "2026-11-01T00:00:00Z", "data": {"event_location": "sp"}},
    ])
    monkeypatch.setattr(reports, "MongoClient", lambda *args, **kwargs: mongo)
    app.config.update(LOGCENTER_MONGOURL="mongodb://unused/logcenter", LOGCENTER_MONGO_DB="logcenter",
                      LOGCENTER_MONGO_COLLECTION="events", LOGCENTER_PROJECT_ID=str(project_id), EVENT_LOCATION="")

    response = client.get("/relatorio?inicio=2026-11-01&fim=2026-11-02")

    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert "Capas geradas" in html
    assert "Geradas para impressão" in html
    assert "Reimpressões" in html
    assert "Visualizações" in html
    assert "Compartilhamentos" in html
    assert "Downloads" in html
    assert 'data-metric="generated" data-count="1"' in html
    assert 'data-event="visualizar_foto_acessada" data-count="2"' in html
    assert "2026-11-01" in html
    assert "2026-11-02" in html
    assert "2026-11-03" not in html
    assert response.headers["Cache-Control"] == "no-store"


def test_report_rejects_invalid_dates_without_querying(app, client, monkeypatch):
    app.config.update(LOGCENTER_MONGOURL="mongodb://invalid")
    monkeypatch.setattr(reports, "MongoClient", lambda *args, **kwargs: pytest.fail("Should not connect"), raising=False)

    for query in ("inicio=2026-02-30&fim=2026-03-01", "inicio=2026-11-02&fim=2026-11-01",
                  "inicio=2026-01-01&fim=2026-11-02"):
        response = client.get(f"/relatorio?{query}")
        assert response.status_code == 400


def test_report_missing_mongo_configuration_is_safe(app, client):
    app.config.update(LOGCENTER_MONGOURL="")

    response = client.get("/relatorio")

    assert response.status_code == 503
    assert "configuração" in response.get_data(as_text=True)


def test_report_counts_bson_datetime_events(app, client, monkeypatch):
    mongo = mongomock.MongoClient()
    project_id = ObjectId()
    mongo.logcenter.events.insert_many([
        {"project_id": project_id, "message": "imprimir_imagem_sucesso", "timestamp": datetime(2026, 11, 1, 15, tzinfo=timezone.utc), "data": {"event_location": "sp"}},
        {"project_id": project_id, "message": "baixar_imagem", "timestamp": datetime(2026, 11, 2, 23, tzinfo=timezone.utc), "data": {"event_location": "sp"}},
        {"project_id": project_id, "message": "baixar_imagem", "timestamp": datetime(2026, 11, 3, 3, tzinfo=timezone.utc), "data": {"event_location": "sp"}},
    ])
    monkeypatch.setattr(reports, "MongoClient", lambda *args, **kwargs: mongo)
    app.config.update(LOGCENTER_MONGOURL="mongodb://unused/logcenter", LOGCENTER_MONGO_DB="logcenter",
                      LOGCENTER_MONGO_COLLECTION="events", LOGCENTER_PROJECT_ID=str(project_id), EVENT_LOCATION="")

    response = client.get("/relatorio?inicio=2026-11-01&fim=2026-11-02")

    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert 'data-metric="generated" data-count="1"' in html
    assert 'data-event="imprimir_imagem_sucesso" data-count="1"' in html
    assert 'data-event="baixar_imagem" data-count="1"' in html
    assert 'data-event="reimprimir_imagem_sucesso" data-count="0"' in html


def test_report_does_not_leak_mongo_errors(app, client, monkeypatch):
    def unavailable(*args, **kwargs):
        raise ServerSelectionTimeoutError("mongodb://private-host/secret")

    monkeypatch.setattr(reports, "MongoClient", unavailable)
    app.config.update(LOGCENTER_MONGOURL="mongodb://private-host/secret", LOGCENTER_PROJECT_ID=str(ObjectId()))

    response = client.get("/relatorio")

    assert response.status_code == 503
    assert "private-host" not in response.get_data(as_text=True)
