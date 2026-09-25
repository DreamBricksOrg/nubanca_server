from flask import Blueprint, abort, current_app, jsonify, render_template, request, send_from_directory

from . import imagemagick, printing, s3_storage, storage

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

    try:
        imagemagick.apply_treatment(dest)
    except imagemagick.TreatmentError as exc:
        current_app.logger.error("Falha ao tratar imagem %s: %s", dest, exc)

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
        description: Image saved to back-covers/ and sent to the printer.
        schema:
          type: object
          properties:
            success:
              type: boolean
              example: true
            message:
              type: string
              example: Imagem salva em back-covers e enviada para impressão
            page_url:
              type: string
              example: http://localhost:5000/view/20260922_143201.jpg
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
    file_storage = request.files.get("image")

    try:
        temp_path = storage.save_uploaded_image_to_tempfile(file_storage)
    except ValueError as exc:
        return jsonify({"success": False, "message": str(exc)}), 400

    try:
        try:
            print_result = printing.print_image(temp_path)
        except printing.PrintError as exc:
            current_app.logger.error("Falha ao imprimir %s: %s", temp_path, exc)
            print_result = {"printed": False, "message": str(exc)}

        filename = storage.build_unique_filename(temp_path.suffix)
        s3_storage.upload_file(temp_path, s3_storage.back_cover_key(filename))
    finally:
        temp_path.unlink(missing_ok=True)

    base_url = current_app.config["BASE_URL"].rstrip("/")
    if print_result["printed"]:
        message = "Imagem salva em back-covers e enviada para impressão"
    else:
        message = f"Imagem salva em back-covers; falha ao imprimir ({print_result['message']})"
    return jsonify({
        "success": True,
        "message": message,
        "page_url": f"{base_url}/view/{filename}",
    })


@bp.get("/view/<filename>")
def view_photo(filename):
    """Branded mobile page to view, share and download a printed photo.
    ---
    tags:
      - print
    parameters:
      - name: filename
        in: path
        type: string
        required: true
    produces:
      - text/html
    responses:
      200:
        description: HTML page with the photo, a share button and a download button.
      404:
        description: The file doesn't exist in back-covers/.
    """
    key = s3_storage.back_cover_key(filename)
    if not s3_storage.object_exists(key):
        abort(404)

    expires_in = current_app.config["S3_PRESIGNED_URL_EXPIRES"]
    image_url = s3_storage.generate_presigned_url(key, filename, expires_in)
    download_url = s3_storage.generate_presigned_url(key, filename, expires_in, download=True)
    return render_template("view.html", filename=filename, image_url=image_url, download_url=download_url)


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
        enum: [captures, photos, discards]
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
