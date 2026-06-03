from __future__ import annotations

from typing import Any


def build_pending_mistake_card(pending: dict[str, Any]) -> dict[str, Any]:
    """Build a Feishu card draft for a pending Shensi mistake analysis."""
    title = pending.get("title") or "\u614e\u601d\u9519\u9898\u5206\u6790"
    mistake_id = pending.get("mistake_id") or ""
    questions = pending.get("questions") or []
    summary = pending.get("confirmation_summary") or {}
    verification_summary = pending.get("verification_summary") or {}
    wrong_ids = [
        item.get("id")
        for item in questions
        if item.get("is_correct") is False and item.get("id") is not None
    ]
    review_ids = [
        item.get("id")
        for item in questions
        if item.get("needs_parent_review") and item.get("id") is not None
    ]
    unsupported_ids = verification_summary.get("unsupported_question_ids") or [
        item.get("id")
        for item in questions
        if item.get("verification_status") != "verified" and item.get("id") is not None
    ]
    total_questions = summary.get("total_questions", len(questions))
    verified_questions = verification_summary.get(
        "verified_question_count",
        summary.get("verified_questions", 0),
    )
    summary_lines = [
        f"\u5171 {total_questions} \u9898",
        f"\u89c4\u5219\u9a8c\u7b97\uff1a{verified_questions}/{total_questions}",
        f"\u9519\u9898\uff1a{_format_ids(wrong_ids)}",
    ]
    if unsupported_ids:
        summary_lines.append(f"\u4ec5\u6a21\u578b\u5224\u65ad\uff1a{_format_ids(unsupported_ids)}")
    if review_ids:
        summary_lines.append(f"\u9700\u786e\u8ba4\uff1a{_format_ids(review_ids)}")
    if summary.get("extraction_complete") is False:
        missing_ids = summary.get("missing_question_numbers") or []
        summary_lines.append(f"\u53ef\u80fd\u6f0f\u9898\uff1a{_format_ids(missing_ids)}")

    elements: list[dict[str, Any]] = [
        {
            "tag": "div",
            "text": {
                "tag": "lark_md",
                "content": "\n".join(summary_lines),
            },
        }
    ]
    if pending.get("root_cause"):
        elements.append(
            {
                "tag": "div",
                "text": {
                    "tag": "lark_md",
                    "content": f"**\u4e3b\u8981\u539f\u56e0**\uff1a{_compact_text(pending['root_cause'])}",
                },
            }
        )
    if pending.get("parent_guidance"):
        elements.append(
            {
                "tag": "div",
                "text": {
                    "tag": "lark_md",
                    "content": f"**\u5bb6\u957f\u5f15\u5bfc**\uff1a{_compact_text(pending['parent_guidance'])}",
                },
            }
        )

    elements.append(
        {
            "tag": "action",
            "actions": [
                _button("\u786e\u8ba4\u5165\u5e93", "primary", "shensi_confirm", mistake_id),
                _button("\u4e22\u5f03", "danger", "shensi_discard", mistake_id),
                _button("\u91cd\u65b0\u5206\u6790", "default", "shensi_reanalyze", mistake_id),
                _button("\u4fee\u6539\u540e\u5165\u5e93", "default", "shensi_modify_confirm", mistake_id),
            ],
        }
    )

    return {
        "config": {"wide_screen_mode": True},
        "header": {
            "template": "blue",
            "title": {"tag": "plain_text", "content": title},
        },
        "elements": elements,
    }


def _button(text: str, button_type: str, action: str, mistake_id: str) -> dict[str, Any]:
    return {
        "tag": "button",
        "text": {"tag": "plain_text", "content": text},
        "type": button_type,
        "value": {
            "action": action,
            "mistake_id": mistake_id,
        },
    }


def _format_ids(ids: list[Any]) -> str:
    if not ids:
        return "\u65e0"
    return "\u3001".join(f"\u7b2c{item}\u9898" for item in ids)


def _compact_text(text: Any, limit: int = 90) -> str:
    value = " ".join(str(text).split())
    if len(value) <= limit:
        return value
    return f"{value[:limit].rstrip()}..."
