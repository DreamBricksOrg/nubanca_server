from flasgger import Swagger
from flask import Flask

from .config import Config
from .storage import ensure_folders

SWAGGER_CONFIG = {
    "headers": [],
    "specs": [
        {
            "endpoint": "apispec",
            "route": "/apispec.json",
            "rule_filter": lambda rule: True,
            "model_filter": lambda tag: True,
        }
    ],
    "static_url_path": "/flasgger_static",
    "swagger_ui": True,
    "specs_route": "/docs/",
}

SWAGGER_TEMPLATE = {
    "info": {
        "title": "Photo Print API",
        "description": "API para captura, tratamento e impressão de fotos.",
        "version": "1.0.0",
    }
}


def create_app(config_class=Config):
    app = Flask(__name__)
    app.config.from_object(config_class)
    ensure_folders(app.config["STORAGE_ROOT"])

    from .routes import bp
    app.register_blueprint(bp)

    Swagger(app, config=SWAGGER_CONFIG, template=SWAGGER_TEMPLATE)

    return app
