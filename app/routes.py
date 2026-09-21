from flask import Blueprint, abort, current_app, jsonify, request, send_from_directory

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
    # OSError from a full/unwritable disk is intentionally left uncaught for
    # now (surfaces as a 500) — no printer hardware exists yet to exercise
    # this path for real; revisit once /print sees production traffic.

    printing.print_image(dest)
    return jsonify({
        "success": True,
        "message": "Imagem salva em back-covers; impressão ainda não implementada (stub)",
    })


@bp.get("/files/<folder>/<filename>")
def serve_file(folder, filename):
    # send_from_directory (werkzeug's safe_join) already rejects ".." traversal
    # and path separators in `filename`, so no extra secure_filename() call is
    # needed on top of this folder allowlist.
    if folder not in storage.FOLDERS:
        abort(404)
    root = current_app.config["STORAGE_ROOT"]
    return send_from_directory(root / folder, filename)
