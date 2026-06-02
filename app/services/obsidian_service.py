from __future__ import annotations

from datetime import date
from typing import Any
import json
from pathlib import Path
import shutil


VAULT_DIRECTORIES = (
    "00-Dashboard",
    "01-Daily",
    "02-Mistakes/数学",
    "02-Mistakes/英语",
    "02-Mistakes/语文",
    "03-Concepts/数学",
    "03-Concepts/英语",
    "03-Concepts/语文",
    "04-Reports/Daily",
    "04-Reports/Weekly",
    "05-Curriculum/数学",
    "05-Curriculum/英语",
    "05-Curriculum/语文",
    "06-Methods/数学",
    "06-Methods/英语",
    "06-Methods/语文",
    "07-Parent-QA",
    "08-Raw-Images",
    "09-AI-Raw-JSON",
    "99-System/prompts",
    "99-System/templates",
)


class ObsidianService:
    def __init__(self, vault_path: Path) -> None:
        self.vault_path = vault_path

    def initialize_vault(self) -> None:
        for directory in VAULT_DIRECTORIES:
            (self.vault_path / directory).mkdir(parents=True, exist_ok=True)

        config_path = self.vault_path / "99-System" / "config.yaml"
        if not config_path.exists():
            config_path.write_text(
                "name: Shensi Learning Vault\nversion: 0.1\n",
                encoding="utf-8",
            )

    def health_check(self) -> bool:
        required = (
            self.vault_path / "00-Dashboard",
            self.vault_path / "08-Raw-Images",
            self.vault_path / "09-AI-Raw-JSON",
            self.vault_path / "99-System" / "config.yaml",
        )
        return all(path.exists() for path in required)

    def save_raw_payload(self, message_id: str, payload: dict[str, Any]) -> Path:
        path = self.vault_path / "09-AI-Raw-JSON" / "raw_payloads" / f"{message_id}.json"
        return self.write_json(path, payload)

    def save_ai_output(self, mistake_id: str, output: dict[str, Any]) -> Path:
        path = self.vault_path / "09-AI-Raw-JSON" / "ai_outputs" / f"{mistake_id}.json"
        return self.write_json(path, output)

    def save_confirmation_json(self, mistake_id: str, output: dict[str, Any]) -> Path:
        path = self.vault_path / "09-AI-Raw-JSON" / "confirmations" / f"{mistake_id}.json"
        return self.write_json(path, output)

    def write_json(self, path: Path, data: dict[str, Any]) -> Path:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True),
            encoding="utf-8",
        )
        return path

    def save_local_image(self, message_id: str, source_path: str | None) -> Path:
        raw_dir = self.vault_path / "08-Raw-Images"
        raw_dir.mkdir(parents=True, exist_ok=True)
        if source_path:
            source = Path(source_path)
            if source.exists() and source.is_file():
                suffix = source.suffix or ".img"
                target = raw_dir / f"{message_id}{suffix}"
                if not target.exists() or target.stat().st_size != source.stat().st_size:
                    shutil.copyfile(source, target)
                return target

        target = raw_dir / f"{message_id}.svg"
        if not target.exists():
            target.write_text(
                """<svg xmlns="http://www.w3.org/2000/svg" width="900" height="520" viewBox="0 0 900 520">
  <rect width="900" height="520" fill="#fbfaf7"/>
  <rect x="56" y="54" width="788" height="412" rx="18" fill="#ffffff" stroke="#222222" stroke-width="3"/>
  <text x="96" y="130" font-family="Arial, sans-serif" font-size="34" fill="#202020">Shensi local sample mistake</text>
  <text x="96" y="205" font-family="Arial, sans-serif" font-size="30" fill="#202020">Solve: 2x + 5 = 17</text>
  <text x="96" y="275" font-family="Arial, sans-serif" font-size="30" fill="#b42318">Student answer: x = 5</text>
  <text x="96" y="345" font-family="Arial, sans-serif" font-size="30" fill="#116329">Correct answer: x = 6</text>
  <text x="96" y="415" font-family="Arial, sans-serif" font-size="24" fill="#555555">Generated because no local image path was provided.</text>
</svg>
""",
                encoding="utf-8",
            )
        return target

    def save_image_bytes(self, message_id: str, data: bytes, suffix: str = ".jpg") -> Path:
        raw_dir = self.vault_path / "08-Raw-Images"
        raw_dir.mkdir(parents=True, exist_ok=True)
        clean_suffix = suffix if suffix.startswith(".") else f".{suffix}"
        target = raw_dir / f"{message_id}{clean_suffix}"
        if not target.exists() or target.read_bytes() != data:
            target.write_bytes(data)
        return target

    def write_mistake_note(self, analysis: dict[str, Any]) -> Path:
        subject = str(analysis.get("subject", "math"))
        mistake_id = str(analysis["mistake_id"])
        safe_subject = self._safe_name(subject)
        title = self._safe_name(str(analysis.get("title") or mistake_id))
        path = self.vault_path / "02-Mistakes" / safe_subject / f"{analysis['date']}-{title}-{mistake_id}.md"
        image_file = Path(str(analysis.get("image_path", ""))).name
        concepts = ", ".join(analysis.get("concepts", [])) or "pending"
        error_types = ", ".join(analysis.get("error_types", [])) or "pending"
        question_items = self._format_question_items(analysis.get("question_items", []))
        question_section = question_items or str(analysis.get("question_text", ""))
        content = f"""---
type: mistake
mistake_id: "{mistake_id}"
grade: "{analysis.get("grade", "")}"
subject: "{subject}"
date: "{analysis.get("date", "")}"
status: confirmed
---

# {analysis.get("title", mistake_id)}

## Original Image

![[{image_file}]]

## AI Recognized Question

{question_section}

## Student Answer

{analysis.get("student_answer", "")}

## Correct Answer

{analysis.get("correct_answer", "")}

## Concepts

{concepts}

## Error Types

{error_types}

## Root Cause

{analysis.get("root_cause", "")}

## Parent Guidance

{analysis.get("parent_guidance", "")}
"""
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        return path

    def _format_question_items(self, items: Any) -> str:
        if not isinstance(items, list) or not items:
            return ""

        sections: list[str] = []
        for index, item in enumerate(items, start=1):
            if not isinstance(item, dict):
                sections.append(f"### Question {index}\n\n{item}")
                continue

            question = item.get("question") or item.get("title") or f"Question {index}"
            student_steps = self._format_steps(item.get("student_steps") or item.get("steps"))
            student_answer = item.get("student_answer") or item.get("answer") or ""
            correct_answer = item.get("correct_answer") or ""
            is_correct = item.get("is_correct")
            if is_correct is None:
                is_correct = item.get("verdict")
            error_reason = item.get("error_reason") or item.get("reason") or item.get("mistake_reason") or ""
            concept = item.get("concept") or item.get("knowledge_point") or ""
            error_type = item.get("error_type") or item.get("error_types") or ""

            sections.append(
                "\n".join(
                    [
                        f"### Question {index}: {question}",
                        "",
                        f"- Result: {self._format_verdict(is_correct)}",
                        f"- Student answer: {student_answer or 'Not provided'}",
                        f"- Correct answer: {correct_answer or 'Not provided'}",
                        f"- Concept: {concept or 'Not provided'}",
                        f"- Error type: {self._format_inline(error_type) or 'Not provided'}",
                        f"- Error reason: {error_reason or 'Not provided'}",
                        "",
                        "Student steps:",
                        "",
                        student_steps or "Not provided",
                    ]
                )
            )
        return "\n\n".join(sections)

    def _format_steps(self, value: Any) -> str:
        if isinstance(value, list):
            return "\n".join(f"{index}. {step}" for index, step in enumerate(value, start=1))
        if isinstance(value, dict):
            return json.dumps(value, ensure_ascii=False, indent=2)
        if value is None:
            return ""
        return str(value)

    def _format_verdict(self, value: Any) -> str:
        if isinstance(value, bool):
            return "correct" if value else "wrong"
        if value is None or value == "":
            return "unknown"
        return str(value)

    def _format_inline(self, value: Any) -> str:
        if isinstance(value, list):
            return ", ".join(str(item) for item in value)
        if value is None:
            return ""
        return str(value)

    def write_concept_note(self, concept: dict[str, Any]) -> Path:
        subject = self._safe_name(str(concept.get("subject", "math")))
        name = str(concept["name"])
        path = self.vault_path / "03-Concepts" / subject / f"{self._safe_name(name)}.md"
        content = f"""---
type: concept
subject: "{concept.get("subject", "")}"
grade: "{concept.get("grade", "")}"
status: "{concept.get("status", "active")}"
---

# {name}

## Description

Auto-created from confirmed mistake analysis.

## Related Mistakes

Updated by SQLite relationships.
"""
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        return path

    def write_daily_report(self, report_date: str, markdown: str) -> Path:
        path = self.vault_path / "04-Reports" / "Daily" / f"{report_date}.md"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(markdown, encoding="utf-8")
        return path

    def write_weekly_report(self, week_label: str, markdown: str) -> Path:
        path = self.vault_path / "04-Reports" / "Weekly" / f"{week_label}.md"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(markdown, encoding="utf-8")
        return path

    def _safe_name(self, value: str) -> str:
        cleaned = "".join(ch if ch.isalnum() or ch in ("-", "_") else "-" for ch in value.strip())
        return cleaned.strip("-") or "untitled"
