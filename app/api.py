from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query, Request

from app.config import Settings
from app.models.schemas import (
    ConfirmationRequest,
    HermesAnalysisIngestRequest,
    HermesMistakeIngestRequest,
    LocalUploadRequest,
    ReportDraftRequest,
)
from app.services.hermes_service import HermesService
from app.services.sqlite_service import SQLiteService
from app.services.workflow_service import MistakeWorkflowService


router = APIRouter(tags=["mvp"])


def _settings(request: Request) -> Settings:
    return request.app.state.settings


@router.post("/local/simulate-upload")
def simulate_upload(body: LocalUploadRequest, request: Request) -> dict[str, Any]:
    workflow = MistakeWorkflowService(_settings(request))
    return workflow.submit_local(body)


@router.post("/ingest/mistake-image")
def ingest_mistake_image(body: HermesMistakeIngestRequest, request: Request) -> dict[str, Any]:
    workflow = MistakeWorkflowService(_settings(request))
    message_id = (
        body.message_id
        or body.platform_message_id
        or f"{body.platform}:{body.chat_id or 'unknown'}:{body.sender_id or 'unknown'}"
    )
    return workflow.submit_local(
        LocalUploadRequest(
            message_id=message_id,
            local_image_path=body.image_path,
            image_base64=body.image_base64,
            image_filename=body.image_filename,
            subject=body.subject,
            grade=body.grade,
            note=body.note,
            source=f"hermes:{body.platform}",
            auto_confirm=body.auto_confirm,
        )
    )


@router.post("/ingest/mistake-analysis")
def ingest_mistake_analysis(body: HermesAnalysisIngestRequest, request: Request) -> dict[str, Any]:
    workflow = MistakeWorkflowService(_settings(request))
    message_id = (
        body.message_id
        or body.platform_message_id
        or f"{body.platform}:{body.chat_id or 'unknown'}:{body.sender_id or 'unknown'}"
    )
    return workflow.submit_external_analysis(
        message_id=message_id,
        platform=body.platform,
        sender_id=body.sender_id,
        chat_id=body.chat_id,
        image_path=body.image_path,
        image_base64=body.image_base64,
        image_filename=body.image_filename,
        subject=body.subject,
        grade=body.grade,
        note=body.note,
        analysis=body.analysis,
        auto_confirm=body.auto_confirm,
    )


@router.post("/mistakes/{mistake_id}/confirm")
def confirm_mistake(
    mistake_id: str,
    body: ConfirmationRequest,
    request: Request,
) -> dict[str, Any]:
    workflow = MistakeWorkflowService(_settings(request))
    try:
        return workflow.confirm_mistake(mistake_id, body)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/mistakes/{mistake_id}/discard")
def discard_mistake(mistake_id: str, request: Request) -> dict[str, Any]:
    workflow = MistakeWorkflowService(_settings(request))
    try:
        return workflow.discard_mistake(mistake_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/mistakes")
def list_mistakes(
    request: Request,
    status: str | None = None,
    days: int | None = Query(default=None, ge=1),
) -> dict[str, Any]:
    sqlite = SQLiteService(_settings(request).db_path)
    return {"items": sqlite.list_mistakes(status=status, days=days)}


@router.get("/reviews/today")
def today_reviews(request: Request, date: str | None = None) -> dict[str, Any]:
    workflow = MistakeWorkflowService(_settings(request))
    target_date = date or workflow._now()[:10]
    return {"date": target_date, "items": workflow.sqlite.list_reviews(review_date=target_date)}


@router.post("/reports/daily/regenerate")
def regenerate_daily(request: Request, date: str | None = None) -> dict[str, Any]:
    workflow = MistakeWorkflowService(_settings(request))
    return workflow.regenerate_daily(date)


@router.post("/reports/weekly/regenerate")
def regenerate_weekly(request: Request, date: str | None = None) -> dict[str, Any]:
    workflow = MistakeWorkflowService(_settings(request))
    return workflow.regenerate_weekly(date)


@router.get("/reports")
def list_reports(request: Request, report_type: str | None = None) -> dict[str, Any]:
    sqlite = SQLiteService(_settings(request).db_path)
    return {"items": sqlite.list_reports(report_type)}


@router.get("/hermes/stats")
def hermes_stats(request: Request, days: int = Query(default=14, ge=1, le=365)) -> dict[str, Any]:
    sqlite = SQLiteService(_settings(request).db_path)
    return HermesService(sqlite).recent_stats(days=days)


@router.get("/hermes/concepts/{concept_name}/mistakes")
def hermes_concept_mistakes(concept_name: str, request: Request) -> dict[str, Any]:
    sqlite = SQLiteService(_settings(request).db_path)
    return {"concept": concept_name, "items": HermesService(sqlite).concept_mistakes(concept_name)}


@router.post("/hermes/reports/draft")
def hermes_report_draft(body: ReportDraftRequest, request: Request) -> dict[str, Any]:
    workflow = MistakeWorkflowService(_settings(request))
    try:
        return workflow.reports.draft(
            body.report_type,
            workflow.reports.parse_date(body.date),
            workflow._now(),
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/debug/counts")
def debug_counts(request: Request) -> dict[str, int]:
    sqlite = SQLiteService(_settings(request).db_path)
    return sqlite.table_counts()
