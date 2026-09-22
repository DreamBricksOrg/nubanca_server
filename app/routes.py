from flask import Blueprint, abort, current_app, jsonify, request, send_from_directory

from . import printing, storage

bp = Blueprint("main", __name__)


@bp.get("/image")
def get_image():
    """Poll for a newly captured photo.
    ---
    tags:
      - photos
    responses:
      200:
        description: A new capture was promoted to photos/ and is returned.
        schema:
          type: object
          properties:
            image_url:
              type: string
              example: http://localhost:5000/files/photos/20260921_143201.jpg
      404:
        description: No new capture is waiting in captures/.
        schema:
          type: object
          properties:
            success:
              type: boolean
              example: false
            message:
              type: string
              example: Nenhuma imagem nova disponível
    """
    root = current_app.config["STORAGE_ROOT"]
    dest = storage.promote_latest_capture(root / "captures", root / "photos")
    if dest is None:
        return jsonify({"success": False, "message": "Nenhuma imagem nova disponível"}), 404

    base_url = current_app.config["BASE_URL"].rstrip("/")
    image_url = f"{base_url}/files/photos/{dest.name}"
    return jsonify({"image_url": image_url})


@bp.post("/discard")
def discard_image():
    """Discard the most recent photo.
    ---
    tags:
      - photos
    responses:
      200:
        description: The most recent photo was moved to discards/.
        schema:
          type: object
          properties:
            success:
              type: boolean
              example: true
            message:
              type: string
              example: Foto descartada
      404:
        description: There is no photo to discard.
        schema:
          type: object
          properties:
            success:
              type: boolean
              example: false
            message:
              type: string
              example: Nenhuma foto para descartar
    """
    root = current_app.config["STORAGE_ROOT"]
    dest = storage.discard_latest_photo(root / "photos", root / "discards")
    if dest is None:
        return jsonify({"success": False, "message": "Nenhuma foto para descartar"}), 404
    return jsonify({"success": True, "message": "Foto descartada"})


@bp.post("/print")
def print_image_route():
    """Upload the final treated image and save it for printing.
    ---
    tags:
      - print
    consumes:
      - multipart/form-data
    parameters:
      - name: image
        in: formData
        type: file
        required: true
        description: The final collage image (.jpg, .jpeg or .png).
    responses:
      200:
        description: Image saved to back-covers/ (printing itself is stubbed).
        schema:
          type: object
          properties:
            success:
              type: boolean
              example: true
            message:
              type: string
              example: Imagem salva em back-covers; impressão ainda não implementada (stub)
      400:
        description: No file sent, or its extension isn't allowed.
        schema:
          type: object
          properties:
            success:
              type: boolean
              example: false
            message:
              type: string
              example: Extensão de arquivo não permitida
    """
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
    """Serve a stored image file.
    ---
    tags:
      - files
    parameters:
      - name: folder
        in: path
        type: string
        required: true
        enum: [captures, photos, discards, back-covers]
      - name: filename
        in: path
        type: string
        required: true
    produces:
      - image/jpeg
      - image/png
    responses:
      200:
        description: The requested file.
      404:
        description: Unknown folder, or the file doesn't exist.
    """
    # send_from_directory (werkzeug's safe_join) already rejects ".." traversal
    # and path separators in `filename`, so no extra secure_filename() call is
    # needed on top of this folder allowlist.
    if folder not in storage.FOLDERS:
        abort(404)
    root = current_app.config["STORAGE_ROOT"]
    return send_from_directory(root / folder, filename)
