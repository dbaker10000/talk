from flask import Blueprint, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required

from ..extensions import db
from ..models import PasswordResetRequest, User
from ..utils import admin_required, generate_temp_password


admin_bp = Blueprint("admin", __name__, url_prefix="/admin")


@admin_bp.before_request
@login_required
def ensure_admin():
    admin_required()


@admin_bp.route("/users")
def users():
    users = User.query.order_by(User.username.asc()).all()
    pending_requests = PasswordResetRequest.query.filter(
        PasswordResetRequest.status.in_(["pending", "generated"])
    ).order_by(PasswordResetRequest.created_at.desc()).all()
    return render_template(
        "admin/users.html",
        users=users,
        pending_requests=pending_requests,
    )


@admin_bp.route("/users/create", methods=["POST"])
def create_user():
    username = request.form.get("username", "").strip()
    email = request.form.get("email", "").strip().lower()
    password = request.form.get("password", "")
    is_admin = bool(request.form.get("is_admin"))

    if not username or not email or not password:
        flash("Username, email, and password are required.", "danger")
        return redirect(url_for("admin.users"))

    existing = User.query.filter((User.username == username) | (User.email == email)).first()
    if existing:
        flash("That username or email is already in use.", "danger")
        return redirect(url_for("admin.users"))

    user = User(
        username=username,
        email=email,
        is_admin=is_admin,
        is_active=True,
    )
    user.set_password(password)
    db.session.add(user)
    db.session.commit()
    flash("User created.", "success")
    return redirect(url_for("admin.users"))


@admin_bp.route("/users/<int:user_id>/toggle-active", methods=["POST"])
def toggle_active(user_id):
    user = User.query.get_or_404(user_id)
    if user.id == current_user.id:
        flash("You cannot disable your own account.", "danger")
        return redirect(url_for("admin.users"))

    user.is_active = not user.is_active
    db.session.commit()
    flash("User status updated.", "success")
    return redirect(url_for("admin.users"))


@admin_bp.route("/users/<int:user_id>/delete", methods=["POST"])
def delete_user(user_id):
    user = User.query.get_or_404(user_id)
    if user.id == current_user.id:
        flash("You cannot delete your own account.", "danger")
        return redirect(url_for("admin.users"))

    db.session.delete(user)
    db.session.commit()
    flash("User deleted.", "success")
    return redirect(url_for("admin.users"))


@admin_bp.route("/users/<int:user_id>/reset-password", methods=["POST"])
def reset_password(user_id):
    user = User.query.get_or_404(user_id)
    temp_password = generate_temp_password()

    reset_request = (
        PasswordResetRequest.query.filter_by(user_id=user.id, status="pending")
        .order_by(PasswordResetRequest.created_at.desc())
        .first()
    )
    if not reset_request:
        reset_request = PasswordResetRequest(
            user=user,
            requested_by_user=False,
            status="pending",
        )
        db.session.add(reset_request)

    reset_request.admin = current_user
    reset_request.set_temp_password(temp_password)
    user.must_change_password = True
    db.session.commit()

    flash(f"Temporary password generated for {user.username}.", "success")
    return redirect(url_for("admin.users"))
