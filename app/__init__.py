import os
from pathlib import Path

from dotenv import load_dotenv
from flask import Flask, flash, redirect, request, url_for
from flask_login import current_user

from .extensions import db, login_manager, migrate
from .models import User


BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")


def create_app():
    app = Flask(__name__, instance_relative_config=False)
    app.config.from_object("config.Config")

    Path(app.config["UPLOAD_FOLDER"]).mkdir(parents=True, exist_ok=True)

    db.init_app(app)
    migrate.init_app(app, db)
    login_manager.init_app(app)

    login_manager.login_view = "auth.login"
    login_manager.login_message_category = "warning"

    from .routes.admin import admin_bp
    from .routes.auth import auth_bp
    from .routes.main import main_bp
    from .routes.talks import talks_bp

    app.register_blueprint(main_bp)
    app.register_blueprint(auth_bp)
    app.register_blueprint(talks_bp)
    app.register_blueprint(admin_bp)

    @app.before_request
    def require_password_update():
        if not current_user.is_authenticated:
            return None

        allowed_endpoints = {
            "auth.logout",
            "auth.force_password_update",
            "static",
        }
        if request.endpoint in allowed_endpoints:
            return None

        if current_user.must_change_password:
            flash("You need to set a new password before continuing.", "warning")
            return redirect(url_for("auth.force_password_update"))
        return None

    @app.context_processor
    def inject_globals():
        return {"app_name": app.config["APP_NAME"]}

    register_cli_commands(app)
    return app


def register_cli_commands(app):
    @app.cli.command("create-admin")
    def create_admin():
        username = os.environ.get("ADMIN_USERNAME", "admin")
        email = os.environ.get("ADMIN_EMAIL", "admin@example.com")
        password = os.environ.get("ADMIN_PASSWORD", "ChangeMe123!")

        existing = User.query.filter(
            (User.username == username) | (User.email == email)
        ).first()
        if existing:
            print("Admin user already exists.")
            return

        user = User(
            username=username,
            email=email,
            is_admin=True,
            is_active=True,
            must_change_password=False,
        )
        user.set_password(password)
        db.session.add(user)
        db.session.commit()
        print(f"Created admin user '{username}' with email '{email}'.")
