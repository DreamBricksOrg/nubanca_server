import pytest

from app import create_app
from app.config import Config


@pytest.fixture
def app(tmp_path):
    class TestConfig(Config):
        STORAGE_ROOT = tmp_path
        BASE_URL = "http://testserver"

    application = create_app(TestConfig)
    application.config["TESTING"] = True
    return application


@pytest.fixture
def client(app):
    return app.test_client()
