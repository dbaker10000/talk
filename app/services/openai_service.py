from __future__ import annotations

import json
import os
from pathlib import Path
from openai import OpenAI
from pydantic import BaseModel, Field
from pypdf import PdfReader
from docx import Document

from ..models import ReferenceFile, Talk, TalkSection


class AIServiceError(Exception):
    pass


class StructuredSection(BaseModel):
    label: str
    text: str
    target_time_minutes: float = Field(default=1.0, ge=0)


class StructuredTalkResponse(BaseModel):
    talk_title: str
    sections: list[StructuredSection]
    notes: str = ""


class OpenAIService:
    DEFAULT_MODEL = "gpt-5.5"

    def __init__(self):
        api_key = os.environ.get("OPENAI_API_KEY")
        self.client = OpenAI(api_key=api_key) if api_key else None
        self.model = self.DEFAULT_MODEL
        self.reference_char_limit = 24000

    def is_configured(self) -> bool:
        return self.client is not None

    def generate_full_talk(self, talk: Talk) -> StructuredTalkResponse:
        prompt = self._build_generation_prompt(talk)
        return self._run_structured_request(prompt)

    def revise_talk(
        self,
        talk: Talk,
        changed_prompt_section_ids: list[int] | None = None,
        global_prompt_changed: bool = False,
        force_rerun: bool = False,
    ) -> StructuredTalkResponse:
        prompt = self._build_revision_prompt(
            talk,
            changed_prompt_section_ids=changed_prompt_section_ids or [],
            global_prompt_changed=global_prompt_changed,
            force_rerun=force_rerun,
        )
        return self._run_structured_request(prompt)

    def revise_single_section(self, talk: Talk, section: TalkSection) -> StructuredTalkResponse:
        prompt = self._build_single_section_prompt(talk, section)
        return self._run_structured_request(prompt)

    def collect_reference_context(self, talk: Talk) -> str:
        chunks = []
        used_chars = 0

        for ref in talk.reference_files:
            extracted = self._extract_reference_text(ref)
            if not extracted:
                continue

            block = f"\n\nFILE: {ref.original_filename}\n{extracted.strip()}"
            remaining = self.reference_char_limit - used_chars
            if remaining <= 0:
                break

            trimmed = block[:remaining]
            chunks.append(trimmed)
            used_chars += len(trimmed)

        return "".join(chunks).strip()

    def _run_structured_request(self, prompt: str) -> StructuredTalkResponse:
        if not self.client:
            raise AIServiceError("OPENAI_API_KEY is not configured.")

        try:
            response = self.client.responses.parse(
                model=self.model,
                input=[
                    {
                        "role": "system",
                        "content": (
                            "You are an expert talk-writing assistant. Return only structured "
                            "content that can be used to update a speech outline and draft."
                        ),
                    },
                    {"role": "user", "content": prompt},
                ],
                text_format=StructuredTalkResponse,
            )
        except Exception as exc:
            raise AIServiceError(f"OpenAI request failed: {exc}") from exc

        parsed = response.output_parsed
        if not parsed:
            raise AIServiceError("The AI response did not include structured content.")
        return parsed

    def _build_generation_prompt(self, talk: Talk) -> str:
        structure = self._serialize_sections(talk.sections)
        references = self.collect_reference_context(talk)

        return f"""
Create a meeting talk draft as structured JSON.

Talk title: {talk.title}
Talk theme: {talk.theme}
Duration minutes: {talk.duration_minutes}
Words per minute: {talk.words_per_minute}
Target total word count: {talk.target_total_word_count}
Base prompt:
{talk.base_prompt or "No base prompt provided."}

Existing section labels and timing guidance:
{structure or "No existing sections. Propose a strong structure."}

Reference context:
{references or "No reference files uploaded."}

Instructions:
- Return sections in a logical order.
- Keep the overall draft aligned with the target duration.
- Assign a realistic target_time_minutes for each section.
- Use clear labels and complete prose for each section text.
- Treat reference files mainly as examples of tone, structure, flow, and phrasing style.
- Do not mention the reference files inside the talk unless the user prompt clearly asks for that.
- Produce a talk draft that sounds ready to speak, not a rough outline.
- Notes may include timing or structure guidance for the user.
""".strip()

    def _build_revision_prompt(
        self,
        talk: Talk,
        changed_prompt_section_ids: list[int],
        global_prompt_changed: bool,
        force_rerun: bool,
    ) -> str:
        references = self.collect_reference_context(talk)
        sections = []
        for section in talk.sections:
            sections.append(
                {
                    "id": section.id,
                    "label": section.label,
                    "text": section.text,
                    "revision_prompt": section.revision_prompt or "",
                    "is_frozen": section.is_frozen,
                    "target_time_minutes": section.target_time_minutes,
                    "actual_time_minutes": section.actual_time_minutes,
                    "actual_word_count": section.actual_word_count,
                    "target_word_count": section.target_word_count,
                    "prompt_changed": section.id in changed_prompt_section_ids,
                }
            )

        changed_section_summary = ", ".join(str(item) for item in changed_prompt_section_ids) or "None"
        global_revision_prompt = talk.global_revision_prompt or "No talk-level revision prompt provided."
        rerun_instruction = (
            "The user explicitly chose to rerun the same instructions even though no section prompts changed."
            if force_rerun
            else "Do not treat this as a blind rerun unless the section data below indicates prompt changes or timing/flow needs."
        )

        return f"""
Revise this talk while respecting frozen sections and preserving user wording when possible.

Talk title: {talk.title}
Talk theme: {talk.theme}
Duration minutes: {talk.duration_minutes}
Words per minute: {talk.words_per_minute}
Target total word count: {talk.target_total_word_count}
Actual total word count: {talk.actual_total_word_count}
Estimated actual time: {talk.estimated_actual_time}
Base prompt:
{talk.base_prompt or "No base prompt provided."}

Talk-level revision prompt:
{global_revision_prompt}

Reference context:
{references or "No reference files uploaded."}

Current sections JSON:
{json.dumps(sections, indent=2)}

Instructions:
- Return every section in order.
- Do not rewrite frozen sections. Keep their text materially unchanged.
- Preserve the speaker's existing language wherever it already fits the goal.
- Prioritize rewriting sections where prompt_changed is true.
- If the talk-level revision prompt changed, apply it across the relevant unfrozen sections while keeping continuity.
- If prompt_changed is false, only revise a section when timing, flow, or continuity clearly needs improvement.
- Respect section-specific revision prompts.
- Changed prompt section ids: {changed_section_summary}
- Talk-level revision prompt changed: {global_prompt_changed}
- {rerun_instruction}
- Treat reference files mainly as examples of tone, cadence, structure, and transitions.
- Keep continuity across sections.
- Notes should explain what changed.
""".strip()

    def _build_single_section_prompt(self, talk: Talk, section: TalkSection) -> str:
        references = self.collect_reference_context(talk)
        all_sections = [
            {
                "label": item.label,
                "text": item.text,
                "revision_prompt": item.revision_prompt or "",
                "is_frozen": item.is_frozen,
                "target_time_minutes": item.target_time_minutes,
            }
            for item in talk.sections
        ]

        return f"""
Revise only one section in this talk and return the full section list, leaving all non-target sections unchanged.

Talk title: {talk.title}
Talk theme: {talk.theme}
Duration minutes: {talk.duration_minutes}
Words per minute: {talk.words_per_minute}
Base prompt:
{talk.base_prompt or "No base prompt provided."}

Talk-level revision prompt:
{talk.global_revision_prompt or "No talk-level revision prompt provided."}

Reference context:
{references or "No reference files uploaded."}

Target section label: {section.label}
Target section current text:
{section.text}

Target section revision prompt:
{section.revision_prompt or "No section-specific prompt provided."}

All sections JSON:
{json.dumps(all_sections, indent=2)}

Instructions:
- Only rewrite the target section.
- Keep frozen sections unchanged.
- Preserve the order and labels of all sections.
- Match the target section to its timing goal.
- Use the reference files mainly as examples of tone and structure.
- Notes should mention the target section that was updated.
""".strip()

    def _serialize_sections(self, sections: list[TalkSection]) -> str:
        if not sections:
            return ""
        return "\n".join(
            f"- {section.label}: target {section.target_time_minutes} min"
            for section in sections
        )

    def _extract_reference_text(self, ref: ReferenceFile) -> str:
        path = Path(ref.file_path)
        if not path.exists():
            return ""

        suffix = path.suffix.lower()
        try:
            if suffix in {".txt", ".md", ".rtf"}:
                return path.read_text(encoding="utf-8", errors="ignore")
            if suffix == ".pdf":
                return "\n".join(page.extract_text() or "" for page in PdfReader(str(path)).pages)
            if suffix == ".docx":
                document = Document(str(path))
                return "\n".join(paragraph.text for paragraph in document.paragraphs)
        except Exception:
            return ""
        return ""
