from app.storage import ensure_folders, FOLDERS


def test_ensure_folders_creates_all_expected_subfolders(tmp_path):
    ensure_folders(tmp_path)

    for name in FOLDERS:
        assert (tmp_path / name).is_dir()
