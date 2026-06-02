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
            concept_id = self._stable_id("concept", final_analysis["subject"], final_analysis["grade"], concept_name)
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
            concept_note = self.obsidian.write_concept_note(concept)
            concept["note_path"] = str(concept_note)
            self.sqlite.upsert_concept(concept)
            self.sqlite.link_mistake_concept(mistake_id, concept_id)
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
