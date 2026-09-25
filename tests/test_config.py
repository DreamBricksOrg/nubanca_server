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
    assert Config.PRINT_ENABLED is True
    assert Config.SUMATRA_PATH == "SumatraPDF.exe"
    assert Config.PRINTER_NAME == ""
    assert Config.PRINT_SETTINGS == "noscale,paper=A4,center"
    assert Config.PRINT_TIMEOUT == 60
    assert Config.PRINT_DPI == 300
    assert Config.PRINT_MARGIN_MM == 6


def test_config_has_imagemagick_settings_with_sane_defaults():
    assert Config.IMAGEMAGICK_ENABLED is True
    assert Config.IMAGEMAGICK_PATH == "magick"
    assert Config.IMAGEMAGICK_ARGS == ""
    assert Config.IMAGEMAGICK_TIMEOUT == 60
