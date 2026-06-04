from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class LocalUploadRequest(BaseModel):
    message_id: str | None = None
    local_image_path: str | None = None
    image_base64: str | None = None
    image_filename: str | None = None
    subject: str = "math"
    grade: str = "grade7"
    note: str = ""
    source: str = "local"
    auto_confirm: bool = False


class HermesMistakeIngestRequest(BaseModel):
    message_id: str | None = None
    platform: str = "feishu"
    platform_message_id: str | None = None
    sender_id: str | None = None
    chat_id: str | None = None
    image_path: str | None = None
    image_base64: str | None = None
    image_filename: str | None = None
    subject: str = "math"
    grade: str = "grade7"
    note: str = ""
    auto_confirm: bool = False


class HermesAnalysisIngestRequest(BaseModel):
    message_id: str | None = None
    platform: str = "feishu"
    platform_message_id: str | None = None
    sender_id: str | None = None
    chat_id: str | None = None
    image_path: str | None = None
    image_base64: str | None = None
    image_filename: str | None = None
    subject: str = "math"
    grade: str = "grade7"
    note: str = ""
    analysis: dict[str, Any] = Field(default_factory=dict)
    auto_confirm: bool = False


class ConfirmationRequest(BaseModel):
    action: Literal["confirm", "discard", "modify"] = "confirm"
    confirmed_by: str = "local_parent"
    overrides: dict[str, Any] = Field(default_factory=dict)


class PendingAnalysisModifyRequest(BaseModel):
    confirmed_by: str = "feishu_parent"
    text: str = ""
    overrides: dict[str, Any] = Field(default_factory=dict)
    question_updates: list[dict[str, Any]] = Field(default_factory=list)


class ReportDraftRequest(BaseModel):
    report_type: Literal["daily", "weekly"]
    date: str | None = None


class FeishuCardSendRequest(BaseModel):
    reply_to_message_id: str | None = None
    receive_id: str | None = None
    receive_id_type: Literal["open_id", "user_id", "union_id", "email", "chat_id"] = "chat_id"
