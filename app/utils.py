import secrets
from pathlib import Path

from flask import abort
from flask_login import current_user
from werkzeug.utils import secure_filename


ALLOWED_REFERENCE_EXTENSIONS = {
    ".txt",
    ".md",
    ".pdf",
    ".docx",
    ".rtf",
}


def admin_required():
    if not current_user.is_authenticated or not current_user.is_admin:
        abort(403)


def talk_access_required(talk):
    if current_user.is_admin or talk.owner_id == current_user.id:
        return
    abort(403)


def generate_temp_password(length=12):
    alphabet = "ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz23456789"
    return "".join(secrets.choice(alphabet) for _ in range(length))


def unique_upload_name(filename: str) -> str:
    safe_name = secure_filename(filename)
    return f"{secrets.token_hex(12)}_{safe_name}"


def is_allowed_reference_file(filename: str) -> bool:
    return Path(filename).suffix.lower() in ALLOWED_REFERENCE_EXTENSIONS
