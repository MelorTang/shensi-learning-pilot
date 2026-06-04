from __future__ import annotations

import json
import time
from typing import Any

from fastapi import APIRouter, HTTPException, Request

from app.config import Settings
from app.feishu.cards import build_pending_mistake_card
from app.feishu.client import FeishuClient, FeishuClientError
from app.models.schemas import ConfirmationRequest
from app.services.hermes_service import HermesService
from app.services.sqlite_service import SQLiteService
from app.services.workflow_service import MistakeWorkflowService


router = APIRouter(prefix="/feishu", tags=["feishu"])


@router.post("/webhook")
async def receive_webhook(request: Request) -> dict[str, Any]:
    payload = await request.json()
    settings: Settings = request.app.state.settings

    if payload.get("encrypt"):
        raise HTTPException(
            status_code=501,
            detail="encrypted Feishu events are not implemented yet; disable Encrypt Key for MVP",
        )

    challenge = payload.get("challenge")
    if challenge:
        if settings.feishu_verification_token and payload.get("token") != settings.feishu_verification_token:
            raise HTTPException(status_code=403, detail="invalid verification token")
        return {"challenge": challenge}

    if settings.feishu_verification_token and payload.get("token") not in {
        settings.feishu_verification_token,
        None,
    }:
        raise HTTPException(status_code=403, detail="invalid verification token")

    workflow = MistakeWorkflowService(settings)
    result = workflow.submit_payload(payload, source="feishu", auto_confirm=bool(payload.get("auto_confirm")))
    if settings.feishu_reply_enabled:
        _try_reply(settings, result)
    return result


@router.post("/card-callback")
async def receive_card_callback(request: Request) -> dict[str, Any]:
    start = time.perf_counter()
    payload = await request.json()
    challenge = payload.get("challenge")
    if challenge:
        return {"challenge": challenge}

    action_value = _extract_card_action_value(payload)
    action = action_value.get("action")
    mistake_id = action_value.get("mistake_id")
    if not action or not mistake_id:
        raise HTTPException(status_code=400, detail="missing card action or mistake_id")
    _log_card_callback(
        "start",
        action=action,
        mistake_id=str(mistake_id),
        elapsed_ms=_elapsed_ms(start),
    )

    settings: Settings = request.app.state.settings
    workflow = MistakeWorkflowService(settings)
    try:
        if action == "shensi_confirm":
            existing = workflow.sqlite.get_mistake(str(mistake_id))
            if existing and existing.get("status") == "confirmed":
                message = "这条错题已确认入库，无需重复操作。"
                delivery = _try_reply_to_card_action(settings, payload, message)
                _log_card_callback(
                    "already_confirmed",
                    action=action,
                    mistake_id=str(mistake_id),
                    delivery_mode=(delivery or {}).get("mode"),
                    elapsed_ms=_elapsed_ms(start),
                )
                return _card_callback_response(
                    message,
                    {"status": "confirmed", "mistake_id": str(mistake_id), "duplicate_action": True},
                    delivery,
                )
            result = workflow.confirm_mistake(
                str(mistake_id),
                ConfirmationRequest(action="confirm", confirmed_by="feishu_card"),
            )
            message = "已确认入库。错题卡和 D+1/D+3/D+7 复习任务已更新。"
            delivery = _try_reply_to_card_action(settings, payload, message)
            _log_card_callback(
                "confirmed",
                action=action,
                mistake_id=str(mistake_id),
                delivery_mode=(delivery or {}).get("mode"),
                elapsed_ms=_elapsed_ms(start),
            )
            return _card_callback_response(message, result, delivery)
        if action == "shensi_discard":
            existing = workflow.sqlite.get_mistake(str(mistake_id))
            if existing and existing.get("status") == "discarded":
                message = "这条分析已丢弃，无需重复操作。"
                delivery = _try_reply_to_card_action(settings, payload, message)
                _log_card_callback(
                    "already_discarded",
                    action=action,
                    mistake_id=str(mistake_id),
                    delivery_mode=(delivery or {}).get("mode"),
                    elapsed_ms=_elapsed_ms(start),
                )
                return _card_callback_response(
                    message,
                    {"status": "discarded", "mistake_id": str(mistake_id), "duplicate_action": True},
                    delivery,
                )
            result = workflow.discard_mistake(str(mistake_id), confirmed_by="feishu_card")
            message = "已丢弃这条分析，不会写入错题卡或复习计划。"
            delivery = _try_reply_to_card_action(settings, payload, message)
            _log_card_callback(
                "discarded",
                action=action,
                mistake_id=str(mistake_id),
                delivery_mode=(delivery or {}).get("mode"),
                elapsed_ms=_elapsed_ms(start),
            )
            return _card_callback_response(message, result, delivery)
        if action == "shensi_reanalyze":
            message = "如需重新分析，请重新发送图片后再点击“慎思分析”。"
            delivery = _try_reply_to_card_action(settings, payload, message)
            _log_card_callback(
                "reanalyze_placeholder",
                action=action,
                mistake_id=str(mistake_id),
                delivery_mode=(delivery or {}).get("mode"),
                elapsed_ms=_elapsed_ms(start),
            )
            return _card_callback_response(message, delivery=delivery)
        if action == "shensi_modify_confirm":
            message = "需要修改时，直接回复要改的题号和内容；我会先更新分析，再请你确认入库。"
            delivery = _try_reply_to_card_action(settings, payload, message)
            _log_card_callback(
                "modify_placeholder",
                action=action,
                mistake_id=str(mistake_id),
                delivery_mode=(delivery or {}).get("mode"),
                elapsed_ms=_elapsed_ms(start),
            )
            return _card_callback_response(message, delivery=delivery)
    except ValueError as exc:
        _log_card_callback(
            "error",
            action=action,
            mistake_id=str(mistake_id),
            error=str(exc),
            elapsed_ms=_elapsed_ms(start),
        )
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    _log_card_callback(
        "unsupported",
        action=action,
        mistake_id=str(mistake_id),
        elapsed_ms=_elapsed_ms(start),
    )
    raise HTTPException(status_code=400, detail=f"unsupported card action: {action}")


def _try_reply(settings: Settings, result: dict[str, Any]) -> None:
    message_id = result.get("message_id")
    if not message_id:
        return
    client = FeishuClient(settings)
    if result.get("duplicate"):
        text = f"慎思已收到重复消息，当前状态：{result.get('status')}。"
    elif result.get("confirmation", {}).get("status") == "confirmed":
        text = "慎思已完成错题入库。错题卡、复习任务、日报和周报都已更新。"
    else:
        try:
            pending = HermesService(SQLiteService(settings.db_path)).latest_pending()
            if pending.get("found"):
                client.reply_interactive_card(
                    message_id=message_id,
                    card=build_pending_mistake_card(pending),
                )
                return
        except FeishuClientError:
            pass
        except Exception:
            pass
        text = "慎思已完成分析，正在等待你确认。请点击卡片按钮，或回复“确认入库 / 丢弃”。"
    try:
        client.reply_text(message_id=message_id, text=text)
    except FeishuClientError:
        return


def _extract_card_action_value(payload: dict[str, Any]) -> dict[str, Any]:
    action = _as_dict(payload.get("action"))
    event = _as_dict(payload.get("event"))
    event_action = _as_dict(event.get("action"))
    for candidate in (
        action.get("value"),
        event_action.get("value"),
        event.get("action_value"),
        payload.get("value"),
    ):
        parsed = _coerce_action_value(candidate)
        if parsed:
            return parsed
    return _find_action_value(payload) or {}


def _coerce_action_value(value: Any) -> dict[str, Any] | None:
    if isinstance(value, str):
        try:
            decoded = json.loads(value)
        except json.JSONDecodeError:
            return None
        return _coerce_action_value(decoded)
    if not isinstance(value, dict):
        return None

    action = value.get("action")
    mistake_id = value.get("mistake_id") or value.get("mistakeId")
    if action and mistake_id:
        normalized = dict(value)
        normalized["mistake_id"] = mistake_id
        return normalized

    for key in ("value", "payload", "action_value", "data"):
        parsed = _coerce_action_value(value.get(key))
        if parsed:
            return parsed
    return None


def _find_action_value(value: Any) -> dict[str, Any] | None:
    parsed = _coerce_action_value(value)
    if parsed:
        return parsed
    if isinstance(value, dict):
        for child in value.values():
            found = _find_action_value(child)
            if found:
                return found
    elif isinstance(value, list):
        for child in value:
            found = _find_action_value(child)
            if found:
                return found
    return None


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _try_reply_to_card_action(
    settings: Settings,
    payload: dict[str, Any],
    message: str,
) -> dict[str, Any] | None:
    start = time.perf_counter()
    client = FeishuClient(settings)
    if not client.is_configured():
        return None

    try:
        message_id = _extract_first_string(
            payload,
            (
                ("event", "context", "open_message_id"),
                ("event", "open_message_id"),
                ("context", "open_message_id"),
                ("open_message_id",),
                ("message_id",),
            ),
        )
        if message_id:
            response = client.reply_text(message_id=message_id, text=message)
            return {
                "mode": "reply",
                "message_id": message_id,
                "elapsed_ms": _elapsed_ms(start),
                "feishu_response": response,
            }

        chat_id = _extract_first_string(
            payload,
            (
                ("event", "context", "open_chat_id"),
                ("event", "open_chat_id"),
                ("context", "open_chat_id"),
                ("open_chat_id",),
                ("chat_id",),
            ),
        )
        if chat_id:
            response = client.send_text(
                receive_id=chat_id,
                receive_id_type="chat_id",
                text=message,
            )
            return {
                "mode": "send",
                "receive_id": chat_id,
                "elapsed_ms": _elapsed_ms(start),
                "feishu_response": response,
            }
    except FeishuClientError as exc:
        return {"mode": "failed", "elapsed_ms": _elapsed_ms(start), "error": str(exc)}
    return None


def _extract_first_string(
    payload: dict[str, Any],
    paths: tuple[tuple[str, ...], ...],
) -> str | None:
    for path in paths:
        current: Any = payload
        for key in path:
            if not isinstance(current, dict):
                current = None
                break
            current = current.get(key)
        if isinstance(current, str) and current:
            return current
    return None


def _card_callback_response(
    message: str,
    result: dict[str, Any] | None = None,
    delivery: dict[str, Any] | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "toast": {
            "type": "success",
            "content": message,
        },
        "reply_text": message,
    }
    if result is not None:
        payload["result"] = result
    if delivery is not None:
        payload["delivery"] = delivery
    return payload


def _elapsed_ms(start: float) -> int:
    return int((time.perf_counter() - start) * 1000)


def _log_card_callback(phase: str, **fields: Any) -> None:
    parts = [f"phase=card_callback_{phase}"]
    for key, value in fields.items():
        if value is None:
            continue
        parts.append(f"{key}={str(value).replace(chr(10), ' ')[:300]}")
    print(" ".join(parts), flush=True)
