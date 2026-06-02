from __future__ import annotations

from datetime import datetime

from flask_login import UserMixin
from werkzeug.security import check_password_hash, generate_password_hash

from .extensions import db, login_manager


class TimestampMixin:
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at = db.Column(
        db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False
    )


class User(UserMixin, TimestampMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    email = db.Column(db.String(255), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    is_admin = db.Column(db.Boolean, default=False, nullable=False)
    is_active = db.Column(db.Boolean, default=True, nullable=False)
    must_change_password = db.Column(db.Boolean, default=False, nullable=False)

    talks = db.relationship("Talk", back_populates="owner", cascade="all, delete-orphan")
    reset_requests = db.relationship(
        "PasswordResetRequest",
        foreign_keys="PasswordResetRequest.user_id",
        back_populates="user",
        cascade="all, delete-orphan",
    )

    def set_password(self, password: str) -> None:
        self.password_hash = generate_password_hash(password)

    def check_password(self, password: str) -> bool:
        return check_password_hash(self.password_hash, password)


@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))


class PasswordResetRequest(TimestampMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    requested_by_user = db.Column(db.Boolean, default=True, nullable=False)
    status = db.Column(db.String(20), default="pending", nullable=False)
    temp_password_hash = db.Column(db.String(255))
    temp_password_plain = db.Column(db.String(255))
    generated_at = db.Column(db.DateTime)
    consumed_at = db.Column(db.DateTime)
    admin_id = db.Column(db.Integer, db.ForeignKey("user.id"))
    note = db.Column(db.Text)

    user = db.relationship("User", foreign_keys=[user_id], back_populates="reset_requests")
    admin = db.relationship("User", foreign_keys=[admin_id])

    def set_temp_password(self, password: str) -> None:
        self.temp_password_hash = generate_password_hash(password)
        self.temp_password_plain = password
        self.generated_at = datetime.utcnow()
        self.status = "generated"

    def matches_temp_password(self, password: str) -> bool:
        if not self.temp_password_hash or self.status != "generated":
            return False
        return check_password_hash(self.temp_password_hash, password)

    def clear_temp_password(self) -> None:
        self.temp_password_hash = None
        self.temp_password_plain = None
        self.consumed_at = datetime.utcnow()
        self.status = "completed"


class Talk(TimestampMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(255), nullable=False)
    theme = db.Column(db.String(255), nullable=False)
    duration_minutes = db.Column(db.Float, default=10.0, nullable=False)
    words_per_minute = db.Column(db.Integer, default=130, nullable=False)
    base_prompt = db.Column(db.Text)
    global_revision_prompt = db.Column(db.Text)
    last_applied_global_revision_prompt = db.Column(db.Text)
    owner_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)

    owner = db.relationship("User", back_populates="talks")
    sections = db.relationship(
        "TalkSection",
        back_populates="talk",
        cascade="all, delete-orphan",
        order_by="TalkSection.sort_order",
    )
    reference_files = db.relationship(
        "ReferenceFile",
        back_populates="talk",
        cascade="all, delete-orphan",
        order_by="ReferenceFile.created_at.desc()",
    )

    @property
    def target_total_word_count(self) -> int:
        return int(round(self.duration_minutes * self.words_per_minute))

    @property
    def actual_total_word_count(self) -> int:
        return sum(section.actual_word_count for section in self.sections)

    @property
    def estimated_actual_time(self) -> float:
        if not self.words_per_minute:
            return 0
        return round(self.actual_total_word_count / self.words_per_minute, 2)

    @property
    def global_prompt_status(self) -> str:
        current = (self.global_revision_prompt or "").strip()
        applied = (self.last_applied_global_revision_prompt or "").strip()
        if not current:
            return "empty"
        if current == applied:
            return "applied"
        return "pending"


class TalkSection(TimestampMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    talk_id = db.Column(db.Integer, db.ForeignKey("talk.id"), nullable=False)
    label = db.Column(db.String(120), nullable=False)
    text = db.Column(db.Text, default="", nullable=False)
    revision_prompt = db.Column(db.Text)
    last_applied_revision_prompt = db.Column(db.Text)
    is_frozen = db.Column(db.Boolean, default=False, nullable=False)
    target_time_minutes = db.Column(db.Float, default=1.0, nullable=False)
    sort_order = db.Column(db.Integer, default=0, nullable=False)

    talk = db.relationship("Talk", back_populates="sections")

    @property
    def actual_word_count(self) -> int:
        return len([word for word in self.text.split() if word.strip()])

    @property
    def target_word_count(self) -> int:
        if not self.talk or not self.talk.words_per_minute:
            return 0
        return int(round(self.target_time_minutes * self.talk.words_per_minute))

    @property
    def actual_time_minutes(self) -> float:
        if not self.talk or not self.talk.words_per_minute:
            return 0
        return round(self.actual_word_count / self.talk.words_per_minute, 2)

    @property
    def prompt_status(self) -> str:
        current = (self.revision_prompt or "").strip()
        applied = (self.last_applied_revision_prompt or "").strip()
        if not current:
            return "empty"
        if current == applied:
            return "applied"
        return "pending"


class ReferenceFile(TimestampMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    talk_id = db.Column(db.Integer, db.ForeignKey("talk.id"), nullable=False)
    original_filename = db.Column(db.String(255), nullable=False)
    stored_filename = db.Column(db.String(255), nullable=False, unique=True)
    file_path = db.Column(db.String(500), nullable=False)
    mime_type = db.Column(db.String(255))
    file_size = db.Column(db.Integer)

    talk = db.relationship("Talk", back_populates="reference_files")
