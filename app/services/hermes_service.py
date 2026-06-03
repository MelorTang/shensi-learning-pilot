from __future__ import annotations

from typing import Any

from app.services.sqlite_service import SQLiteService


class HermesService:
    """Hermes-facing summaries and lightweight query helpers."""

    def __init__(self, sqlite: SQLiteService) -> None:
        self.sqlite = sqlite

    def recent_stats(self, days: int = 14) -> dict[str, Any]:
        return self.sqlite.stats(days=days)

    def concept_mistakes(self, concept_name: str) -> list[dict[str, Any]]:
        return self.sqlite.concept_mistakes(concept_name)

    def latest_pending(self) -> dict[str, Any]:
        items = self.sqlite.list_mistakes(status="waiting_confirmation")
        if not items:
            return {
                "found": False,
                "status": "none",
                "reply_text": "当前没有待确认的错题。",
            }

        mistake = items[0]
        analysis = self.sqlite.read_json_file(mistake.get("raw_json_path")) or {}
        payload = self._pending_payload(mistake, analysis)
        payload["found"] = True
        payload["reply_text"] = self._pending_reply_text(payload)
        return payload

    def _pending_payload(self, mistake: dict[str, Any], analysis: dict[str, Any]) -> dict[str, Any]:
        questions = []
        for index, item in enumerate(analysis.get("question_items") or [], start=1):
            verification = item.get("verification") or {}
            is_correct = item.get("is_correct")
            questions.append(
                {
                    "id": item.get("id") or index,
                    "question": item.get("question") or "",
                    "student_answer": item.get("student_answer") or "",
                    "correct_answer": item.get("correct_answer") or "",
                    "is_correct": is_correct,
                    "verification_status": verification.get("status"),
                    "verification_method": verification.get("method"),
                    "needs_parent_review": bool(item.get("needs_parent_review")),
                }
            )

        return {
            "status": mistake.get("status"),
            "mistake_id": mistake["id"],
            "title": analysis.get("title") or mistake.get("title"),
            "subject": analysis.get("subject") or mistake.get("subject"),
            "grade": analysis.get("grade") or mistake.get("grade"),
            "date": analysis.get("date") or mistake.get("date"),
            "concepts": analysis.get("concepts") or [],
            "error_types": analysis.get("error_types") or [],
            "root_cause": analysis.get("root_cause") or "",
            "parent_guidance": analysis.get("parent_guidance") or "",
            "confirmation_summary": analysis.get("confirmation_summary") or {},
            "extraction": {
                "expected_question_count": analysis.get("expected_question_count"),
                "extracted_question_count": analysis.get("extracted_question_count"),
            },
            "questions": questions,
            "actions": {
                "confirm_latest": "/hermes/pending/latest/confirm",
                "discard_latest": "/hermes/pending/latest/discard",
                "confirm": f"/mistakes/{mistake['id']}/confirm",
                "discard": f"/mistakes/{mistake['id']}/discard",
            },
        }

    def _pending_reply_text(self, payload: dict[str, Any]) -> str:
        summary = payload.get("confirmation_summary") or {}
        wrong_ids = summary.get("wrong_questions") or [
            item["id"] for item in payload.get("questions") or [] if item.get("is_correct") is False
        ]
        review_ids = summary.get("needs_parent_review_questions") or [
            item["id"] for item in payload.get("questions") or [] if item.get("needs_parent_review")
        ]
        total = summary.get("total_questions", len(payload.get("questions") or []))
        verified = summary.get("verified_questions", 0)
        lines = [
            f"分析完成：《{payload.get('title') or '未命名错题'}》。",
            f"共 {total} 题，已验算 {verified} 题。",
        ]
        if summary.get("extraction_complete") is False:
            expected = summary.get("expected_question_count") or "未知"
            extracted = summary.get("extracted_question_count") or len(payload.get("questions") or [])
            missing = summary.get("missing_question_numbers") or []
            missing_text = f"第{', '.join(str(item) for item in missing)}题" if missing else "部分题目"
            lines.append(
                f"注意：图片里预计有 {expected} 题，但这次只抽取到 {extracted} 题，"
                f"可能漏了{missing_text}。建议重新分析或重新发一张更清晰的图。"
            )
        if wrong_ids:
            lines.append(f"错题：第{', '.join(str(item) for item in wrong_ids)}题。")
        else:
            lines.append("没有发现明确错题。")
        if review_ids:
            lines.append(f"需要你看一眼：第{', '.join(str(item) for item in review_ids)}题。")
        if payload.get("root_cause"):
            lines.append(f"主要原因：{self._compact(payload['root_cause'])}")
        if payload.get("parent_guidance"):
            lines.append(f"家长引导：{self._compact(payload['parent_guidance'])}")
        lines.append("请在卡片里确认入库或丢弃。")
        return "\n".join(lines)

    def _compact(self, value: Any, limit: int = 70) -> str:
        text = " ".join(str(value).split())
        if len(text) <= limit:
            return text
        return f"{text[:limit].rstrip()}..."
