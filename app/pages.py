from flask import Blueprint, render_template

bp = Blueprint("pages", __name__, template_folder='../templates')

@bp.get("/editor")
def open_editor():
    return render_template('editor.html', name="editor")

@bp.get("/termos")
def open_terms():
    return render_template('termos.html', name="termos")

@bp.get("/qrcode")
def open_qrcode():
    return render_template('qrcode.html', name="qrcode")

@bp.get("/validacao")
def open_validacao():
    return render_template('validacao.html', name="validacao")