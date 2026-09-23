import time
from datetime import datetime

from app.storage import ensure_folders, FOLDERS, is_allowed_extension, list_image_files, most_recent_file, build_timestamped_filename, promote_latest_capture


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


def test_most_recent_file_returns_none_when_folder_empty(tmp_path):
    assert most_recent_file(tmp_path) is None


def test_most_recent_file_returns_the_newest_by_mtime(tmp_path):
    older = tmp_path / "older.jpg"
    older.write_bytes(b"x")
    time.sleep(0.01)
    newer = tmp_path / "newer.jpg"
    newer.write_bytes(b"x")

    assert most_recent_file(tmp_path) == newer


def test_build_timestamped_filename_uses_given_moment(tmp_path):
    moment = datetime(2026, 9, 21, 14, 32, 1)

    name = build_timestamped_filename(".jpg", tmp_path, moment=moment)

    assert name == "20260921_143201.jpg"


def test_build_timestamped_filename_avoids_collisions(tmp_path):
    moment = datetime(2026, 9, 21, 14, 32, 1)
    (tmp_path / "20260921_143201.jpg").write_bytes(b"x")

    name = build_timestamped_filename(".jpg", tmp_path, moment=moment)

    assert name == "20260921_143201_1.jpg"


def test_promote_latest_capture_returns_none_when_captures_empty(tmp_path):
    captures = tmp_path / "captures"
    photos = tmp_path / "photos"
    captures.mkdir()
    photos.mkdir()

    assert promote_latest_capture(captures, photos) is None


def test_promote_latest_capture_moves_and_renames_single_file(tmp_path):
    captures = tmp_path / "captures"
    photos = tmp_path / "photos"
    captures.mkdir()
    photos.mkdir()
    (captures / "DSC0001.jpg").write_bytes(b"x")

    dest = promote_latest_capture(captures, photos)

    assert dest.parent == photos
    assert dest.exists()
    assert not (captures / "DSC0001.jpg").exists()
    assert list(captures.iterdir()) == []


def test_promote_latest_capture_keeps_only_the_newest_and_deletes_others(tmp_path):
    captures = tmp_path / "captures"
    photos = tmp_path / "photos"
    captures.mkdir()
    photos.mkdir()
    (captures / "older.jpg").write_bytes(b"x")
    time.sleep(0.01)
    (captures / "newer.jpg").write_bytes(b"x")

    dest = promote_latest_capture(captures, photos)

    assert dest.exists()
    assert list(captures.iterdir()) == []
    assert len(list(photos.iterdir())) == 1


from app.storage import discard_latest_photo, save_uploaded_image
import io
from werkzeug.datastructures import FileStorage


def test_discard_latest_photo_returns_none_when_photos_empty(tmp_path):
    photos = tmp_path / "photos"
    discards = tmp_path / "discards"
    photos.mkdir()
    discards.mkdir()

    assert discard_latest_photo(photos, discards) is None


def test_discard_latest_photo_moves_newest_file_keeping_its_name(tmp_path):
    photos = tmp_path / "photos"
    discards = tmp_path / "discards"
    photos.mkdir()
    discards.mkdir()
    (photos / "older.jpg").write_bytes(b"x")
    time.sleep(0.01)
    (photos / "20260921_143201.jpg").write_bytes(b"x")

    dest = discard_latest_photo(photos, discards)

    assert dest == discards / "20260921_143201.jpg"
    assert dest.exists()
    assert (photos / "older.jpg").exists()
    assert not (photos / "20260921_143201.jpg").exists()


def test_save_uploaded_image_raises_for_missing_file(tmp_path):
    dest_folder = tmp_path / "back-covers"
    dest_folder.mkdir()

    try:
        save_uploaded_image(None, dest_folder)
        assert False, "expected ValueError"
    except ValueError:
        pass


def test_save_uploaded_image_raises_for_disallowed_extension(tmp_path):
    dest_folder = tmp_path / "back-covers"
    dest_folder.mkdir()
    upload = FileStorage(stream=io.BytesIO(b"x"), filename="final.gif")

    try:
        save_uploaded_image(upload, dest_folder)
        assert False, "expected ValueError"
    except ValueError:
        pass


def test_save_uploaded_image_saves_with_timestamped_name(tmp_path):
    dest_folder = tmp_path / "back-covers"
    dest_folder.mkdir()
    upload = FileStorage(stream=io.BytesIO(b"binary-image-data"), filename="final.jpg")

    dest = save_uploaded_image(upload, dest_folder)

    assert dest.parent == dest_folder
    assert dest.exists()
    assert dest.read_bytes() == b"binary-image-data"


import re

from app.storage import build_unique_filename


def test_build_unique_filename_matches_expected_shape():
    name = build_unique_filename(".jpg")

    assert re.match(r"^\d{8}_\d{6}_[0-9a-f]{8}\.jpg$", name)


def test_build_unique_filename_generates_different_names_each_call():
    first = build_unique_filename(".jpg")
    second = build_unique_filename(".jpg")

    assert first != second