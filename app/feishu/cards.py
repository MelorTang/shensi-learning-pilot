from __future__ import annotations

from typing import Any


def build_pending_mistake_card(pending: dict[str, Any]) -> dict[str, Any]:
    """Build a Feishu card draft for a pending Shensi mistake analysis."""
    title = pending.get("title") or "慎思错题分析"
    mistake_id = pending.get("mistake_id") or ""
    questions = pending.get("questions") or []
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
    summary_lines = [
        f"共 {len(questions)} 题",
        f"错题：{_format_ids(wrong_ids)}",
    ]
    if review_ids:
        summary_lines.append(f"需确认：{_format_ids(review_ids)}")

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
                    "content": f"**主要原因**：{_compact_text(pending['root_cause'])}",
                },
            }
        )
    if pending.get("parent_guidance"):
        elements.append(
            {
                "tag": "div",
                "text": {
                    "tag": "lark_md",
                    "content": f"**家长引导**：{_compact_text(pending['parent_guidance'])}",
                },
            }
        )

    elements.append(
        {
            "tag": "action",
            "actions": [
                _button("确认入库", "primary", "shensi_confirm", mistake_id),
                _button("丢弃", "danger", "shensi_discard", mistake_id),
                _button("重新分析", "default", "shensi_reanalyze", mistake_id),
                _button("修改后入库", "default", "shensi_modify_confirm", mistake_id),
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
        return "无"
    return "、".join(f"第{item}题" for item in ids)


def _compact_text(text: Any, limit: int = 90) -> str:
    value = " ".join(str(text).split())
    if len(value) <= limit:
        return value
    return f"{value[:limit].rstrip()}..."
