from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen
import json

from app.config import Settings


class FeishuClientError(RuntimeError):
    pass


@dataclass(frozen=True)
class FeishuResource:
    data: bytes
    content_type: str
    suffix: str


class FeishuClient:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.base_url = settings.feishu_base_url.rstrip("/")
        self._tenant_access_token: str | None = None

    def is_configured(self) -> bool:
        return bool(self.settings.feishu_app_id and self.settings.feishu_app_secret)

    def tenant_access_token(self) -> str:
        if self._tenant_access_token:
            return self._tenant_access_token
        if not self.is_configured():
            raise FeishuClientError("Missing SHENSI_FEISHU_APP_ID or SHENSI_FEISHU_APP_SECRET")

        response = self._json_request(
            "POST",
            "/open-apis/auth/v3/tenant_access_token/internal",
            body={
                "app_id": self.settings.feishu_app_id,
                "app_secret": self.settings.feishu_app_secret,
            },
            authenticated=False,
        )
        token = response.get("tenant_access_token")
        if not token:
            raise FeishuClientError(f"Feishu token response missing tenant_access_token: {response}")
        self._tenant_access_token = str(token)
        return self._tenant_access_token

    def download_message_resource(
        self,
        *,
        message_id: str,
        file_key: str,
        resource_type: str = "image",
    ) -> FeishuResource:
        query = urlencode({"type": resource_type})
        request = Request(
            f"{self.base_url}/open-apis/im/v1/messages/{message_id}/resources/{file_key}?{query}",
            headers={
                "Authorization": f"Bearer {self.tenant_access_token()}",
                "Content-Type": "application/json; charset=utf-8",
            },
            method="GET",
        )
        try:
            with urlopen(request, timeout=20) as response:
                content_type = response.headers.get("content-type", "application/octet-stream")
                return FeishuResource(
                    data=response.read(),
                    content_type=content_type,
                    suffix=self._suffix_for(content_type, resource_type),
                )
        except (HTTPError, URLError, TimeoutError) as exc:
            raise FeishuClientError(f"Failed to download Feishu resource {file_key}: {exc}") from exc

    def reply_text(self, *, message_id: str, text: str) -> dict[str, Any]:
        return self._json_request(
            "POST",
            f"/open-apis/im/v1/messages/{message_id}/reply",
            body={
                "msg_type": "text",
                "content": json.dumps({"text": text}, ensure_ascii=False),
            },
            authenticated=True,
        )

    def send_text(
        self,
        *,
        receive_id: str,
        receive_id_type: str,
        text: str,
    ) -> dict[str, Any]:
        query = urlencode({"receive_id_type": receive_id_type})
        return self._json_request(
            "POST",
            f"/open-apis/im/v1/messages?{query}",
            body={
                "receive_id": receive_id,
                "msg_type": "text",
                "content": json.dumps({"text": text}, ensure_ascii=False),
            },
            authenticated=True,
        )

    def reply_interactive_card(self, *, message_id: str, card: dict[str, Any]) -> dict[str, Any]:
        return self._json_request(
            "POST",
            f"/open-apis/im/v1/messages/{message_id}/reply",
            body={
                "msg_type": "interactive",
                "content": json.dumps(card, ensure_ascii=False),
            },
            authenticated=True,
        )

    def send_interactive_card(
        self,
        *,
        receive_id: str,
        receive_id_type: str,
        card: dict[str, Any],
    ) -> dict[str, Any]:
        query = urlencode({"receive_id_type": receive_id_type})
        return self._json_request(
            "POST",
            f"/open-apis/im/v1/messages?{query}",
            body={
                "receive_id": receive_id,
                "msg_type": "interactive",
                "content": json.dumps(card, ensure_ascii=False),
            },
            authenticated=True,
        )

    def _json_request(
        self,
        method: str,
        path: str,
        *,
        body: dict[str, Any],
        authenticated: bool,
    ) -> dict[str, Any]:
        headers = {"Content-Type": "application/json; charset=utf-8"}
        if authenticated:
            headers["Authorization"] = f"Bearer {self.tenant_access_token()}"
        request = Request(
            f"{self.base_url}{path}",
            data=json.dumps(body, ensure_ascii=False).encode("utf-8"),
            headers=headers,
            method=method,
        )
        try:
            with urlopen(request, timeout=20) as response:
                raw = response.read().decode("utf-8")
        except (HTTPError, URLError, TimeoutError) as exc:
            raise FeishuClientError(f"Feishu API request failed: {path}: {exc}") from exc

        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise FeishuClientError(f"Feishu API returned non-JSON response: {raw[:200]}") from exc
        code = parsed.get("code", 0)
        if code not in {0, "0"}:
            raise FeishuClientError(f"Feishu API returned code={code}: {parsed}")
        return parsed

    def _suffix_for(self, content_type: str, resource_type: str) -> str:
        lower = content_type.lower()
        if "png" in lower:
            return ".png"
        if "jpeg" in lower or "jpg" in lower:
            return ".jpg"
        if "gif" in lower:
            return ".gif"
        if "webp" in lower:
            return ".webp"
        if resource_type == "image":
            return ".jpg"
        return ".bin"
