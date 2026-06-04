from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
import base64
import hashlib
import json

from app.config import Settings
from app.feishu.client import FeishuClient, FeishuClientError
from app.models.schemas import ConfirmationRequest, LocalUploadRequest
from app.services.ai_service import AIService
from app.services.math_verification_service import MathVerificationService
from app.services.obsidian_service import ObsidianService
from app.services.report_service import ReportService
from app.services.review_service import ReviewService
from app.services.sqlite_service import SQLiteService


class MistakeWorkflowService:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.sqlite = SQLiteService(settings.db_path)
        self.obsidian = ObsidianService(settings.vault_path)
        self.ai = AIService(settings.ai_provider, settings.ai_model)
        self.math_verifier = MathVerificationService()
        self.review = ReviewService()
        self.reports = ReportService(self.sqlite, self.obsidian)

    def submit_local(self, request: LocalUploadRequest) -> dict[str, Any]:
        message_id = request.message_id or self._stable_id(
            "local",
            request.local_image_path or "generated-image",
            request.subject,
            request.grade,
            request.note,
        )
        payload = {
            "message_id": message_id,
            "message_type": "image",
            "chat_id": "local-dev",
            "sender_id": "local-parent",
            "source": request.source,
            "subject": request.subject,
            "grade": request.grade,
            "note": request.note,
            "local_image_path": request.local_image_path,
            "image_base64": request.image_base64,
            "image_filename": request.image_filename,
            "auto_confirm": request.auto_confirm,
        }
        return self.submit_payload(payload, source=request.source, auto_confirm=request.auto_confirm)

    def submit_external_analysis(
        self,
        *,
        message_id: str,
        platform: str,
        sender_id: str | None,
        chat_id: str | None,
        image_path: str | None,
        image_base64: str | None,
        image_filename: str | None,
        subject: str,
        grade: str,
        note: str,
        analysis: dict[str, Any],
        auto_confirm: bool = False,
    ) -> dict[str, Any]:
        self.sqlite.initialize()
        self.obsidian.initialize_vault()
        now = self._now()
        today = now[:10]
        source = f"hermes:{platform}:analysis"
        mistake_id = self._mistake_id(message_id)
        payload = {
            "message_id": message_id,
            "message_type": "external_analysis",
            "chat_id": chat_id,
            "sender_id": sender_id,
            "source": source,
            "subject": subject,
            "grade": grade,
            "note": note,
            "image_path": image_path,
            "image_base64": image_base64,
            "image_filename": image_filename,
            "analysis": analysis,
            "auto_confirm": auto_confirm,
        }
        raw_payload_path = self.obsidian.save_raw_payload(message_id, payload)
        inserted = self.sqlite.upsert_feishu_message(
            message_id=message_id,
            chat_id=chat_id,
            sender_id=sender_id,
            message_type="external_analysis",
            raw_payload_path=str(raw_payload_path),
            status="received",
            created_at=now,
        )
        if not inserted:
            existing = self.sqlite.get_mistake(mistake_id)
            result: dict[str, Any] = {
                "status": existing["status"] if existing else "duplicated",
                "message_id": message_id,
                "mistake_id": mistake_id,
                "mistake": existing,
                "duplicate": True,
            }
            if auto_confirm and existing and existing["status"] == "waiting_confirmation":
                existing_analysis = self.sqlite.read_json_file(existing.get("raw_json_path"))
                if self._can_auto_confirm_external_analysis(existing_analysis):
                    result["confirmation"] = self.confirm_mistake(
                        mistake_id,
                        ConfirmationRequest(action="confirm", confirmed_by="hermes"),
                    )
                else:
                    result |= self._auto_confirm_blocked_payload(existing_analysis)
            elif auto_confirm and existing and existing["status"] == "confirmed":
                result["confirmation"] = {
                    "status": "confirmed",
                    "mistake_id": mistake_id,
                    "note_path": existing.get("note_path"),
                }
            return result

        parsed = {
            "message_id": message_id,
            "local_image_path": image_path,
            "image_base64": image_base64,
            "image_filename": image_filename,
        }
        saved_image_path, download_status = self._save_inbound_image(message_id, parsed, source)
        normalized = self._normalize_external_analysis(
            analysis=analysis,
            mistake_id=mistake_id,
            message_id=message_id,
            image_path=saved_image_path,
            subject=subject,
            grade=grade,
            note=note,
            today=today,
            source=source,
        )
        output_path = self.obsidian.save_ai_output(mistake_id, normalized)
        self.sqlite.upsert_mistake(
            {
                "id": mistake_id,
                "subject": normalized["subject"],
                "grade": normalized["grade"],
                "date": normalized["date"],
                "title": normalized["title"],
                "source": source,
                "image_path": str(saved_image_path),
                "note_path": None,
                "raw_json_path": str(output_path),
                "severity": normalized["severity"],
                "confidence": normalized["confidence"],
                "status": "waiting_confirmation",
                "created_at": now,
                "updated_at": now,
            }
        )
        self.sqlite.upsert_ai_run(
            {
                "id": f"ai:{mistake_id}",
                "mistake_id": mistake_id,
                "model_name": normalized["model"],
                "prompt_version": normalized["prompt_version"],
                "input_path": str(saved_image_path),
                "output_json_path": str(output_path),
                "confidence": normalized["confidence"],
                "created_at": now,
            }
        )
        self.sqlite.update_message_status(message_id, "waiting_confirmation")
        result = {
            "status": "waiting_confirmation",
            "message_id": message_id,
            "mistake_id": mistake_id,
            "duplicate": False,
            "raw_payload_path": str(raw_payload_path),
            "image_path": str(saved_image_path),
            "image_download": download_status,
            "analysis": normalized,
            "confirmation_summary": normalized["confirmation_summary"],
            "next": {
                "confirm": f"/mistakes/{mistake_id}/confirm",
                "discard": f"/mistakes/{mistake_id}/discard",
            },
        }
        if auto_confirm:
            if self._can_auto_confirm_external_analysis(normalized):
                result["confirmation"] = self.confirm_mistake(
                    mistake_id,
                    ConfirmationRequest(action="confirm", confirmed_by="hermes"),
                )
            else:
                result |= self._auto_confirm_blocked_payload(normalized)
        return result

    def submit_payload(
        self,
        payload: dict[str, Any],
        *,
        source: str = "feishu",
        auto_confirm: bool = False,
    ) -> dict[str, Any]:
        self.sqlite.initialize()
        self.obsidian.initialize_vault()
        now = self._now()
        today = now[:10]
        parsed = self._parse_payload(payload)
        message_id = parsed["message_id"]
        mistake_id = self._mistake_id(message_id)
        raw_payload_path = self.obsidian.save_raw_payload(message_id, payload)
        inserted = self.sqlite.upsert_feishu_message(
            message_id=message_id,
            chat_id=parsed.get("chat_id"),
            sender_id=parsed.get("sender_id"),
            message_type=parsed["message_type"],
            raw_payload_path=str(raw_payload_path),
            status="received",
            created_at=now,
        )
        if not inserted:
            existing = self.sqlite.get_mistake(mistake_id)
            result: dict[str, Any] = {
                "status": existing["status"] if existing else "duplicated",
                "message_id": message_id,
                "mistake_id": mistake_id,
                "mistake": existing,
                "duplicate": True,
            }
            if auto_confirm and existing and existing["status"] == "waiting_confirmation":
                result["confirmation"] = self.confirm_mistake(
                    mistake_id,
                    ConfirmationRequest(action="confirm", confirmed_by="local_parent"),
                )
            elif auto_confirm and existing and existing["status"] == "confirmed":
                result["confirmation"] = {
                    "status": "confirmed",
                    "mistake_id": mistake_id,
                    "note_path": existing.get("note_path"),
                }
            return result

        image_path, download_status = self._save_inbound_image(message_id, parsed, source)
        analysis = self.ai.analyze_mistake(
            mistake_id=mistake_id,
            image_path=image_path,
            subject=parsed["subject"],
            grade=parsed["grade"],
            note=parsed.get("note") or "",
            today=today,
        )
        analysis["message_id"] = message_id
        analysis["source"] = source
        ai_output_path = self.obsidian.save_ai_output(mistake_id, analysis)
        self.sqlite.upsert_mistake(
            {
                "id": mistake_id,
                "subject": analysis["subject"],
                "grade": analysis["grade"],
                "date": analysis["date"],
                "title": analysis["title"],
                "source": source,
                "image_path": str(image_path),
                "note_path": None,
                "raw_json_path": str(ai_output_path),
                "severity": analysis["severity"],
                "confidence": analysis["confidence"],
                "status": "waiting_confirmation",
                "created_at": now,
                "updated_at": now,
            }
        )
        self.sqlite.upsert_ai_run(
            {
                "id": f"ai:{mistake_id}",
                "mistake_id": mistake_id,
                "model_name": analysis["model"],
                "prompt_version": analysis["prompt_version"],
                "input_path": str(image_path),
                "output_json_path": str(ai_output_path),
                "confidence": analysis["confidence"],
                "created_at": now,
            }
        )
        self.sqlite.update_message_status(message_id, "waiting_confirmation")
        result = {
            "status": "waiting_confirmation",
            "message_id": message_id,
            "mistake_id": mistake_id,
            "duplicate": False,
            "raw_payload_path": str(raw_payload_path),
            "image_path": str(image_path),
            "image_download": download_status,
            "analysis": analysis,
            "next": {
                "confirm": f"/mistakes/{mistake_id}/confirm",
                "discard": f"/mistakes/{mistake_id}/discard",
            },
        }
        if auto_confirm:
            result["confirmation"] = self.confirm_mistake(
                mistake_id,
                ConfirmationRequest(action="confirm", confirmed_by="local_parent"),
            )
        return result

    def confirm_mistake(self, mistake_id: str, request: ConfirmationRequest) -> dict[str, Any]:
        mistake = self.sqlite.get_mistake(mistake_id)
        if not mistake:
            raise ValueError(f"Unknown mistake_id: {mistake_id}")
        analysis = self.sqlite.read_json_file(mistake.get("raw_json_path"))
        if not analysis:
            raise ValueError(f"Missing AI output for mistake_id: {mistake_id}")

        now = self._now()
        action = request.action
        final_analysis = self._apply_overrides(analysis, request.overrides)
        final_analysis["status"] = "discarded" if action == "discard" else "confirmed"
        final_path = self.obsidian.save_confirmation_json(mistake_id, final_analysis)
        self.sqlite.upsert_parent_confirmation(
            {
                "id": f"confirmation:{mistake_id}",
                "mistake_id": mistake_id,
                "message_id": final_analysis.get("message_id"),
                "action": action,
                "before_json_path": mistake.get("raw_json_path"),
                "after_json_path": str(final_path),
                "confirmed_by": request.confirmed_by,
                "confirmed_at": now,
            }
        )

        if action == "discard":
            self.sqlite.upsert_mistake(
                mistake
                | {
                    "status": "discarded",
                    "updated_at": now,
                }
            )
            if final_analysis.get("message_id"):
                self.sqlite.update_message_status(final_analysis["message_id"], "discarded")
            return {"status": "discarded", "mistake_id": mistake_id}

        note_path = self.obsidian.write_mistake_note(final_analysis)
        final_analysis["note_path"] = str(note_path)
        self.sqlite.upsert_mistake(
            mistake
            | {
                "subject": final_analysis["subject"],
                "grade": final_analysis["grade"],
                "date": final_analysis["date"],
                "title": final_analysis["title"],
                "image_path": final_analysis["image_path"],
                "note_path": str(note_path),
                "raw_json_path": str(final_path),
                "severity": final_analysis["severity"],
                "confidence": final_analysis["confidence"],
                "status": "confirmed",
                "updated_at": now,
            }
        )
        for concept_name in final_analysis.get("concepts", []):
            concept_id = self._stable_id(
                "concept",
                final_analysis["subject"],
                final_analysis["grade"],
                concept_name,
            )
            concept = {
                "id": concept_id,
                "subject": final_analysis["subject"],
                "grade": final_analysis["grade"],
                "name": concept_name,
                "chapter": None,
                "status": "active",
                "created_at": now,
                "updated_at": now,
            }
            self.obsidian.write_curriculum_note(concept)
            concept["note_path"] = str(self.obsidian.concept_note_path(concept))
            self.sqlite.upsert_concept(concept)
            self.sqlite.link_mistake_concept(mistake_id, concept_id)
            related_mistakes = self.sqlite.concept_mistakes(concept_name)
            self.obsidian.write_concept_note(
                concept,
                related_mistakes=related_mistakes,
                analysis=final_analysis,
            )
        for error_type in final_analysis.get("error_types", []):
            self.sqlite.link_mistake_error_type(mistake_id, error_type)
        base_date = self.review.parse_date(final_analysis["date"])
        reviews = self.review.build_reviews(mistake_id=mistake_id, base_date=base_date, now=now)
        for review in reviews:
            self.sqlite.upsert_review(review)
        daily_report = self.reports.generate_daily(base_date, now)
        weekly_report = self.reports.generate_weekly(base_date, now)
        if final_analysis.get("message_id"):
            self.sqlite.update_message_status(final_analysis["message_id"], "confirmed")
        return {
            "status": "confirmed",
            "mistake_id": mistake_id,
            "note_path": str(note_path),
            "reviews": reviews,
            "daily_report": daily_report,
            "weekly_report": weekly_report,
        }

    def discard_mistake(self, mistake_id: str, confirmed_by: str = "local_parent") -> dict[str, Any]:
        return self.confirm_mistake(
            mistake_id,
            ConfirmationRequest(action="discard", confirmed_by=confirmed_by),
        )

    def regenerate_daily(self, date_text: str | None = None) -> dict[str, Any]:
        now = self._now()
        report_date = self.reports.parse_date(date_text)
        return self.reports.generate_daily(report_date, now)

    def regenerate_weekly(self, date_text: str | None = None) -> dict[str, Any]:
        now = self._now()
        report_date = self.reports.parse_date(date_text)
        return self.reports.generate_weekly(report_date, now)

    def _parse_payload(self, payload: dict[str, Any]) -> dict[str, Any]:
        event = payload.get("event") or {}
        message = event.get("message") or payload.get("message") or {}
        sender = event.get("sender") or {}
        content = self._parse_content(message.get("content") or payload.get("content") or {})
        message_id = (
            payload.get("message_id")
            or message.get("message_id")
            or payload.get("event_id")
            or payload.get("uuid")
        )
        if not message_id:
            message_id = self._stable_id("payload", json.dumps(payload, ensure_ascii=False, sort_keys=True))
        sender_id = payload.get("sender_id") or sender.get("sender_id", {}).get("user_id")
        return {
            "message_id": str(message_id),
            "chat_id": payload.get("chat_id") or message.get("chat_id"),
            "sender_id": sender_id,
            "message_type": payload.get("message_type") or message.get("message_type") or "image",
            "subject": payload.get("subject") or content.get("subject") or "math",
            "grade": payload.get("grade") or content.get("grade") or "grade7",
            "note": payload.get("note") or content.get("note") or content.get("text") or "",
            "image_key": payload.get("image_key") or content.get("image_key"),
            "image_base64": payload.get("image_base64") or content.get("image_base64"),
            "image_filename": payload.get("image_filename") or content.get("image_filename"),
            "local_image_path": (
                payload.get("local_image_path")
                or payload.get("image_path")
                or content.get("local_image_path")
                or content.get("image_path")
            ),
        }

    def _parse_content(self, content: Any) -> dict[str, Any]:
        if isinstance(content, dict):
            return content
        if isinstance(content, str):
            try:
                parsed = json.loads(content)
            except json.JSONDecodeError:
                return {"text": content}
            return parsed if isinstance(parsed, dict) else {"text": content}
        return {}

    def _save_inbound_image(
        self,
        message_id: str,
        parsed: dict[str, Any],
        source: str,
    ) -> tuple[Path, dict[str, Any]]:
        image_key = parsed.get("image_key")
        image_base64 = parsed.get("image_base64")
        if image_base64:
            try:
                data = base64.b64decode(image_base64, validate=True)
            except ValueError:
                data = b""
            if data:
                suffix = self._suffix_from_filename(parsed.get("image_filename")) or ".jpg"
                path = self.obsidian.save_image_bytes(message_id, data, suffix)
                return path, {
                    "mode": "base64_upload",
                    "bytes": len(data),
                    "filename": parsed.get("image_filename"),
                }

        if (
            source == "feishu"
            and image_key
            and self.settings.feishu_download_resources
            and self.settings.feishu_app_id
            and self.settings.feishu_app_secret
        ):
            client = FeishuClient(self.settings)
            try:
                resource = client.download_message_resource(
                    message_id=message_id,
                    file_key=image_key,
                    resource_type="image",
                )
            except FeishuClientError as exc:
                fallback = self.obsidian.save_local_image(message_id, parsed.get("local_image_path"))
                return fallback, {
                    "mode": "fallback_local_stub",
                    "image_key": image_key,
                    "error": str(exc),
                }
            path = self.obsidian.save_image_bytes(message_id, resource.data, resource.suffix)
            return path, {
                "mode": "feishu_resource",
                "image_key": image_key,
                "content_type": resource.content_type,
                "bytes": len(resource.data),
            }

        path = self.obsidian.save_local_image(message_id, parsed.get("local_image_path"))
        return path, {
            "mode": "local_stub" if not parsed.get("local_image_path") else "local_file",
            "image_key": image_key,
        }

    def _suffix_from_filename(self, filename: str | None) -> str | None:
        if not filename:
            return None
        suffix = Path(filename).suffix.strip()
        return suffix or None

    def _normalize_external_analysis(
        self,
        *,
        analysis: dict[str, Any],
        mistake_id: str,
        message_id: str,
        image_path: Path,
        subject: str,
        grade: str,
        note: str,
        today: str,
        source: str,
    ) -> dict[str, Any]:
        question_items = self._normalize_question_items(
            analysis.get("question_items") or analysis.get("questions") or []
        )
        question_items, math_verification = self.math_verifier.verify_question_items(question_items)
        expected_question_count = self._parse_positive_int(
            analysis.get("expected_question_count")
            or analysis.get("total_question_count")
            or analysis.get("question_count")
        )
        confirmation_summary = self._build_confirmation_summary(
            question_items,
            math_verification,
            expected_question_count=expected_question_count,
        )
        title = analysis.get("title") or analysis.get("worksheet_title") or "External vision mistake analysis"
        question_text = analysis.get("question_text") or self._question_items_text(question_items)
        student_answer = analysis.get("student_answer") or analysis.get("student_answers") or ""
        correct_answer = analysis.get("correct_answer") or analysis.get("correct_answers") or ""
        root_cause = (
            analysis.get("root_cause")
            or analysis.get("summary")
            or "External vision analysis submitted by Hermes."
        )
        return {
            "schema_version": str(analysis.get("schema_version") or "0.1"),
            "provider": str(analysis.get("provider") or "hermes"),
            "model": str(analysis.get("model") or analysis.get("model_name") or "external-vision"),
            "prompt_version": str(analysis.get("prompt_version") or "external-analysis-v0.1"),
            "mistake_id": mistake_id,
            "message_id": message_id,
            "subject": str(analysis.get("subject") or subject),
            "grade": str(analysis.get("grade") or grade),
            "date": str(analysis.get("date") or today),
            "title": str(title),
            "question_text": str(question_text or "See original image and external analysis JSON."),
            "student_answer": self._stringify_answer(student_answer),
            "correct_answer": self._stringify_answer(correct_answer),
            "concepts": self._normalize_list(analysis.get("concepts") or ["linear equation"]),
            "error_types": self._normalize_error_types(analysis.get("error_types") or analysis.get("errors")),
            "root_cause": str(root_cause),
            "severity": self._clamp_int(analysis.get("severity"), default=3, low=1, high=5),
            "confidence": self._clamp_float(analysis.get("confidence"), default=0.8, low=0.0, high=1.0),
            "status": "waiting_confirmation",
            "parent_guidance": str(
                analysis.get("parent_guidance")
                or "Ask the child to re-solve the marked wrong steps and explain the sign changes."
            ),
            "image_path": str(image_path),
            "note": note,
            "source": source,
            "question_items": question_items,
            "expected_question_count": expected_question_count,
            "extracted_question_count": len(question_items),
            "math_verification": math_verification,
            "confirmation_summary": confirmation_summary,
            "external_analysis": analysis,
        }

    def _build_confirmation_summary(
        self,
        question_items: list[dict[str, Any]],
        math_verification: dict[str, Any],
        *,
        expected_question_count: int | None = None,
    ) -> dict[str, Any]:
        wrong_items = [
            item.get("id") for item in question_items if item.get("is_correct") is False
        ]
        review_items = [
            item.get("id") for item in question_items if item.get("needs_parent_review")
        ]
        total_questions = len(question_items)
        missing_count = max((expected_question_count or 0) - total_questions, 0)
        missing_question_numbers = list(
            range(total_questions + 1, total_questions + missing_count + 1)
        )
        extraction_complete = missing_count == 0
        return {
            "total_questions": total_questions,
            "expected_question_count": expected_question_count,
            "extracted_question_count": total_questions,
            "missing_question_count": missing_count,
            "missing_question_numbers": missing_question_numbers,
            "extraction_complete": extraction_complete,
            "verified_questions": int(math_verification.get("verified_count") or 0),
            "wrong_questions": [item for item in wrong_items if item is not None],
            "needs_parent_review_questions": [item for item in review_items if item is not None],
            "needs_parent_review_count": int(
                math_verification.get("needs_parent_review_count") or 0
            )
            + missing_count,
            "message": self._confirmation_summary_message(
                question_items,
                math_verification,
                expected_question_count=expected_question_count,
                missing_count=missing_count,
            ),
        }

    def _confirmation_summary_message(
        self,
        question_items: list[dict[str, Any]],
        math_verification: dict[str, Any],
        *,
        expected_question_count: int | None = None,
        missing_count: int = 0,
    ) -> str:
        total = len(question_items)
        verified = int(math_verification.get("verified_count") or 0)
        review_count = int(math_verification.get("needs_parent_review_count") or 0)
        wrong_count = len([item for item in question_items if item.get("is_correct") is False])
        expected_text = f", expected {expected_question_count}" if expected_question_count else ""
        missing_text = f", {missing_count} missing from extraction" if missing_count else ""
        return (
            f"{total} question(s){expected_text}, {verified} verified by Shensi, "
            f"{wrong_count} marked wrong, {review_count + missing_count} need parent review"
            f"{missing_text}."
        )

    def _can_auto_confirm_external_analysis(self, analysis: dict[str, Any] | None) -> bool:
        if not analysis:
            return False
        summary = analysis.get("confirmation_summary") or {}
        return (
            bool(summary.get("extraction_complete", True))
            and int(summary.get("needs_parent_review_count") or 0) == 0
        )

    def _auto_confirm_blocked_payload(self, analysis: dict[str, Any] | None) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "auto_confirm_blocked": True,
            "auto_confirm_blocked_reason": "parent review required",
        }
        if analysis and analysis.get("confirmation_summary"):
            payload["confirmation_summary"] = analysis["confirmation_summary"]
        return payload

    def _normalize_question_items(self, items: Any) -> list[dict[str, Any]]:
        if not isinstance(items, list):
            return []

        normalized: list[dict[str, Any]] = []
        for index, item in enumerate(items, start=1):
            if not isinstance(item, dict):
                normalized.append(
                    {
                        "id": index,
                        "question": str(item),
                        "student_steps": [],
                        "student_answer": "",
                        "correct_answer": "",
                        "is_correct": None,
                        "error_reason": "",
                    }
                )
                continue

            is_correct = item.get("is_correct")
            if is_correct is None:
                is_correct = item.get("correct")
            if is_correct is None:
                is_correct = self._parse_verdict(item.get("verdict") or item.get("result"))

            student_steps = (
                item.get("student_steps")
                or item.get("steps")
                or item.get("student_solution")
                or item.get("student_process")
                or item.get("solution_steps")
                or item.get("recognized_steps")
                or []
            )
            normalized.append(
                {
                    "id": item.get("id") or item.get("number") or index,
                    "question": item.get("question") or item.get("title") or f"Question {index}",
                    "type": item.get("type") or item.get("question_type") or "",
                    "student_steps": self._normalize_steps(student_steps),
                    "student_answer": item.get("student_answer") or item.get("answer") or "",
                    "correct_answer": item.get("correct_answer") or item.get("expected_answer") or "",
                    "is_correct": is_correct,
                    "error_reason": (
                        item.get("error_reason")
                        or item.get("reason")
                        or item.get("mistake_reason")
                        or item.get("root_cause")
                        or ""
                    ),
                    "concept": item.get("concept") or item.get("knowledge_point") or "",
                    "error_type": item.get("error_type") or item.get("error_types") or "",
                    "sub_items": self._normalize_sub_items(
                        item.get("sub_items") or item.get("parts") or item.get("sub_questions") or []
                    ),
                }
            )
        return normalized

    def _normalize_sub_items(self, items: Any) -> list[dict[str, Any]]:
        if not isinstance(items, list):
            return []

        normalized: list[dict[str, Any]] = []
        for index, item in enumerate(items, start=1):
            if not isinstance(item, dict):
                normalized.append(
                    {
                        "label": f"({index})",
                        "is_correct": None,
                        "error_reason": str(item),
                        "concept": "",
                    }
                )
                continue

            is_correct = item.get("is_correct")
            if is_correct is None:
                is_correct = item.get("correct")
            if is_correct is None:
                is_correct = self._parse_verdict(item.get("verdict") or item.get("result"))
            normalized.append(
                {
                    "label": str(item.get("label") or item.get("id") or item.get("number") or f"({index})"),
                    "is_correct": is_correct,
                    "error_reason": (
                        item.get("error_reason")
                        or item.get("reason")
                        or item.get("mistake_reason")
                        or ""
                    ),
                    "concept": item.get("concept") or item.get("knowledge_point") or "",
                }
            )
        return normalized

    def _question_items_text(self, items: Any) -> str:
        if not isinstance(items, list):
            return ""
        parts: list[str] = []
        for index, item in enumerate(items, start=1):
            if not isinstance(item, dict):
                parts.append(f"{index}. {item}")
                continue
            question = item.get("question") or item.get("title") or f"Question {index}"
            steps = self._stringify_answer(item.get("student_steps") or item.get("steps") or "")
            verdict = item.get("verdict")
            if verdict is None:
                verdict = item.get("is_correct")
            parts.append(f"{index}. {question}\nStudent steps: {steps}\nVerdict: {verdict}")
        return "\n\n".join(parts)

    def _normalize_steps(self, value: Any) -> list[str]:
        if isinstance(value, list):
            return [str(item) for item in value if str(item).strip()]
        if isinstance(value, str):
            return [line.strip() for line in value.splitlines() if line.strip()]
        if isinstance(value, dict):
            return [json.dumps(value, ensure_ascii=False)]
        if value is None:
            return []
        return [str(value)]

    def _parse_verdict(self, value: Any) -> bool | None:
        if isinstance(value, bool):
            return value
        if value is None:
            return None
        text = str(value).strip().lower()
        if text in {"true", "correct", "right", "yes", "ok", "pass", "对", "正确"}:
            return True
        if text in {"false", "wrong", "incorrect", "no", "fail", "错", "错误"}:
            return False
        return None

    def _parse_positive_int(self, value: Any) -> int | None:
        if value is None or isinstance(value, bool):
            return None
        try:
            parsed = int(value)
        except (TypeError, ValueError):
            return None
        return parsed if parsed > 0 else None

    def _stringify_answer(self, value: Any) -> str:
        if isinstance(value, str):
            return value
        if isinstance(value, list):
            return "\n".join(str(item) for item in value)
        if isinstance(value, dict):
            return json.dumps(value, ensure_ascii=False, indent=2)
        return "" if value is None else str(value)

    def _normalize_list(self, value: Any) -> list[str]:
        if isinstance(value, str):
            return [value]
        if isinstance(value, list):
            return [str(item) for item in value if str(item).strip()]
        return []

    def _normalize_error_types(self, value: Any) -> list[str]:
        aliases = {
            "计算错误": "calculation_error",
            "計算錯誤": "calculation_error",
            "calculation": "calculation_error",
            "漏乘": "missed_condition",
            "漏乘括号": "missed_condition",
            "漏乘括號": "missed_condition",
            "审题漏条件": "missed_condition",
            "跳步": "step_skipped",
            "步骤跳跃": "step_skipped",
            "step skipped": "step_skipped",
            "移项符号错": "calculation_error",
            "移项符号错误": "calculation_error",
            "符号错误": "calculation_error",
            "概念不清": "concept_unclear",
            "方法不会": "method_missing",
            "表达不规范": "expression_irregular",
            "粗心": "attention_careless",
            "迁移困难": "transfer_difficulty",
            "时间管理": "time_management",
        }
        allowed = {
            "concept_unclear",
            "missed_condition",
            "method_missing",
            "calculation_error",
            "memory_weak",
            "expression_irregular",
            "step_skipped",
            "attention_careless",
            "transfer_difficulty",
            "time_management",
        }
        normalized: list[str] = []
        for item in self._normalize_list(value):
            key = aliases.get(item.strip(), item.strip())
            if key in allowed and key not in normalized:
                normalized.append(key)
        return normalized or ["calculation_error"]

    def _clamp_int(self, value: Any, *, default: int, low: int, high: int) -> int:
        try:
            parsed = int(value)
        except (TypeError, ValueError):
            parsed = default
        return max(low, min(high, parsed))

    def _clamp_float(self, value: Any, *, default: float, low: float, high: float) -> float:
        try:
            parsed = float(value)
        except (TypeError, ValueError):
            parsed = default
        return max(low, min(high, parsed))

    def _apply_overrides(self, analysis: dict[str, Any], overrides: dict[str, Any]) -> dict[str, Any]:
        allowed = {
            "subject",
            "grade",
            "date",
            "title",
            "question_text",
            "student_answer",
            "correct_answer",
            "concepts",
            "error_types",
            "root_cause",
            "severity",
            "confidence",
            "parent_guidance",
        }
        updated = dict(analysis)
        for key, value in overrides.items():
            if key in allowed:
                updated[key] = value
        return updated

    def _mistake_id(self, message_id: str) -> str:
        return self._stable_id("mistake", message_id)

    def _stable_id(self, *parts: str) -> str:
        raw = "::".join(parts)
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]

    def _now(self) -> str:
        try:
            tz = ZoneInfo(self.settings.timezone)
        except ZoneInfoNotFoundError:
            tz = timezone(timedelta(hours=8))
        return datetime.now(tz).isoformat(timespec="seconds")
