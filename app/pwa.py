from flask import Blueprint, current_app, render_template, send_from_directory

bp = Blueprint("pwa", __name__)


@bp.get("/manifest.webmanifest")
def manifest():
    response = send_from_directory(current_app.static_folder, "manifest.webmanifest", mimetype="application/manifest+json")
    response.headers["Cache-Control"] = "no-cache"
    return response


@bp.get("/sw.js")
def service_worker():
    # Served from the root so the worker's scope covers every page.
    response = send_from_directory(current_app.static_folder, "sw.js", mimetype="text/javascript")
    response.headers["Cache-Control"] = "no-cache"
    response.headers["Service-Worker-Allowed"] = "/"
    return response


@bp.get("/offline")
def offline():
    return render_template("offline.html")
