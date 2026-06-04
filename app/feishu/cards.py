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
    wrong_label = "\u89c4\u5219\u786e\u8ba4\u9519\u9898" if not unsupported_ids else "\u521d\u5224\u9519\u9898"
    summary_lines = [
        f"\u5171 {total_questions} \u9898\uff5c\u89c4\u5219\u9a8c\u7b97 {verified_questions}/{total_questions}",
        f"{wrong_label}\uff1a{_format_ids(wrong_ids)}",
    ]
    if unsupported_ids:
        summary_lines.append(f"\u4ec5\u6a21\u578b\u5224\u65ad\uff1a{_format_ids(unsupported_ids)}")
    if review_ids:
        summary_lines.append(f"\u5efa\u8bae\u5bb6\u957f\u590d\u6838\uff1a{_format_ids(review_ids)}")
    if summary.get("extraction_complete") is False:
        missing_ids = summary.get("missing_question_numbers") or []
        summary_lines.append(f"\u53ef\u80fd\u6f0f\u9898\uff1a{_format_ids(missing_ids)}")

    elements: list[dict[str, Any]] = [
        {
            "tag": "div",
            "text": {
                "tag": "lark_md",
                "content": "**\u5206\u6790\u6982\u89c8**\n" + "\n".join(summary_lines),
            },
        }
    ]
    question_lines = _question_lines(questions)
    if question_lines:
        elements.append(
            {
                "tag": "div",
                "text": {
                    "tag": "lark_md",
                    "content": "**\u9010\u9898\u5224\u65ad**\n" + "\n".join(question_lines),
                },
            }
        )
    if pending.get("root_cause"):
        elements.append(
            {
                "tag": "div",
                "text": {
                    "tag": "lark_md",
                    "content": f"**\u4e3b\u8981\u539f\u56e0**\uff1a{_compact_text(pending['root_cause'], 110)}",
                },
            }
        )
    concepts = pending.get("concepts") or []
    if concepts:
        elements.append(
            {
                "tag": "div",
                "text": {
                    "tag": "lark_md",
                    "content": f"**\u77e5\u8bc6\u70b9**\uff1a{_compact_list(concepts)}",
                },
            }
        )
    if pending.get("parent_guidance"):
        elements.append(
            {
                "tag": "div",
                "text": {
                    "tag": "lark_md",
                    "content": f"**\u5bb6\u957f\u5f15\u5bfc**\uff1a{_compact_text(pending['parent_guidance'], 110)}",
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


def _question_lines(questions: list[dict[str, Any]], limit: int = 8) -> list[str]:
    lines = []
    for item in questions[:limit]:
        question_id = item.get("id") or "?"
        status = _question_status(item)
        brief = _question_brief(item)
        lines.append(f"{status} **\u7b2c{question_id}\u9898**\uff1a{_compact_text(brief, 86)}")
    remaining = len(questions) - limit
    if remaining > 0:
        lines.append(f"\u8fd8\u6709 {remaining} \u9898\u672a\u5728\u5361\u7247\u5c55\u5f00\uff0c\u53ef\u786e\u8ba4\u540e\u8fdb\u5165\u9519\u9898\u5e93\u67e5\u770b\u3002")
    return lines


def _question_status(item: dict[str, Any]) -> str:
    if item.get("needs_parent_review"):
        if item.get("is_correct") is False:
            return "\u26a0\ufe0f \u521d\u5224\u9519"
        if item.get("is_correct") is True:
            return "\u26a0\ufe0f \u521d\u5224\u5bf9"
        return "\u26a0\ufe0f \u5efa\u8bae\u590d\u6838"
    if item.get("is_correct") is False:
        return "\u274c \u9519\u9898"
    if item.get("is_correct") is True:
        return "\u2705 \u6b63\u786e"
    return "\u2022"


def _question_brief(item: dict[str, Any]) -> str:
    sub_items = _sub_item_brief(item.get("sub_items") or [])
    if sub_items:
        return sub_items

    reason = str(item.get("error_reason") or "").strip()
    review_reason = str(item.get("review_reason") or "").strip()
    question = str(item.get("question") or "").strip()
    parts = []
    if reason:
        parts.append(_short_reason(reason))
    elif review_reason:
        parts.append(_short_reason(review_reason))
    elif question:
        parts.append(question)
    return "\uff1a".join(parts) or "\u6682\u65e0\u8be6\u7ec6\u8bf4\u660e"


def _sub_item_brief(items: list[Any], limit: int = 4) -> str:
    parts = []
    for index, raw in enumerate(items[:limit], start=1):
        if not isinstance(raw, dict):
            continue
        label = str(raw.get("label") or f"({index})")
        reason = _short_reason(raw.get("error_reason") or raw.get("concept") or "")
        status = _sub_item_status(raw.get("is_correct"))
        if reason:
            parts.append(f"{label}{status}{reason}")
        else:
            parts.append(f"{label}{status}\u5efa\u8bae\u590d\u6838")
    remaining = len(items) - limit
    if remaining > 0:
        parts.append(f"\u8fd8\u6709{remaining}\u5c0f\u9898")
    return "\uff1b".join(parts)


def _sub_item_status(is_correct: Any) -> str:
    if is_correct is True:
        return "\u5bf9\uff1a"
    if is_correct is False:
        return "\u9519\uff1a"
    return "\u590d\u6838\uff1a"


def _short_reason(value: Any) -> str:
    text = " ".join(str(value or "").split())
    replacements = (
        ("\u5224\u65ad\u4f9d\u636e\uff1a", ""),
        ("Verification:", ""),
        ("deterministic verifier overrode the LLM verdict", "\u89c4\u5219\u9a8c\u7b97\u4e0e\u6a21\u578b\u5224\u65ad\u4e0d\u4e00\u81f4"),
        ("verification unsupported", "\u6682\u65e0\u89c4\u5219\u9a8c\u7b97"),
    )
    for source, target in replacements:
        text = text.replace(source, target)
    return text.strip()


def _compact_list(values: list[Any], limit: int = 6) -> str:
    cleaned = [_display_concept(item) for item in values if str(item).strip()]
    if not cleaned:
        return "\u5f85\u5f52\u7eb3"
    visible = "\u3001".join(cleaned[:limit])
    if len(cleaned) > limit:
        return f"{visible} \u7b49"
    return visible


def _display_concept(value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    mapping = {
        "quadratic_function": "\u4e8c\u6b21\u51fd\u6570",
        "similar_triangles": "\u76f8\u4f3c\u4e09\u89d2\u5f62",
        "trigonometry": "\u9510\u89d2\u4e09\u89d2\u6bd4",
        "linear_function": "\u4e00\u6b21\u51fd\u6570",
        "quadratic_function_application": "\u4e8c\u6b21\u51fd\u6570\u5e94\u7528",
    }
    return mapping.get(text, text.replace("_", " "))


def _compact_text(text: Any, limit: int = 90) -> str:
    value = " ".join(str(text).split())
    if len(value) <= limit:
        return value
    return f"{value[:limit].rstrip()}..."
