from flask import Blueprint, current_app, jsonify, request

from . import printing, storage

bp = Blueprint("main", __name__)


@bp.get("/image")
def get_image():
    root = current_app.config["STORAGE_ROOT"]
    dest = storage.promote_latest_capture(root / "captures", root / "photos")
    if dest is None:
        return "", 204

    base_url = current_app.config["BASE_URL"].rstrip("/")
    image_url = f"{base_url}/files/photos/{dest.name}"
    return jsonify({"image_url": image_url})


@bp.post("/discard")
def discard_image():
    root = current_app.config["STORAGE_ROOT"]
    dest = storage.discard_latest_photo(root / "photos", root / "discards")
    if dest is None:
        return jsonify({"success": False, "message": "Nenhuma foto para descartar"}), 404
    return jsonify({"success": True, "message": "Foto descartada"})


@bp.post("/print")
def print_image_route():
    root = current_app.config["STORAGE_ROOT"]
    file_storage = request.files.get("image")

    try:
        dest = storage.save_uploaded_image(file_storage, root / "back-covers")
    except ValueError as exc:
        return jsonify({"success": False, "message": str(exc)}), 400

    printing.print_image(dest)
    return jsonify({
        "success": True,
        "message": "Imagem salva em back-covers; impressão ainda não implementada (stub)",
    })
