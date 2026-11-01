import html as html_module
import json
import re

import boto3


def test_editor_print_and_digital_labels_and_secondary_style(client):
    html = client.get("/editor").get_data(as_text=True)

    assert 'id="saveImage" class="btn btn-primary">Imprimir</button>' in html
    assert 'id="qrcodeOnly" type="button" class="btn btn-secondary">Apenas Digital</button>' in html
    assert html.index('id="saveImage"') < html.index('id="qrcodeOnly"')


def test_editor_and_gallery_share_scoped_history_script(client, app):
    app.config["EVENT_LOCATION"] = "sp"
    app.config["PRINTER_NAME"] = "Printer A"
    for route, script in [("/editor", "editor.js"), ("/photos", "photos.js")]:
        html = client.get(route).get_data(as_text=True)
        match = re.search(r'data-print-scope="([^"]+)"', html)
        assert match
        assert json.loads(html_module.unescape(match.group(1))) == [
            app.config["AWS_S3_BUCKET"], "sp", "Printer A"
        ]
        assert html.index("/static/js/print_history.js") < html.index(f"/static/js/{script}")
    assert client.get("/static/js/print_history.js").status_code == 200


def test_gallery_has_estimate_button_and_local_history_notice(client, app):
    s3 = boto3.client("s3", region_name=app.config["AWS_REGION"])
    s3.put_object(Bucket=app.config["AWS_S3_BUCKET"], Key="back-covers/20261031_120000_abcd.png", Body=b"photo")
    html = client.get("/photos").get_data(as_text=True)

    assert 'class="btn btn-secondary estimate-photo"' in html
    assert '>Estimar horário</button>' in html
    assert 'class="print-estimate"' in html
    assert 'class="print-history-label"' in html
    assert "3min30s" in html
    assert "neste navegador" in html
    assert "não confirma" in html


def test_changed_assets_bypass_old_service_worker_cache_entries(client):
    for route, assets in [
        ("/editor", ["css/editor.css", "js/editor.js", "js/print_history.js"]),
        ("/photos", ["css/photos.css", "js/photos.js", "js/print_history.js"]),
        ("/qrcode", ["js/qrcode.js"]),
    ]:
        html = client.get(route).get_data(as_text=True)
        for asset in assets:
            assert f"/static/{asset}?v=print-history-1" in html
