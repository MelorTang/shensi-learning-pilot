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
                "reply_text": "\u5f53\u524d\u6ca1\u6709\u5f85\u786e\u8ba4\u7684\u9519\u9898\u3002",
            }

        mistake = items[0]
        analysis = self.sqlite.read_json_file(mistake.get("raw_json_path")) or {}
        payload = self._pending_payload(mistake, analysis)
        payload["found"] = True
        payload["reply_text"] = self._pending_reply_text(payload)
        return payload

    def _pending_payload(self, mistake: dict[str, Any], analysis: dict[str, Any]) -> dict[str, Any]:
        questions = []
        unsupported_ids: list[int] = []
        conflict_ids: list[int] = []
        for index, item in enumerate(analysis.get("question_items") or [], start=1):
            verification = item.get("verification") or {}
            question_id = item.get("id") or index
            verification_status = verification.get("status")
            conflict_with_llm = bool(verification.get("conflict_with_llm"))
            if verification_status != "verified":
                unsupported_ids.append(question_id)
            if conflict_with_llm:
                conflict_ids.append(question_id)
            is_correct = item.get("is_correct")
            questions.append(
                {
                    "id": question_id,
                    "question": item.get("question") or "",
                    "concept": item.get("concept") or "",
                    "error_reason": item.get("error_reason") or "",
                    "student_answer": item.get("student_answer") or "",
                    "correct_answer": item.get("correct_answer") or "",
                    "is_correct": is_correct,
                    "verification_status": verification_status,
                    "verification_method": verification.get("method"),
                    "verification_conflict_with_llm": conflict_with_llm,
                    "needs_parent_review": bool(item.get("needs_parent_review")),
                    "sub_items": item.get("sub_items") or [],
                }
            )

        confirmation_summary = analysis.get("confirmation_summary") or {}
        total_questions = confirmation_summary.get("total_questions", len(questions))
        verified_questions = confirmation_summary.get("verified_questions", 0)
        verification_summary = {
            "total_questions": total_questions,
            "verified_question_count": verified_questions,
            "unsupported_question_count": len(unsupported_ids),
            "unsupported_question_ids": unsupported_ids,
            "conflict_question_count": len(conflict_ids),
            "conflict_question_ids": conflict_ids,
        }

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
            "confirmation_summary": confirmation_summary,
            "verification_summary": verification_summary,
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
        verification_summary = payload.get("verification_summary") or {}
        wrong_ids = summary.get("wrong_questions") or [
            item["id"] for item in payload.get("questions") or [] if item.get("is_correct") is False
        ]
        review_ids = summary.get("needs_parent_review_questions") or [
            item["id"] for item in payload.get("questions") or [] if item.get("needs_parent_review")
        ]
        unsupported_ids = verification_summary.get("unsupported_question_ids") or []
        conflict_ids = verification_summary.get("conflict_question_ids") or []
        total = summary.get("total_questions", len(payload.get("questions") or []))
        verified = verification_summary.get(
            "verified_question_count",
            summary.get("verified_questions", 0),
        )

        lines = [
            f"\u5206\u6790\u5b8c\u6210\uff1a\u300a{payload.get('title') or '\u672a\u547d\u540d\u9519\u9898'}\u300b",
            f"\u5171 {total} \u9898\uff0c\u89c4\u5219\u9a8c\u7b97 {verified} \u9898\u3002",
        ]
        if summary.get("extraction_complete") is False:
            expected = summary.get("expected_question_count") or "\u672a\u77e5"
            extracted = summary.get("extracted_question_count") or len(payload.get("questions") or [])
            missing = summary.get("missing_question_numbers") or []
            missing_text = (
                f"\u7b2c{', '.join(str(item) for item in missing)}\u9898"
                if missing
                else "\u90e8\u5206\u9898\u76ee"
            )
            lines.append(
                f"\u6ce8\u610f\uff1a\u56fe\u7247\u91cc\u9884\u8ba1\u6709 {expected} \u9898\uff0c\u4f46\u8fd9\u6b21\u53ea\u62bd\u53d6\u5230 {extracted} \u9898\uff0c"
                f"\u53ef\u80fd\u6f0f\u4e86{missing_text}\u3002"
            )
        if unsupported_ids:
            lines.append(
                f"\u5176\u4e2d\u7b2c{', '.join(str(item) for item in unsupported_ids)}\u9898"
                "\u6682\u65f6\u53ea\u505a\u89c6\u89c9\u6a21\u578b\u5224\u65ad\uff0c\u5efa\u8bae\u4eba\u5de5\u786e\u8ba4\u3002"
            )
        if conflict_ids:
            lines.append(
                f"\u7b2c{', '.join(str(item) for item in conflict_ids)}\u9898"
                "\u51fa\u73b0\u201c\u89c4\u5219\u9a8c\u7b97\u201d\u4e0e\u201c\u6a21\u578b\u5224\u65ad\u201d\u4e0d\u4e00\u81f4\u3002"
            )
        if wrong_ids:
            lines.append(f"\u9519\u9898\uff1a\u7b2c{', '.join(str(item) for item in wrong_ids)}\u9898\u3002")
        else:
            lines.append("\u6ca1\u6709\u53d1\u73b0\u660e\u786e\u9519\u9898\u3002")
        if review_ids:
            lines.append(f"\u9700\u8981\u4f60\u770b\u4e00\u773c\uff1a\u7b2c{', '.join(str(item) for item in review_ids)}\u9898\u3002")
        if payload.get("root_cause"):
            lines.append(f"\u4e3b\u8981\u539f\u56e0\uff1a{self._compact(payload['root_cause'])}")
        if payload.get("parent_guidance"):
            lines.append(f"\u5bb6\u957f\u5f15\u5bfc\uff1a{self._compact(payload['parent_guidance'])}")
        lines.append("\u8bf7\u5728\u5361\u7247\u91cc\u786e\u8ba4\u5165\u5e93\u6216\u4e22\u5f03\u3002")
        return "\n".join(lines)

    def _compact(self, value: Any, limit: int = 70) -> str:
        text = " ".join(str(value).split())
        if len(text) <= limit:
            return text
        return f"{text[:limit].rstrip()}..."
