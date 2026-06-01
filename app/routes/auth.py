from flask import Blueprint, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required, login_user, logout_user

from ..extensions import db
from ..models import PasswordResetRequest, User


auth_bp = Blueprint("auth", __name__, url_prefix="/auth")


@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("talks.dashboard"))

    if request.method == "POST":
        identity = request.form.get("identity", "").strip()
        password = request.form.get("password", "")

        user = User.query.filter(
            (User.username.ilike(identity)) | (User.email.ilike(identity))
        ).first()

        if not user or not user.is_active:
            flash("Invalid credentials.", "danger")
            return render_template("auth/login.html")

        temp_request = (
            PasswordResetRequest.query.filter_by(user_id=user.id, status="generated")
            .order_by(PasswordResetRequest.generated_at.desc())
            .first()
        )

        if user.check_password(password):
            login_user(user)
            return redirect(url_for("talks.dashboard"))

        if temp_request and temp_request.matches_temp_password(password):
            login_user(user)
            user.must_change_password = True
            db.session.commit()
            flash("Temporary password accepted. Please set a new password now.", "warning")
            return redirect(url_for("auth.force_password_update"))

        flash("Invalid credentials.", "danger")

    return render_template("auth/login.html")


@auth_bp.route("/logout")
@login_required
def logout():
    logout_user()
    flash("You have been signed out.", "info")
    return redirect(url_for("auth.login"))


@auth_bp.route("/request-reset", methods=["GET", "POST"])
def request_reset():
    if request.method == "POST":
        identity = request.form.get("identity", "").strip()
        note = request.form.get("note", "").strip()
        user = User.query.filter(
            (User.username.ilike(identity)) | (User.email.ilike(identity))
        ).first()

        if user:
            existing = (
                PasswordResetRequest.query.filter_by(user_id=user.id, status="pending")
                .order_by(PasswordResetRequest.created_at.desc())
                .first()
            )
            if not existing:
                reset_request = PasswordResetRequest(
                    user=user,
                    requested_by_user=True,
                    status="pending",
                    note=note or None,
                )
                db.session.add(reset_request)
                db.session.commit()

        flash(
            "If that account exists, the admin panel will now show a password reset request.",
            "info",
        )
        return redirect(url_for("auth.login"))

    return render_template("auth/request_reset.html")


@auth_bp.route("/force-password-update", methods=["GET", "POST"])
@login_required
def force_password_update():
    if request.method == "POST":
        password = request.form.get("password", "")
        confirm_password = request.form.get("confirm_password", "")

        if len(password) < 10:
            flash("Choose a password with at least 10 characters.", "danger")
            return render_template("auth/force_password_update.html")

        if password != confirm_password:
            flash("The passwords did not match.", "danger")
            return render_template("auth/force_password_update.html")

        current_user.set_password(password)
        current_user.must_change_password = False

        generated_requests = PasswordResetRequest.query.filter_by(
            user_id=current_user.id, status="generated"
        ).all()
        for reset_request in generated_requests:
            reset_request.clear_temp_password()
        db.session.commit()

        flash("Password updated successfully.", "success")
        return redirect(url_for("talks.dashboard"))

    return render_template("auth/force_password_update.html")
