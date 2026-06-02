from __future__ import annotations

from pathlib import Path
import base64

from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app
from app.models.schemas import LocalUploadRequest
from app.services.sqlite_service import SQLiteService
from app.services.workflow_service import MistakeWorkflowService


def test_local_workflow_full_cycle(tmp_path):
    image_path = tmp_path / "sample.svg"
    image_path.write_text("<svg xmlns='http://www.w3.org/2000/svg'></svg>", encoding="utf-8")
    settings = Settings(
        db_path=tmp_path / "shensi.db",
        vault_path=tmp_path / "vault" / "Shensi-Learning-Vault",
    )
    workflow = MistakeWorkflowService(settings)

    result = workflow.submit_local(
        LocalUploadRequest(
            message_id="test-message-001",
            local_image_path=str(image_path),
            subject="math",
            grade="grade7",
            note="pytest full cycle",
            auto_confirm=True,
        )
    )

    assert result["status"] == "waiting_confirmation"
    assert result["confirmation"]["status"] == "confirmed"
    sqlite = SQLiteService(settings.db_path)
    counts = sqlite.table_counts()
    assert counts["mistakes"] == 1
    assert counts["concepts"] >= 1
    assert counts["reviews"] == 3
    assert counts["reports"] == 2
    assert Path(result["confirmation"]["note_path"]).exists()
    assert Path(result["confirmation"]["daily_report"]["note_path"]).exists()
    assert Path(result["confirmation"]["weekly_report"]["note_path"]).exists()

    duplicate = workflow.submit_local(
        LocalUploadRequest(
            message_id="test-message-001",
            local_image_path=str(image_path),
            subject="math",
            grade="grade7",
            note="pytest full cycle",
            auto_confirm=True,
        )
    )
    assert duplicate["duplicate"] is True
    assert sqlite.table_counts()["mistakes"] == 1
    assert sqlite.table_counts()["reviews"] == 3


def test_api_simulate_upload_and_hermes_stats(tmp_path):
    settings = Settings(
        db_path=tmp_path / "shensi.db",
        vault_path=tmp_path / "vault" / "Shensi-Learning-Vault",
    )
    client = TestClient(create_app(settings))

    response = client.post(
        "/local/simulate-upload",
        json={
            "message_id": "api-message-001",
            "subject": "math",
            "grade": "grade7",
            "note": "api full cycle",
            "auto_confirm": True,
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["confirmation"]["status"] == "confirmed"
    stats = client.get("/hermes/stats").json()
    assert stats["mistakes_by_subject"][0]["subject"] == "math"
    counts = client.get("/debug/counts").json()
    assert counts["mistakes"] == 1
    assert counts["reports"] == 2
    draft = client.post("/hermes/reports/draft", json={"report_type": "daily"}).json()
    assert draft["draft"] is True
    assert client.get("/debug/counts").json()["reports"] == 2


def test_hermes_ingest_accepts_base64_image(tmp_path):
    settings = Settings(
        db_path=tmp_path / "shensi.db",
        vault_path=tmp_path / "vault" / "Shensi-Learning-Vault",
    )
    client = TestClient(create_app(settings))
    image_data = base64.b64encode(b"fake image bytes").decode("ascii")

    response = client.post(
        "/ingest/mistake-image",
        json={
            "message_id": "hermes-feishu-001",
            "platform": "feishu",
            "sender_id": "parent-user",
            "chat_id": "chat-001",
            "image_base64": image_data,
            "image_filename": "mistake.png",
            "subject": "math",
            "grade": "grade7",
            "note": "from Hermes gateway",
            "auto_confirm": True,
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["image_download"]["mode"] == "base64_upload"
    assert body["confirmation"]["status"] == "confirmed"
    assert Path(body["image_path"]).suffix == ".png"
    assert client.get("/debug/counts").json()["reviews"] == 3


def test_hermes_ingest_accepts_external_analysis(tmp_path):
    image_path = tmp_path / "real-homework.jpg"
    image_path.write_bytes(b"fake homework image")
    settings = Settings(
        db_path=tmp_path / "shensi.db",
        vault_path=tmp_path / "vault" / "Shensi-Learning-Vault",
    )
    client = TestClient(create_app(settings))

    response = client.post(
        "/ingest/mistake-analysis",
        json={
            "message_id": "hermes-analysis-001",
            "platform": "feishu",
            "sender_id": "parent-user",
            "chat_id": "chat-001",
            "image_path": str(image_path),
            "subject": "math",
            "grade": "grade7",
            "note": "MiMo analysis from Feishu image",
            "auto_confirm": True,
            "analysis": {
                "provider": "hermes",
                "model": "mimo-v2.5",
                "title": "初一数学｜一元一次方程练习",
                "concepts": ["一元一次方程", "去括号", "移项"],
                "error_types": ["漏乘", "移项符号错"],
                "root_cause": "第2题去括号时漏乘 -2，第3题移项时符号处理错误。",
                "severity": 4,
                "confidence": 0.91,
                "question_items": [
                    {
                        "question": "2x + 5 = 17",
                        "student_steps": ["2x = 12", "x = 6"],
                        "verdict": "correct",
                    },
                    {
                        "question": "3(x - 2) = 12",
                        "student_solution": "3x - 2 = 12\n3x = 14\nx = 14/3",
                        "student_answer": "x = 14/3",
                        "correct_answer": "x = 6",
                        "verdict": "wrong",
                        "error_reason": "missed distributing 3 to -2",
                    },
                    {
                        "question": "5x - 7 = 2x + 8",
                        "solution_steps": ["5x - 2x = 8 - 7", "3x = 1", "x = 1/3"],
                        "student_answer": "x = 1/3",
                        "correct_answer": "x = 5",
                        "is_correct": False,
                        "error_reason": "moved -7 without changing the sign",
                    },
                ],
                "student_answer": "第1题正确；第2题 x=14/3；第3题 x=1/3。",
                "correct_answer": "第1题 x=6；第2题 x=6；第3题 x=5。",
                "parent_guidance": "重点复盘去括号分配律和移项变号。",
            },
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["analysis"]["model"] == "mimo-v2.5"
    assert body["analysis"]["error_types"] == ["missed_condition", "calculation_error"]
    assert body["confirmation"]["status"] == "confirmed"
    note_path = Path(body["confirmation"]["note_path"])
    assert note_path.exists()
    note = note_path.read_text(encoding="utf-8")
    assert "### Question 2: 3(x - 2) = 12" in note
    assert "3x - 2 = 12" in note
    assert "missed distributing 3 to -2" in note
    assert "- Result: wrong" in note
    counts = client.get("/debug/counts").json()
    assert counts["mistakes"] == 1
    assert counts["reviews"] == 3
    assert counts["reports"] == 2


def test_feishu_webhook_image_payload_without_credentials_uses_stub(tmp_path):
    settings = Settings(
        db_path=tmp_path / "shensi.db",
        vault_path=tmp_path / "vault" / "Shensi-Learning-Vault",
    )
    client = TestClient(create_app(settings))

    response = client.post(
        "/feishu/webhook",
        json={
            "schema": "2.0",
            "header": {"event_type": "im.message.receive_v1"},
            "event": {
                "sender": {"sender_id": {"user_id": "parent-user"}},
                "message": {
                    "message_id": "feishu-image-001",
                    "chat_id": "chat-001",
                    "message_type": "image",
                    "content": '{"image_key":"img_test_key","subject":"math","grade":"grade7"}',
                },
            },
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "waiting_confirmation"
    assert body["image_download"]["mode"] == "local_stub"
    assert body["analysis"]["message_id"] == "feishu-image-001"
