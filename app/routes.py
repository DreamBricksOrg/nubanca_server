import tempfile
from pathlib import Path

from botocore.exceptions import BotoCoreError, ClientError
from flask import Blueprint, abort, current_app, jsonify, redirect, render_template, request, send_from_directory, url_for

from .event_types import EventType

from . import imagemagick, printing, s3_storage, storage
from .logcenter import log_event, log_event_v3

bp = Blueprint("main", __name__)


def device_info():
    """Dados do aparelho que fez a requisição, para o campo "data" dos logs."""
    ua = request.user_agent
    return {
        "user_agent": ua.string,
        "browser": ua.browser,
        "platform": ua.platform,
        "ip": request.remote_addr,
    }


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
        log_event("ERROR", "tratamento_imagem_falhou", data={"file": dest.name, "error": str(exc)})
        log_event_v3(f"ERROR: tratamento_imagem_falhou | \"file\": {dest.name}, \"error\": {str(exc)}", True)

    base_url = request.host_url.rstrip("/")
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
        log_event("DEBUG", "descartar_imagem_chamada", status=404)
        log_event_v3("DEBUG: descartar_imagem_chamada | status=404", True)
        return jsonify({"success": False, "message": "Nenhuma foto para descartar"}), 404
    log_event("DEBUG", "descartar_imagem_chamada", status=200)
    log_event_v3("DEBUG: descartar_imagem_chamada | status=200", True)
    
    return jsonify({"success": True, "message": "Foto descartada"})


@bp.post("/print")
def print_image_route():
    """Upload the final treated image, optionally skipping printing for QR Code only.
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
      - name: print
        in: formData
        type: boolean
        default: true
        description: Set to false to save the image for QR Code without printing.
    responses:
      200:
        description: Image saved to back-covers/ and optionally sent to the printer.
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
    should_print = request.form.get("print", "true") != "false"

    try:
        temp_path = storage.save_uploaded_image_to_tempfile(file_storage)
    except ValueError as exc:
        log_event("DEBUG", "imprimir_imagem_chamada", status=400)
        log_event_v3("DEBUG: imprimir_imagem_chamada | status=400", True)
        
        return jsonify({"success": False, "message": str(exc)}), 400

    print_result = {"printed": False, "message": "Impressão não solicitada"}
    try:
        if should_print:
            try:
                print_result = printing.print_image(temp_path)
            except printing.PrintError as exc:
                log_event("ERROR", "imprimir_imagem_falhou", data={"file": temp_path.name, "error": str(exc)})
                log_event_v3(f"ERROR: imprimir_imagem_falhou | \"file\": {temp_path.name}, \"error\": {str(exc)}", True)

                print_result = {"printed": False, "message": str(exc)}

        filename = storage.build_unique_filename(temp_path.suffix)
        s3_storage.upload_file(temp_path, s3_storage.back_cover_key(filename))
    finally:
        temp_path.unlink(missing_ok=True)

    base_url = current_app.config["BASE_URL"].rstrip("/")
    if not should_print:
        message = "Imagem salva em back-covers; apenas QR Code"
        log_event("INFO", "apenas_qrcode_gerado", data={"file": filename}, status=200)
        log_event_v3(f"INFO: apenas_qrcode_gerado | \"file\": {filename}", True)
    elif print_result["printed"]:
        message = "Imagem salva em back-covers e enviada para impressão"
        log_event("INFO", "imprimir_imagem_sucesso", data={"file": filename}, status=200)
        log_event_v3(EventType.imprimir_imagem_sucesso.generate_payload(data={"file": filename}))
    else:
        message = f"Imagem salva em back-covers; falha ao imprimir ({print_result['message']})"
    log_event("DEBUG", "imprimir_imagem_chamada", status=200)
    log_event_v3("DEBUG: imprimir_imagem_chamada | status=200", True)

    return jsonify({
        "success": True,
        "message": message,
        "page_url": f"{base_url}/view/{filename}",
    })


@bp.get("/photos")
def photo_gallery():
    """List all photos in the configured S3 bucket and back-cover prefix.
    ---
    tags:
      - photos
    produces:
      - text/html
    responses:
      200:
        description: Photo gallery with a print button beneath each image.
      502:
        description: Could not list the configured S3 folder.
    """
    try:
        photos = s3_storage.list_back_covers()
        expires_in = current_app.config["S3_PRESIGNED_URL_EXPIRES"]
        for photo in photos:
            photo["image_url"] = s3_storage.generate_presigned_url(
                photo["key"], photo["filename"], expires_in
            )
    except (BotoCoreError, ClientError) as exc:
        log_event("ERROR", "listar_fotos_falhou", data={"error": str(exc)}, status=502)
        return render_template(
            "photos.html", photos=[], error="Não foi possível carregar as fotos. Verifique a configuração do S3."
        ), 502
    return render_template("photos.html", photos=photos)


@bp.post("/photos/print")
def print_stored_photo():
    """Print an existing image from the configured S3 folder without uploading it again.
    ---
    tags:
      - photos
    consumes:
      - application/json
    parameters:
      - name: body
        in: body
        required: true
        schema:
          type: object
          required: [key]
          properties:
            key:
              type: string
              description: Full S3 key returned in the photo gallery.
    responses:
      200:
        description: Original image sent to the configured printer.
      400:
        description: Invalid image key or key outside the configured prefix.
      404:
        description: Image no longer exists in S3.
      409:
        description: Printing is disabled.
      502:
        description: S3 download or printer dispatch failed.
    """
    payload = request.get_json(silent=True)
    key = payload.get("key") if isinstance(payload, dict) else None
    if not isinstance(key, str) or not s3_storage.is_back_cover_image_key(key):
        return jsonify({"success": False, "message": "Foto inválida ou fora da pasta configurada"}), 400
    if not current_app.config.get("PRINT_ENABLED", True):
        return jsonify({"success": False, "printed": False, "message": "Impressão desabilitada"}), 409
    try:
        with tempfile.TemporaryDirectory(prefix="nubanca-print-") as directory:
            local_path = Path(directory) / f"photo{Path(key).suffix.lower()}"
            s3_storage.download_file(local_path, key)
            result = printing.print_image(local_path)
    except (BotoCoreError, ClientError, printing.PrintError, OSError) as exc:
        missing = isinstance(exc, ClientError) and exc.response.get("Error", {}).get("Code") in ("404", "NoSuchKey")
        status = 404 if missing else 502
        message = "Foto não encontrada" if missing else "Não foi possível imprimir a foto. Verifique o S3 e a impressora."
        log_event("ERROR", "reimprimir_imagem_falhou", data={"file": key, "error": str(exc)}, status=status)
        log_event_v3(f"ERROR: reimprimir_imagem_falhou | \"file\": {key}, \"error\": {str(exc)}", True)
        return jsonify({"success": False, "printed": False, "message": message}), status
    if not result["printed"]:
        return jsonify({"success": False, **result}), 409
    log_event("INFO", "reimprimir_imagem_sucesso", data={"file": key}, status=200)
    log_event_v3(f"INFO: reimprimir_imagem_sucesso | \"file\": {key}", True)
    return jsonify({"success": True, **result})


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
    download_url = url_for("main.download_photo", filename=filename)

    log_event("INFO", "visualizar_foto_acessada", data={"filename": filename, **device_info()}, status=200)
    log_event_v3(EventType.visualizar_foto_acessada.generate_payload(data={"filename": filename, **device_info()}))
    
    return render_template("view.html", filename=filename, image_url=image_url, download_url=download_url)


@bp.post("/view/<filename>/share")
def share_photo(filename):
    """Log the share action triggered from the /view page.
    ---
    tags:
      - print
    parameters:
      - name: filename
        in: path
        type: string
        required: true
    responses:
      204:
        description: Share event logged.
    """
    log_event("INFO", "compartilhar_imagem", data={"filename": filename, **device_info()}, status=204)
    log_event_v3(EventType.compartilhar_imagem.generate_payload(data={"filename": filename, **device_info()}))
    return "", 204


@bp.get("/view/<filename>/download")
def download_photo(filename):
    """Log the download and redirect to a presigned S3 download URL.
    ---
    tags:
      - print
    parameters:
      - name: filename
        in: path
        type: string
        required: true
    responses:
      302:
        description: Redirects to a presigned S3 URL with a download disposition.
      404:
        description: The file doesn't exist in back-covers/.
    """
    key = s3_storage.back_cover_key(filename)
    if not s3_storage.object_exists(key):
        abort(404)

    expires_in = current_app.config["S3_PRESIGNED_URL_EXPIRES"]
    download_url = s3_storage.generate_presigned_url(key, filename, expires_in, download=True)

    log_event("INFO", "baixar_imagem", data={"filename": filename, **device_info()}, status=302)
    log_event_v3(EventType.baixar_imagem.generate_payload(data={"filename": filename, **device_info()}))
    return redirect(download_url, code=302)


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
        log_event("DEBUG", "servir_arquivo_chamada", status=404, data={"folder": folder, "filename": filename})
        log_event_v3(f"DEBUG: servir_arquivo_chamada, status=404, data=\"folder\": {folder}, \"filename\": {filename}", True)
        abort(404)
    root = current_app.config["STORAGE_ROOT"]
    log_event("DEBUG", "servir_arquivo_chamada", status=200, data={"folder": folder, "filename": filename})
    log_event_v3(f"DEBUG: servir_arquivo_chamada, status=200, data=\"folder\": {folder}, \"filename\": {filename}", True)
    return send_from_directory(root / folder, filename)
