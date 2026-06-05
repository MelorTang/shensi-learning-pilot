from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any
import json
import os
import re
import subprocess
import sys
import traceback
import time
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.config import Settings
from app.feishu.client import FeishuClient, FeishuClientError
from app.feishu.router_helpers import classify_intent, index_image_path, resolve_indexed_image
from app.services.workflow_service import MistakeWorkflowService


SHENSI_API_BASE_URL = "http://127.0.0.1:8000"

# ── Default paths (overridable via env) ──────────────────────────────
_HERMES_HOME = Path(os.path.expanduser("~/.hermes"))
_IMAGE_CACHE = Path(
    os.environ.get("SHENSI_IMAGE_CACHE", str(_HERMES_HOME / "image_cache"))
)
_INDEX_DIR = Path(
    os.environ.get("SHENSI_IMAGE_INDEX_DIR", str(_HERMES_HOME / "shensi_image_index"))
)
_ANALYSIS_BIN = os.environ.get(
    "SHENSI_ANALYSIS_LATEST", "/home/admin/bin/shensi-feishu-analysis-latest"
)
_DEFAULT_SUBJECT = os.environ.get("SHENSI_DEFAULT_SUBJECT", "math")
_DEFAULT_GRADE = os.environ.get("SHENSI_DEFAULT_GRADE", "grade8")


# ── Helpers reused from webhook.py ────────────────────────────────────
def _normalize_event(raw: dict[str, Any]) -> dict[str, Any]:
    if "event" in raw:
        return raw
    if "message" in raw:
        return {"event": raw}
    if "sender" in raw:
        return {"event": raw}
    return raw


# ── Existing message handler (used in default mode) ───────────────────
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


# ── Router helpers ────────────────────────────────────────────────────

def _safe_key(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]", "_", value)


def _parse_router_message(raw: dict[str, Any]) -> dict[str, Any]:
    """Extract message fields needed by the router from a Feishu event."""
    event: dict[str, Any] = raw.get("event") if isinstance(raw.get("event"), dict) else {}
    message: dict[str, Any] = (
        event.get("message") if isinstance(event.get("message"), dict) else {}
    )
    sender: dict[str, Any] = (
        event.get("sender") if isinstance(event.get("sender"), dict) else {}
    )

    message_id: str = (
        raw.get("message_id")
        or message.get("message_id")
        or event.get("message_id")
        or ""
    )
    chat_id: str = message.get("chat_id") or raw.get("chat_id") or ""
    sender_id: str = (
        sender.get("sender_id", {}).get("user_id")
        or sender.get("sender_id", {}).get("open_id")
        or raw.get("sender_id")
        or ""
    )
    message_type: str = message.get("message_type") or raw.get("message_type") or ""

    content_raw = message.get("content") or raw.get("content") or "{}"
    try:
        content: dict[str, Any] = json.loads(content_raw)
    except (json.JSONDecodeError, TypeError):
        content = {}
    text: str = content.get("text", "")
    image_key: str = content.get("image_key", "")

    return {
        "message_id": str(message_id),
        "chat_id": str(chat_id),
        "sender_id": str(sender_id),
        "message_type": str(message_type),
        "text": str(text),
        "image_key": str(image_key),
    }


def _download_and_index_image(
    message_id: str,
    image_key: str,
    chat_id: str,
    sender_id: str,
    feishu_client: FeishuClient,
) -> Path | None:
    """Download a Feishu image resource, save to cache, write index.  Returns cached path."""
    if not image_key or not feishu_client.is_configured():
        return None

    try:
        resource = feishu_client.download_message_resource(
            message_id=message_id,
            file_key=image_key,
            resource_type="image",
        )
    except FeishuClientError:
        traceback.print_exc(file=sys.stderr)
        return None

    _IMAGE_CACHE.mkdir(parents=True, exist_ok=True)
    safe_msg = _safe_key(message_id)
    cached = _IMAGE_CACHE / f"img_{safe_msg}{resource.suffix}"
    cached.write_bytes(resource.data)

    # Write index
    index_target = index_image_path(chat_id, sender_id, index_dir=_INDEX_DIR)
    index_target.parent.mkdir(parents=True, exist_ok=True)
    index_target.write_text(str(cached))

    print(
        f"router image indexed message_id={message_id} "
        f"image={cached} index={index_target} "
        f"bytes={len(resource.data)}"
    )
    return cached


def _resolve_indexed_image_for_analysis(chat_id: str, sender_id: str) -> Path | None:
    """Look up the same-chat same-sender image index.  No global-cache fallback."""
    index_target = index_image_path(chat_id, sender_id, index_dir=_INDEX_DIR)
    if index_target.exists():
        indexed = index_target.read_text().strip()
        if indexed and Path(indexed).exists():
            return Path(indexed)
    return None


def _spawn_analysis(
    chat_id: str,
    sender_id: str,
    image_path: Path,
    *,
    subject: str = _DEFAULT_SUBJECT,
    grade: str = _DEFAULT_GRADE,
) -> None:
    """Spawn ``shensi-feishu-analysis-latest`` in a detached background process."""
    cmd = [
        _ANALYSIS_BIN,
        chat_id,
        sender_id,
        subject,
        grade,
        str(image_path),
    ]
    print(f"router spawning analysis: {' '.join(cmd)}")
    subprocess.Popen(
        cmd,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )


def _shensi_post(endpoint: str, body: dict[str, Any] | None = None) -> dict[str, Any]:
    """Minimal POST to the local Shensi API."""
    url = f"{SHENSI_API_BASE_URL}{endpoint}"
    data = (
        json.dumps(body, ensure_ascii=False).encode("utf-8")
        if body
        else None
    )
    req = Request(
        url,
        data=data,
        headers={"Content-Type": "application/json; charset=utf-8"},
        method="POST",
    )
    try:
        with urlopen(req, timeout=10) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except (HTTPError, URLError, TimeoutError) as exc:
        raise RuntimeError(f"Shensi API call failed: {endpoint}: {exc}") from exc


def _shensi_get(endpoint: str) -> dict[str, Any]:
    """Minimal GET to the local Shensi API."""
    url = f"{SHENSI_API_BASE_URL}{endpoint}"
    req = Request(url, headers={}, method="GET")
    try:
        with urlopen(req, timeout=10) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except (HTTPError, URLError, TimeoutError) as exc:
        raise RuntimeError(f"Shensi API GET failed: {endpoint}: {exc}") from exc


# ── Router message handler ────────────────────────────────────────────

def _handle_message_router(
    data: Any,
    settings: Settings,
    feishu_client: FeishuClient,
) -> None:
    """Direct router: keyword/intent matching → shell script or Shensi API.

    This handler does NOT call any LLM.  Image messages trigger background
    Antigravity analysis.  Text messages are matched against a fixed
    keyword table.
    """
    import lark_oapi as lark

    raw_text = lark.JSON.marshal(data)
    raw = json.loads(raw_text)
    msg = _parse_router_message(raw)

    message_id = msg["message_id"]
    chat_id = msg["chat_id"]
    sender_id = msg["sender_id"]
    message_type = msg["message_type"]

    if not message_id:
        return

    # ── Image ──────────────────────────────────────────────────
    if message_type == "image":
        image_key = msg["image_key"]
        cached = None
        if image_key:
            cached = _download_and_index_image(
                message_id, image_key, chat_id, sender_id, feishu_client
            )
        if cached:
            _spawn_analysis(chat_id, sender_id, cached)
            reply_text = "已收到图片，正在分析，约40秒后发确认卡片。"
        else:
            reply_text = "图片已收到，但下载失败，请重发一次。"

        try:
            feishu_client.reply_text(message_id=message_id, text=reply_text)
        except FeishuClientError:
            pass
        return

    # ── Text ───────────────────────────────────────────────────
    if message_type == "text":
        text = msg["text"]
        intent = classify_intent(text)

        if intent == "shensi_analyze":
            image = _resolve_indexed_image_for_analysis(chat_id, sender_id)
            if image:
                _spawn_analysis(chat_id, sender_id, image)
                reply = "正在分析这张错题，完成后我会发确认卡片。"
            else:
                reply = "请先发送一张作业图片。"
            try:
                feishu_client.reply_text(message_id=message_id, text=reply)
            except FeishuClientError:
                pass
            return

        if intent == "confirm":
            try:
                result = _shensi_post(
                    "/hermes/pending/latest/confirm",
                    {"action": "confirm", "confirmed_by": "feishu_parent"},
                )
                reply = result.get("reply_text") or "已确认入库。"
            except RuntimeError:
                reply = "确认失败，请稍后重试。"
            try:
                feishu_client.reply_text(message_id=message_id, text=reply)
            except FeishuClientError:
                pass
            return

        if intent == "discard":
            try:
                result = _shensi_post(
                    "/hermes/pending/latest/discard",
                    {"action": "discard", "confirmed_by": "feishu_parent"},
                )
                reply = result.get("reply_text") or "已丢弃。"
            except RuntimeError:
                reply = "丢弃失败，请稍后重试。"
            try:
                feishu_client.reply_text(message_id=message_id, text=reply)
            except FeishuClientError:
                pass
            return

        if intent == "help":
            try:
                feishu_client.reply_text(
                    message_id=message_id,
                    text="发送图片自动分析。\n命令：慎思分析 / 确认入库 / 丢弃 / 帮助\n日报、复习任务、讲题请找「慎思辅导机器人」。",
                )
            except FeishuClientError:
                pass
            return

        # unknown — reply short help (no LLM)
        try:
            feishu_client.reply_text(
                message_id=message_id,
                text="我现在只处理作业图片、慎思分析、确认入库、丢弃和帮助。日报、复习任务、讲题请找「慎思辅导机器人」。",
            )
        except FeishuClientError:
            pass
        return

    # Other message types (audio, file, sticker, etc.) — ignored


# ── Card action handler (shared by all modes) ─────────────────────────

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


# ── Main ──────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run Shensi Feishu long-connection handlers."
    )
    group = parser.add_mutually_exclusive_group()
    group.add_argument(
        "--card-actions-only",
        action="store_true",
        help="Only forward Feishu card.action.trigger callbacks to Shensi.",
    )
    group.add_argument(
        "--router",
        action="store_true",
        help=(
            "Direct keyword router: handle im.message.receive_v1 with "
            "fixed intent matching (no LLM).  Also forwards card actions."
        ),
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
        raise SystemExit(
            "Please set SHENSI_FEISHU_APP_ID and SHENSI_FEISHU_APP_SECRET in .env"
        )

    feishu_client = FeishuClient(settings)

    event_builder = lark.EventDispatcherHandler.builder("", "")

    if args.router:
        event_builder.register_p2_im_message_receive_v1(
            lambda data: _handle_message_router(data, settings, feishu_client)
        )
    elif not args.card_actions_only:
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

    if args.router:
        mode = "direct router"
    elif args.card_actions_only:
        mode = "card actions only"
    else:
        mode = "messages and card actions"
    print(f"Starting Feishu long-connection client ({mode}). Press Ctrl+C to stop.")
    client.start()


if __name__ == "__main__":
    main()
