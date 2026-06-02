from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Request

from app.config import Settings
from app.feishu.client import FeishuClient, FeishuClientError
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


def _try_reply(settings: Settings, result: dict[str, Any]) -> None:
    message_id = result.get("message_id")
    if not message_id:
        return
    if result.get("duplicate"):
        text = f"慎思已收到重复消息，当前状态：{result.get('status')}。"
    elif result.get("confirmation", {}).get("status") == "confirmed":
        text = f"慎思已完成错题入库：{result.get('mistake_id')}。"
    else:
        text = (
            "慎思已收到错题图片，已生成待确认分析。\n"
            f"mistake_id: {result.get('mistake_id')}\n"
            f"确认接口: {result.get('next', {}).get('confirm')}"
        )
    try:
        FeishuClient(settings).reply_text(message_id=message_id, text=text)
    except FeishuClientError:
        return
