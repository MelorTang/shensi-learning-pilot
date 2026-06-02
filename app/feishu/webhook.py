from __future__ import annotations

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
    payload = await request.json()
    challenge = payload.get("challenge")
    if challenge:
        return {"challenge": challenge}

    action_value = _extract_card_action_value(payload)
    action = action_value.get("action")
    mistake_id = action_value.get("mistake_id")
    if not action or not mistake_id:
        raise HTTPException(status_code=400, detail="missing card action or mistake_id")

    settings: Settings = request.app.state.settings
    workflow = MistakeWorkflowService(settings)
    try:
        if action == "shensi_confirm":
            result = workflow.confirm_mistake(
                str(mistake_id),
                ConfirmationRequest(action="confirm", confirmed_by="feishu_card"),
            )
            return _card_callback_response("已确认入库。错题卡和复习任务已更新。", result)
        if action == "shensi_discard":
            result = workflow.discard_mistake(str(mistake_id), confirmed_by="feishu_card")
            return _card_callback_response("已丢弃这条分析。", result)
        if action == "shensi_reanalyze":
            return _card_callback_response("重新分析功能下一步接入。现在可以重新发送图片并点击“慎思分析”。")
        if action == "shensi_modify_confirm":
            return _card_callback_response("修改后入库功能下一步接入。现在可以文字说明要修改的地方。")
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

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
        if isinstance(candidate, dict):
            return candidate
    return {}


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _card_callback_response(message: str, result: dict[str, Any] | None = None) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "toast": {
            "type": "success",
            "content": message,
        },
        "reply_text": message,
    }
    if result is not None:
        payload["result"] = result
    return payload
