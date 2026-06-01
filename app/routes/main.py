from flask import Blueprint, redirect, render_template, url_for
from flask_login import current_user


main_bp = Blueprint("main", __name__)


@main_bp.route("/")
def index():
    if current_user.is_authenticated:
        return redirect(url_for("talks.dashboard"))
    return render_template("landing.html")
