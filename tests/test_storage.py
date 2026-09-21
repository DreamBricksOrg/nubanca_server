from app.storage import ensure_folders, FOLDERS, is_allowed_extension, list_image_files


def test_ensure_folders_creates_all_expected_subfolders(tmp_path):
    ensure_folders(tmp_path)

    for name in FOLDERS:
        assert (tmp_path / name).is_dir()


def test_is_allowed_extension_accepts_known_image_types():
    assert is_allowed_extension("foo.jpg")
    assert is_allowed_extension("foo.JPEG")
    assert is_allowed_extension("foo.png")


def test_is_allowed_extension_rejects_other_types():
    assert not is_allowed_extension("foo.txt")
    assert not is_allowed_extension("foo")


def test_list_image_files_only_returns_allowed_images(tmp_path):
    (tmp_path / "a.jpg").write_bytes(b"x")
    (tmp_path / "b.png").write_bytes(b"x")
    (tmp_path / "notes.txt").write_bytes(b"x")

    result = {p.name for p in list_image_files(tmp_path)}

    assert result == {"a.jpg", "b.png"}