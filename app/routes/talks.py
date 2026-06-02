from __future__ import annotations

import mimetypes
from pathlib import Path
import shutil

from flask import Blueprint, current_app, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required

from ..extensions import db
from ..models import ReferenceFile, Talk, TalkSection
from ..services.openai_service import AIServiceError, OpenAIService
from ..utils import is_allowed_reference_file, talk_access_required, unique_upload_name


talks_bp = Blueprint("talks", __name__, url_prefix="/talks")
openai_service = OpenAIService()


@talks_bp.route("/")
@login_required
def dashboard():
    talks = Talk.query.filter_by(owner_id=current_user.id).order_by(Talk.updated_at.desc()).all()
    return render_template("talks/dashboard.html", talks=talks)


@talks_bp.route("/create", methods=["GET", "POST"])
@login_required
def create():
    if request.method == "POST":
        title = request.form.get("title", "").strip()
        theme = request.form.get("theme", "").strip()
        duration_minutes = float(request.form.get("duration_minutes", 10) or 10)
        words_per_minute = int(request.form.get("words_per_minute", 130) or 130)
        base_prompt = request.form.get("base_prompt", "").strip()

        if not title or not theme:
            flash("Title and theme are required.", "danger")
            return render_template("talks/create.html")

        talk = Talk(
            title=title,
            theme=theme,
            duration_minutes=duration_minutes,
            words_per_minute=words_per_minute,
            base_prompt=base_prompt,
            global_revision_prompt="",
            last_applied_global_revision_prompt="",
            owner=current_user,
        )
        db.session.add(talk)
        db.session.flush()

        starter_sections = [
            ("Intro", 1.0),
            ("Main Point", max(duration_minutes - 2.0, 1.0)),
            ("Conclusion", 1.0),
        ]
        for index, (label, target_time) in enumerate(starter_sections):
            db.session.add(
                TalkSection(
                    talk=talk,
                    label=label,
                    target_time_minutes=target_time,
                    sort_order=index,
                )
            )

        _save_reference_uploads(talk, request.files.getlist("reference_files"))
        db.session.commit()
        flash("Talk created.", "success")
        return redirect(url_for("talks.editor", talk_id=talk.id))

    return render_template("talks/create.html")


@talks_bp.route("/<int:talk_id>/settings", methods=["GET", "POST"])
@login_required
def settings(talk_id):
    talk = Talk.query.get_or_404(talk_id)
    talk_access_required(talk)

    if request.method == "POST":
        talk.title = request.form.get("title", "").strip()
        talk.theme = request.form.get("theme", "").strip()
        talk.duration_minutes = float(request.form.get("duration_minutes", talk.duration_minutes) or 0)
        talk.words_per_minute = int(request.form.get("words_per_minute", talk.words_per_minute) or 0)
        talk.base_prompt = request.form.get("base_prompt", "").strip()
        talk.global_revision_prompt = request.form.get("global_revision_prompt", "").strip()

        _save_reference_uploads(talk, request.files.getlist("reference_files"))

        db.session.commit()
        flash("Talk settings updated.", "success")
        return redirect(url_for("talks.settings", talk_id=talk.id))

    return render_template("talks/settings.html", talk=talk)


@talks_bp.route("/<int:talk_id>/reference-files/<int:file_id>/delete", methods=["POST"])
@login_required
def delete_reference_file(talk_id, file_id):
    talk = Talk.query.get_or_404(talk_id)
    talk_access_required(talk)
    ref = ReferenceFile.query.filter_by(id=file_id, talk_id=talk.id).first_or_404()

    path = Path(ref.file_path)
    if path.exists():
        path.unlink()
    db.session.delete(ref)
    db.session.commit()
    flash("Reference file removed.", "success")
    return redirect(url_for("talks.settings", talk_id=talk.id))


@talks_bp.route("/<int:talk_id>/editor", methods=["GET", "POST"])
@login_required
def editor(talk_id):
    talk = Talk.query.get_or_404(talk_id)
    talk_access_required(talk)
    if _normalize_existing_section_times(talk):
        db.session.commit()

    if request.method == "POST":
        section_action = request.form.get("section_action", "").strip()
        if section_action.startswith("update:"):
            action = "update_section"
            section_id = int(section_action.split(":", 1)[1])
        elif section_action.startswith("delete:"):
            action = "delete_section"
            section_id = int(section_action.split(":", 1)[1])
        else:
            action = request.form.get("action", "save")
            section_id = None

        if action == "add_section":
            next_order = len(talk.sections)
            db.session.add(
                TalkSection(
                    talk=talk,
                    label="New Section",
                    target_time_minutes=1.0,
                    sort_order=next_order,
                )
            )
            db.session.commit()
            flash("Section added.", "success")
            return redirect(url_for("talks.editor", talk_id=talk.id))

        _apply_section_form_data(talk, request.form)
        talk.global_revision_prompt = request.form.get(
            "global_revision_prompt", talk.global_revision_prompt or ""
        ).strip()

        if action == "save":
            db.session.commit()
            flash("Talk saved.", "success")
            return redirect(url_for("talks.editor", talk_id=talk.id))

        if action == "generate":
            return _generate_sections(talk)

        if action == "ai_update":
            return _revise_talk(talk)

        if action == "update_section":
            return _revise_section(talk, section_id)

        if action == "delete_section":
            section = TalkSection.query.filter_by(id=section_id, talk_id=talk.id).first_or_404()
            db.session.delete(section)
            db.session.flush()
            _normalize_sort_order(talk)
            db.session.commit()
            flash("Section removed.", "success")
            return redirect(url_for("talks.editor", talk_id=talk.id))

    return render_template("talks/editor.html", talk=talk)


@talks_bp.route("/<int:talk_id>/generate", methods=["POST"])
@login_required
def generate(talk_id):
    talk = Talk.query.get_or_404(talk_id)
    talk_access_required(talk)
    _apply_section_form_data(talk, request.form)
    talk.global_revision_prompt = request.form.get(
        "global_revision_prompt", talk.global_revision_prompt or ""
    ).strip()
    return _generate_sections(talk)


@talks_bp.route("/<int:talk_id>/ai-update", methods=["POST"])
@login_required
def ai_update(talk_id):
    talk = Talk.query.get_or_404(talk_id)
    talk_access_required(talk)
    _apply_section_form_data(talk, request.form)
    talk.global_revision_prompt = request.form.get(
        "global_revision_prompt", talk.global_revision_prompt or ""
    ).strip()
    return _revise_talk(talk)


@talks_bp.route("/<int:talk_id>/sections/<int:section_id>/update", methods=["POST"])
@login_required
def update_section(talk_id, section_id):
    talk = Talk.query.get_or_404(talk_id)
    talk_access_required(talk)
    _apply_section_form_data(talk, request.form)
    talk.global_revision_prompt = request.form.get(
        "global_revision_prompt", talk.global_revision_prompt or ""
    ).strip()
    return _revise_section(talk, section_id)


@talks_bp.route("/<int:talk_id>/view")
@login_required
def view(talk_id):
    talk = Talk.query.get_or_404(talk_id)
    talk_access_required(talk)
    return render_template("talks/view.html", talk=talk)


@talks_bp.route("/<int:talk_id>/delete", methods=["POST"])
@login_required
def delete(talk_id):
    talk = Talk.query.get_or_404(talk_id)
    talk_access_required(talk)

    for ref in talk.reference_files:
        path = Path(ref.file_path)
        if path.exists():
            path.unlink()

    db.session.delete(talk)
    db.session.commit()
    flash("Talk deleted.", "success")
    return redirect(url_for("talks.dashboard"))


@talks_bp.route("/<int:talk_id>/duplicate", methods=["POST"])
@login_required
def duplicate(talk_id):
    talk = Talk.query.get_or_404(talk_id)
    talk_access_required(talk)

    duplicate_talk = Talk(
        title=f"{talk.title} (Copy)",
        theme=talk.theme,
        duration_minutes=talk.duration_minutes,
        words_per_minute=talk.words_per_minute,
        base_prompt=talk.base_prompt,
        global_revision_prompt=talk.global_revision_prompt,
        last_applied_global_revision_prompt=talk.last_applied_global_revision_prompt,
        owner=current_user,
    )
    db.session.add(duplicate_talk)
    db.session.flush()

    for section in talk.sections:
        db.session.add(
            TalkSection(
                talk=duplicate_talk,
                label=section.label,
                text=section.text,
                revision_prompt=section.revision_prompt,
                last_applied_revision_prompt=section.last_applied_revision_prompt,
                is_frozen=section.is_frozen,
                target_time_minutes=section.target_time_minutes,
                sort_order=section.sort_order,
            )
        )

    for ref in talk.reference_files:
        source_path = Path(ref.file_path)
        if not source_path.exists():
            continue

        stored_filename = unique_upload_name(ref.original_filename)
        destination_path = Path(current_app.config["UPLOAD_FOLDER"]) / stored_filename
        shutil.copy2(source_path, destination_path)

        db.session.add(
            ReferenceFile(
                talk=duplicate_talk,
                original_filename=ref.original_filename,
                stored_filename=stored_filename,
                file_path=str(destination_path),
                mime_type=ref.mime_type,
                file_size=destination_path.stat().st_size,
            )
        )

    db.session.commit()
    flash("Talk duplicated.", "success")
    return redirect(url_for("talks.editor", talk_id=duplicate_talk.id))


def _apply_section_form_data(talk: Talk, form) -> None:
    for section in talk.sections:
        prefix = f"section-{section.id}"
        section.label = form.get(f"{prefix}-label", section.label).strip() or "Untitled Section"
        section.text = form.get(f"{prefix}-text", section.text)
        section.revision_prompt = form.get(f"{prefix}-prompt", "").strip()
        section.target_time_minutes = _normalized_target_time(
            float(form.get(f"{prefix}-target-time", section.target_time_minutes) or 0)
        )
        section.is_frozen = form.get(f"{prefix}-frozen") == "on"
        section.sort_order = int(form.get(f"{prefix}-sort-order", section.sort_order) or 0)

    _normalize_sort_order(talk)


def _save_reference_uploads(talk: Talk, uploads) -> None:
    for upload in uploads:
        if not upload or not upload.filename:
            continue
        if not is_allowed_reference_file(upload.filename):
            flash(f"Skipped unsupported file: {upload.filename}", "warning")
            continue

        stored_filename = unique_upload_name(upload.filename)
        file_path = Path(current_app.config["UPLOAD_FOLDER"]) / stored_filename
        upload.save(file_path)

        ref = ReferenceFile(
            talk=talk,
            original_filename=upload.filename,
            stored_filename=stored_filename,
            file_path=str(file_path),
            mime_type=upload.mimetype or mimetypes.guess_type(upload.filename)[0],
            file_size=file_path.stat().st_size,
        )
        db.session.add(ref)


def _changed_prompt_section_ids(talk: Talk, form) -> list[int]:
    changed_ids = []
    for section in talk.sections:
        prefix = f"section-{section.id}"
        original_prompt = form.get(f"{prefix}-original-prompt", "").strip()
        current_prompt = (section.revision_prompt or "").strip()
        if current_prompt != original_prompt:
            changed_ids.append(section.id)
    return changed_ids


def _global_revision_prompt_changed(talk: Talk, form) -> bool:
    original_prompt = form.get("original_global_revision_prompt", "").strip()
    current_prompt = (talk.global_revision_prompt or "").strip()
    return current_prompt != original_prompt


def _has_any_revision_instructions(talk: Talk) -> bool:
    if (talk.global_revision_prompt or "").strip():
        return True
    return any((section.revision_prompt or "").strip() for section in talk.sections)


def _normalize_sort_order(talk: Talk) -> None:
    for index, section in enumerate(sorted(talk.sections, key=lambda item: item.sort_order)):
        section.sort_order = index


def _normalized_target_time(value: float) -> float:
    if value <= 0:
        return 0.25
    rounded = round(value * 4) / 4
    return round(max(0.25, rounded), 2)


def _normalize_existing_section_times(talk: Talk) -> bool:
    changed = False
    for section in talk.sections:
        normalized = _normalized_target_time(section.target_time_minutes)
        if normalized != section.target_time_minutes:
            section.target_time_minutes = normalized
            changed = True
    return changed


def _mark_prompts_applied(talk: Talk) -> None:
    talk.last_applied_global_revision_prompt = talk.global_revision_prompt
    for section in talk.sections:
        section.last_applied_revision_prompt = section.revision_prompt


def _generate_sections(talk: Talk):
    try:
        structured = openai_service.generate_full_talk(talk)
    except AIServiceError as exc:
        db.session.rollback()
        flash(str(exc), "danger")
        return redirect(url_for("talks.editor", talk_id=talk.id))

    talk.sections.clear()
    db.session.flush()
    for index, item in enumerate(structured.sections):
        db.session.add(
            TalkSection(
                talk=talk,
                label=item.label,
                text=item.text,
                target_time_minutes=_normalized_target_time(item.target_time_minutes),
                sort_order=index,
            )
        )
    _mark_prompts_applied(talk)
    db.session.commit()
    flash("Sections generated with AI.", "success")
    if structured.notes:
        flash(structured.notes, "info")
    return redirect(url_for("talks.editor", talk_id=talk.id))


def _revise_talk(talk: Talk):
    changed_prompt_section_ids = _changed_prompt_section_ids(talk, request.form)
    global_prompt_changed = _global_revision_prompt_changed(talk, request.form)
    has_any_revision_instructions = _has_any_revision_instructions(talk)
    force_rerun = request.form.get("force_rerun") == "1"

    if (
        not changed_prompt_section_ids
        and not global_prompt_changed
        and not has_any_revision_instructions
        and not force_rerun
    ):
        db.session.rollback()
        flash(
            "No talk-level or section-level revision prompts are present. Add revision instructions or confirm a rerun if you want to send the same draft back again.",
            "warning",
        )
        return redirect(url_for("talks.editor", talk_id=talk.id))

    try:
        structured = openai_service.revise_talk(
            talk,
            changed_prompt_section_ids=changed_prompt_section_ids,
            global_prompt_changed=global_prompt_changed,
            force_rerun=force_rerun,
        )
    except AIServiceError as exc:
        db.session.rollback()
        flash(str(exc), "danger")
        return redirect(url_for("talks.editor", talk_id=talk.id))

    for index, item in enumerate(structured.sections):
        if index >= len(talk.sections):
            db.session.add(
                TalkSection(
                    talk=talk,
                    label=item.label,
                    text=item.text,
                    target_time_minutes=_normalized_target_time(item.target_time_minutes),
                    sort_order=index,
                )
            )
            continue

        section = talk.sections[index]
        if section.is_frozen:
            continue

        section.label = item.label
        section.text = item.text
        section.target_time_minutes = _normalized_target_time(item.target_time_minutes)

    _mark_prompts_applied(talk)
    db.session.commit()
    flash("Talk updated with AI.", "success")
    if structured.notes:
        flash(structured.notes, "info")
    return redirect(url_for("talks.editor", talk_id=talk.id))


def _revise_section(talk: Talk, section_id: int):
    section = TalkSection.query.filter_by(id=section_id, talk_id=talk.id).first_or_404()
    if section.is_frozen:
        flash("Unfreeze this section before requesting an AI section update.", "warning")
        return redirect(url_for("talks.editor", talk_id=talk.id))
    try:
        structured = openai_service.revise_single_section(talk, section)
    except AIServiceError as exc:
        db.session.rollback()
        flash(str(exc), "danger")
        return redirect(url_for("talks.editor", talk_id=talk.id))

    for current, returned in zip(talk.sections, structured.sections):
        if current.id == section.id:
            current.label = returned.label
            current.text = returned.text
            current.target_time_minutes = _normalized_target_time(
                returned.target_time_minutes
            )
            break

    talk.last_applied_global_revision_prompt = talk.global_revision_prompt
    section.last_applied_revision_prompt = section.revision_prompt
    db.session.commit()
    flash(f"Section '{section.label}' updated with AI.", "success")
    if structured.notes:
        flash(structured.notes, "info")
    return redirect(url_for("talks.editor", talk_id=talk.id))
