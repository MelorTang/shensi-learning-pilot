from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any
import json
import sys
import traceback
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
import time

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.config import Settings
from app.services.workflow_service import MistakeWorkflowService


SHENSI_API_BASE_URL = "http://127.0.0.1:8000"


def _normalize_event(raw: dict[str, Any]) -> dict[str, Any]:
    if "event" in raw:
        return raw
    if "message" in raw:
        return {"event": raw}
    if "sender" in raw:
        return {"event": raw}
    return raw


def _handle_message_event(data: Any, settings: Settings) -> None:
    import lark_oapi as lark

    raw_text = lark.JSON.marshal(data)
    raw = json.loads(raw_text)
    payload = _normalize_event(raw)
    result = MistakeWorkflowService(settings).submit_payload(
        payload,
        source="feishu_ws",
        auto_confirm=False,
    )
    print(
        "received im.message.receive_v1 "
        f"message_id={result.get('message_id')} "
        f"mistake_id={result.get('mistake_id')} "
        f"status={result.get('status')}"
    )


def _handle_card_action(data: Any, settings: Settings) -> Any:
    import lark_oapi as lark
    from lark_oapi.event.callback.model.p2_card_action_trigger import (
        P2CardActionTriggerResponse,
    )

    raw_text = lark.JSON.marshal(data)
    raw = json.loads(raw_text)
    action = _extract_action(raw)
    mistake_id = _extract_action_value(raw).get("mistake_id") or ""
    start = time.perf_counter()
    callback_response = _post_card_callback(raw)
    elapsed_ms = int((time.perf_counter() - start) * 1000)
    toast = callback_response.get("toast") or {
        "type": "success",
        "content": callback_response.get("reply_text") or "慎思已处理卡片操作。",
    }
    print(
        "received card.action.trigger "
        f"action={action} "
        f"mistake_id={mistake_id} "
        f"post_elapsed_ms={elapsed_ms} "
        f"delivery_mode={(callback_response.get('delivery') or {}).get('mode')} "
        f"toast={toast.get('content')}",
        flush=True,
    )
    return P2CardActionTriggerResponse({"toast": toast})


def _post_card_callback(payload: dict[str, Any]) -> dict[str, Any]:
    request = Request(
        f"{SHENSI_API_BASE_URL}/feishu/card-callback",
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json; charset=utf-8"},
        method="POST",
    )
    try:
        with urlopen(request, timeout=20) as response:
            raw = response.read().decode("utf-8")
    except HTTPError as exc:
        error_body = exc.read().decode("utf-8", errors="replace")
        print(
            "card callback HTTPError "
            f"status={exc.code} reason={exc.reason} body={error_body[:1000]}",
            file=sys.stderr,
        )
        return {
            "toast": {
                "type": "error",
                "content": f"慎思处理卡片按钮失败：HTTP {exc.code}",
            }
        }
    except (URLError, TimeoutError) as exc:
        print(f"card callback request failed: {exc}", file=sys.stderr)
        return {
            "toast": {
                "type": "error",
                "content": f"慎思处理卡片按钮失败：{exc}",
            }
        }
    except Exception as exc:
        print(f"card callback unexpected error: {exc}", file=sys.stderr)
        traceback.print_exc(file=sys.stderr)
        return {
            "toast": {
                "type": "error",
                "content": "慎思处理卡片按钮失败：转发服务异常",
            }
        }
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        print(f"card callback returned non-json: {raw[:1000]}", file=sys.stderr)
        return {
            "toast": {
                "type": "error",
                "content": "慎思返回了无法解析的卡片回调结果。",
            }
        }
    return parsed if isinstance(parsed, dict) else {}


def _extract_action(payload: dict[str, Any]) -> str:
    action_value = _extract_action_value(payload)
    return str(action_value.get("action") or "unknown")


def _extract_action_value(payload: dict[str, Any]) -> dict[str, Any]:
    event = payload.get("event") if isinstance(payload.get("event"), dict) else {}
    action = payload.get("action") if isinstance(payload.get("action"), dict) else {}
    event_action = event.get("action") if isinstance(event.get("action"), dict) else {}
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


def main() -> None:
    parser = argparse.ArgumentParser(description="Run Shensi Feishu long-connection handlers.")
    parser.add_argument(
        "--card-actions-only",
        action="store_true",
        help="Only forward Feishu card.action.trigger callbacks to Shensi.",
    )
    args = parser.parse_args()

    try:
        import lark_oapi as lark
    except ImportError as exc:
        raise SystemExit(
            "Missing dependency: lark-oapi. Install it with `pip install lark-oapi` "
            "or reinstall the project dependencies."
        ) from exc

    settings = Settings.load()
    if not settings.feishu_app_id or not settings.feishu_app_secret:
        raise SystemExit("Please set SHENSI_FEISHU_APP_ID and SHENSI_FEISHU_APP_SECRET in .env")

    event_builder = lark.EventDispatcherHandler.builder("", "")
    if not args.card_actions_only:
        event_builder.register_p2_im_message_receive_v1(
            lambda data: _handle_message_event(data, settings)
        )
    event_handler = (
        event_builder.register_p2_card_action_trigger(
            lambda data: _handle_card_action(data, settings)
        ).build()
    )
    client = lark.ws.Client(
        settings.feishu_app_id,
        settings.feishu_app_secret,
        event_handler=event_handler,
        log_level=lark.LogLevel.INFO,
    )
    mode = "card actions only" if args.card_actions_only else "messages and card actions"
    print(f"Starting Feishu long-connection client ({mode}). Press Ctrl+C to stop.")
    client.start()


if __name__ == "__main__":
    main()
