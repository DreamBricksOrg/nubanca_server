from app.storage import FOLDERS


def test_create_app_creates_all_storage_folders(app):
    root = app.config["STORAGE_ROOT"]

    for name in FOLDERS:
        assert (root / name).is_dir()
