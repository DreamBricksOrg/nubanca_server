import json
from pathlib import Path

import mongomock
import boto3
from bson import ObjectId
from moto import mock_aws


def test_export_produces_minimal_linkable_jsonl_without_personal_data(tmp_path):
    from scripts.export_report import export_events

    project = ObjectId()
    logs = mongomock.MongoClient().logcenter_prod.logs
    logs.insert_many([
        {"project_id": project, "message": "imprimir_imagem_sucesso", "timestamp": "2026-11-01T13:00:00Z",
         "data": {"event_location": "rj", "file": "secret-photo.jpg", "ip": "192.0.2.1"}},
        {"project_id": project, "message": "visualizar_foto_acessada", "timestamp": "2026-11-01T13:00:30Z",
         "data": {"event_location": "rj", "filename": "secret-photo.jpg", "user_agent": "PrivateBrowser"}},
        {"project_id": project, "message": "apenas_qrcode_gerado", "timestamp": "2026-11-01T14:00:00+00:00",
         "data": {"event_location": "sp", "file": "digital.jpg"}},
        {"project_id": ObjectId(), "message": "imprimir_imagem_sucesso", "timestamp": "2026-11-01T13:00:00Z",
         "data": {"event_location": "rj", "file": "other-project.jpg"}},
        {"project_id": project, "message": "error_with_secret", "timestamp": "2026-11-01T13:00:00Z",
         "data": {"event_location": "rj", "error": "private-token"}},
    ])
    output = tmp_path / "logs.jsonl"

    count = export_events(logs, output, project,
                          {"back-covers/rj/secret-photo.jpg", "back-covers/sp/digital.jpg"}, hash_key=b"test-key")

    rows = [json.loads(line) for line in output.read_text(encoding="utf-8").splitlines()]
    assert count == len(rows) == 3
    assert all(set(row) == {"timestamp", "message", "location", "photo_id", "removed"} for row in rows)
    assert rows[0]["photo_id"] == rows[1]["photo_id"]
    assert rows[0]["photo_id"] != rows[2]["photo_id"]
    assert rows[0]["timestamp"] == "2026-11-01T13:00:00Z"
    assert {row["location"] for row in rows} == {"sp", "rj"}
    text = output.read_text(encoding="utf-8")
    for secret in ("secret-photo.jpg", "other-project.jpg", "192.0.2.1", "PrivateBrowser", "private-token"):
        assert secret not in text


def test_bundle_copies_static_assets_without_embedded_credentials(tmp_path):
    from scripts.export_report import build_bundle

    destination = tmp_path / "site"
    build_bundle(destination)

    for name in ("index.html", "js/report.js", "css/reports.css", "img/logo-white.png",
                 "fonts/NuSansText-Regular.ttf", "fonts/NuSansText-Bold.ttf"):
        assert (destination / name).is_file(), name
    assert "logs.jsonl" in (destination / "js/report.js").read_text(encoding="utf-8")
    assert not (destination / "logs.jsonl").exists()

def test_export_marks_only_missing_generated_objects_without_exposing_filenames(tmp_path):
    from scripts.export_report import export_events

    project = ObjectId()
    logs = mongomock.MongoClient().logcenter_prod.logs
    logs.insert_many([
        {"project_id": project, "message": "imprimir_imagem_sucesso", "timestamp": "2026-11-01T17:57:45Z",
         "data": {"event_location": "rj", "file": "removed.png"}},
        {"project_id": project, "message": "apenas_qrcode_gerado", "timestamp": "2026-11-01T18:00:00Z",
         "data": {"event_location": "rj", "file": "present.png"}},
        {"project_id": project, "message": "reimprimir_imagem_sucesso", "timestamp": "2026-11-01T18:01:00Z",
         "data": {"event_location": "rj", "file": "back-covers/rj/removed.png"}},
        {"project_id": project, "message": "apenas_qrcode_gerado", "timestamp": "2026-11-01T18:02:00Z",
         "data": {"event_location": "sp", "file": "present.png"}},
    ])
    output = tmp_path / "logs.jsonl"

    export_events(logs, output, project, existing_keys={"back-covers/rj/present.png",
                                                    "back-covers/sp/present.png"}, hash_key=b"test-key")

    rows = [json.loads(line) for line in output.read_text(encoding="utf-8").splitlines()]
    assert [row["removed"] for row in rows] == [True, False, None, False]
    assert all(set(row) == {"timestamp", "message", "location", "photo_id", "removed"} for row in rows)
    assert "removed.png" not in output.read_text(encoding="utf-8")

def test_export_lists_every_cover_key_across_s3_pages_and_both_locations():
    from scripts.export_report import list_existing_cover_keys

    with mock_aws():
        s3 = boto3.client("s3", region_name="us-east-1")
        s3.create_bucket(Bucket="report-test-bucket")
        for index in range(1001):
            s3.put_object(Bucket="report-test-bucket", Key=f"back-covers/rj/{index}.jpg", Body=b"x")
        s3.put_object(Bucket="report-test-bucket", Key="back-covers/sp/one.jpg", Body=b"x")
        s3.put_object(Bucket="report-test-bucket", Key="back-covers/other.jpg", Body=b"x")

        keys = list_existing_cover_keys(s3, "report-test-bucket")

        assert len(keys) == 1002
        assert "back-covers/rj/1000.jpg" in keys
        assert "back-covers/sp/one.jpg" in keys
        assert "back-covers/other.jpg" not in keys
