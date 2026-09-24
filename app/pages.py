from flask import Blueprint, render_template
import os
from dotenv import load_dotenv
bp = Blueprint("pages", __name__, template_folder='../templates')

@bp.get("/editor")
def open_editor():
    return render_template('editor.html', name="editor", server_url=os.getenv("BASE_URL"))

@bp.get("/termos")
def open_terms():
    return render_template('termos.html', name="termos", server_url=os.getenv("BASE_URL"))

@bp.get("/qrcode")
def open_qrcode():
    return render_template('qrcode.html', name="qrcode", server_url=os.getenv("BASE_URL"))

@bp.get("/validacao")
def open_validacao():
    return render_template('validacao.html', name="validacao", server_url=os.getenv("BASE_URL"))