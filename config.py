import os
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent


class Config:
    APP_NAME = os.environ.get("APP_NAME", "AI Talk Builder")
    SECRET_KEY = os.environ.get("SECRET_KEY", "dev-secret-change-me")
    SQLALCHEMY_DATABASE_URI = os.environ.get(
        "DATABASE_URL", f"sqlite:///{BASE_DIR / 'dev.db'}"
    )
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    UPLOAD_FOLDER = os.environ.get("UPLOAD_FOLDER", str(BASE_DIR / "app" / "uploads"))
    MAX_CONTENT_LENGTH = 16 * 1024 * 1024
