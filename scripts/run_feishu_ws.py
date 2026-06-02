from __future__ import annotations

from pathlib import Path
from typing import Any
import json
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.config import Settings
from app.services.workflow_service import MistakeWorkflowService


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


def main() -> None:
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

    event_handler = (
        lark.EventDispatcherHandler.builder("", "")
        .register_p2_im_message_receive_v1(
            lambda data: _handle_message_event(data, settings)
        )
        .build()
    )
    client = lark.ws.Client(
        settings.feishu_app_id,
        settings.feishu_app_secret,
        event_handler=event_handler,
        log_level=lark.LogLevel.INFO,
    )
    print("Starting Feishu long-connection client. Press Ctrl+C to stop.")
    client.start()


if __name__ == "__main__":
    main()
