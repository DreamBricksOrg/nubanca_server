from flask import Flask

from .config import Config
from .storage import ensure_folders


def create_app(config_class=Config):
    app = Flask(__name__)
    app.config.from_object(config_class)
    ensure_folders(app.config["STORAGE_ROOT"])

    from .routes import bp
    app.register_blueprint(bp)

    return app
