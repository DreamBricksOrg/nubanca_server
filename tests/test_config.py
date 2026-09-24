from app.config import Config


def test_config_has_s3_settings_with_sane_defaults():
    assert Config.AWS_REGION == "us-east-1"
    assert Config.S3_PRESIGNED_URL_EXPIRES == 86400
    assert hasattr(Config, "AWS_ACCESS_KEY_ID")
    assert hasattr(Config, "AWS_SECRET_ACCESS_KEY")
    assert hasattr(Config, "AWS_S3_BUCKET")


def test_config_defaults_event_location_to_empty_string():
    assert Config.EVENT_LOCATION == ""


def test_config_has_print_settings_with_sane_defaults():
    assert Config.SUMATRA_PATH == "SumatraPDF.exe"
    assert Config.PRINTER_NAME == ""
    assert Config.PRINT_SETTINGS == "fit,portrait"
    assert Config.PRINT_TIMEOUT == 60
