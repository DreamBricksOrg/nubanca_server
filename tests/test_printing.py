from pathlib import Path

from app.printing import print_image


def test_print_image_stub_returns_not_printed(tmp_path):
    fake_file = tmp_path / "cover.jpg"
    fake_file.write_bytes(b"x")

    result = print_image(fake_file)

    assert result == {
        "printed": False,
        "message": "Impressão ainda não implementada (stub)",
    }
