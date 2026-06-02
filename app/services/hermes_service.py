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
        question_lines = []
        for item in payload.get("questions") or []:
            verdict = "正确" if item.get("is_correct") is True else "错误" if item.get("is_correct") is False else "待确认"
            review = "，需家长看一下" if item.get("needs_parent_review") else ""
            question_lines.append(
                f"- 第{item['id']}题：{verdict}{review}。学生答案：{item.get('student_answer') or '未识别'}；"
                f"正确答案：{item.get('correct_answer') or '未识别'}。"
            )

        wrong_ids = summary.get("wrong_questions") or [
            item["id"] for item in payload.get("questions") or [] if item.get("is_correct") is False
        ]
        review_ids = summary.get("needs_parent_review_questions") or [
            item["id"] for item in payload.get("questions") or [] if item.get("needs_parent_review")
        ]
        lines = [
            f"已分析完成：《{payload.get('title') or '未命名错题'}》。",
            f"共 {summary.get('total_questions', len(payload.get('questions') or []))} 题，"
            f"慎思已验算 {summary.get('verified_questions', 0)} 题。",
        ]
        if wrong_ids:
            lines.append(f"错题：第{', '.join(str(item) for item in wrong_ids)}题。")
        else:
            lines.append("没有发现明确错题。")
        if review_ids:
            lines.append(f"需要你看一眼：第{', '.join(str(item) for item in review_ids)}题。")
        if question_lines:
            lines.append("题目摘要：")
            lines.extend(question_lines)
        if payload.get("root_cause"):
            lines.append(f"主要原因：{payload['root_cause']}")
        if payload.get("parent_guidance"):
            lines.append(f"家长引导：{payload['parent_guidance']}")
        lines.append("确认无误后，直接回复“确认入库”；不想保存就回复“丢弃”。")
        return "\n".join(lines)
