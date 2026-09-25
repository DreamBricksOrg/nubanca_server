from dotenv import load_dotenv

load_dotenv(override=True)

from app import create_app  # noqa: E402 (must load .env before Config is evaluated)

app = create_app()

if __name__ == "__main__":
    app.run(host=app.config["HOST"], port=app.config["PORT"])
