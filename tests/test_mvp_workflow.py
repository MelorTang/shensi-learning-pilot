from __future__ import annotations

from pathlib import Path
import base64
import json

from fastapi.testclient import TestClient

from app.config import Settings
from app.feishu.cards import build_pending_mistake_card
from app.main import create_app
from app.models.schemas import LocalUploadRequest
from app.services.math_verification_service import MathVerificationService
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
    concept_notes = list((settings.vault_path / "03-Concepts" / "数学").glob("*.md"))
    curriculum_notes = list((settings.vault_path / "05-Curriculum" / "数学").glob("*.md"))
    assert concept_notes
    assert curriculum_notes
    assert "## Static Knowledge" in concept_notes[0].read_text(encoding="utf-8")
    assert "## Related Mistakes" in concept_notes[0].read_text(encoding="utf-8")
    assert "## Core Idea" in curriculum_notes[0].read_text(encoding="utf-8")

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
    questions = body["analysis"]["question_items"]
    assert body["analysis"]["math_verification"]["verified_count"] == 3
    assert questions[0]["verification"]["method"] == "one_variable_equation"
    assert questions[0]["is_correct"] is True
    assert questions[1]["verification"]["method"] == "one_variable_equation"
    assert questions[1]["is_correct"] is False
    assert questions[1]["correct_answer"] == "x=6"
    assert questions[2]["verification"]["method"] == "one_variable_equation"
    assert questions[2]["is_correct"] is False
    assert questions[2]["correct_answer"] == "x=5"
    assert body["confirmation"]["status"] == "confirmed"
    note_path = Path(body["confirmation"]["note_path"])
    assert note_path.exists()
    note = note_path.read_text(encoding="utf-8")
    assert "### Question 2: 3(x - 2) = 12" in note
    assert "3x - 2 = 12" in note
    assert "missed distributing 3 to -2" in note
    assert "- Result: wrong" in note
    assert "one_variable_equation" in note
    counts = client.get("/debug/counts").json()
    assert counts["mistakes"] == 1
    assert counts["reviews"] == 3
    assert counts["reports"] == 2


def test_hermes_parent_friendly_latest_pending_flow(tmp_path):
    image_path = tmp_path / "pending-homework.jpg"
    image_path.write_bytes(b"fake pending homework image")
    settings = Settings(
        db_path=tmp_path / "shensi.db",
        vault_path=tmp_path / "vault" / "Shensi-Learning-Vault",
    )
    client = TestClient(create_app(settings))

    response = client.post(
        "/ingest/mistake-analysis",
        json={
            "message_id": "hermes-parent-friendly-001",
            "platform": "feishu",
            "sender_id": "parent-user",
            "chat_id": "chat-001",
            "image_path": str(image_path),
            "subject": "math",
            "grade": "grade8",
            "note": "parent friendly pending flow",
            "auto_confirm": False,
            "analysis": {
                "provider": "antigravity",
                "model": "gemini-via-antigravity",
                "title": "初二数学｜一次函数与方程组小测",
                "concepts": ["一次函数求值", "二元一次方程组", "斜率公式"],
                "error_types": ["calculation_error"],
                "root_cause": "第3题斜率公式分子顺序反了。",
                "severity": 3,
                "confidence": 0.95,
                "question_items": [
                    {
                        "id": 1,
                        "question": "已知一次函数 y = -3x + 2，求当 x = -2 时 y 的值。",
                        "student_answer": "y=-3×(-2)+2=6+2=8",
                        "is_correct": True,
                    },
                    {
                        "id": 2,
                        "question": "解方程组：x + y = 10，2x - y = 2。",
                        "student_answer": "x = 4, y = 6",
                        "is_correct": True,
                    },
                    {
                        "id": 3,
                        "question": "已知点 A(1,3)，B(5,11)，求直线 AB 的斜率 k。",
                        "student_answer": "k = -2",
                        "is_correct": False,
                    },
                ],
                "parent_guidance": "复习斜率公式 k=(y2-y1)/(x2-x1)。",
            },
        },
    )

    assert response.status_code == 200
    assert response.json()["status"] == "waiting_confirmation"

    pending = client.get("/hermes/pending/latest").json()
    assert pending["found"] is True
    assert pending["mistake_id"] == response.json()["mistake_id"]
    assert pending["actions"]["confirm_latest"] == "/hermes/pending/latest/confirm"
    assert "确认入库" in pending["reply_text"]
    assert "curl" not in pending["reply_text"].lower()
    assert "学生答案" not in pending["reply_text"]
    assert "题目摘要" not in pending["reply_text"]
    assert "规则验算 3 题" in pending["reply_text"]
    assert len(pending["reply_text"]) < 260
    assert pending["questions"][0]["verification_method"] == "function_substitution"
    assert pending["questions"][0]["is_correct"] is True
    assert pending["questions"][0]["needs_parent_review"] is False
    assert pending["questions"][2]["is_correct"] is False
    card_payload = client.get("/hermes/pending/latest/card").json()
    assert card_payload["found"] is True
    assert card_payload["mistake_id"] == pending["mistake_id"]
    assert card_payload["feishu_message"]["msg_type"] == "interactive"
    assert json.loads(card_payload["feishu_message"]["content"]) == card_payload["card"]
    assert card_payload["reply_text"] == ""
    assert card_payload["final_message"] == ""
    assert card_payload["suppress_followup_text"] is True
    assert "规则验算：3/3" in card_payload["card"]["elements"][0]["text"]["content"]
    card_actions = card_payload["card"]["elements"][-1]["actions"]
    assert [item["text"]["content"] for item in card_actions] == ["确认入库", "丢弃", "重新分析", "修改后入库"]
    assert all(item["value"]["mistake_id"] == pending["mistake_id"] for item in card_actions)

    confirmation = client.post(
        "/hermes/pending/latest/confirm",
        json={"action": "confirm", "confirmed_by": "feishu_parent", "overrides": {}},
    ).json()
    assert confirmation["status"] == "confirmed"
    assert "已确认入库" in confirmation["reply_text"]
    assert client.get("/hermes/pending/latest").json()["found"] is False
    assert client.get("/debug/counts").json()["reviews"] == 3


def test_external_analysis_flags_incomplete_question_extraction(tmp_path):
    image_path = tmp_path / "four-question-homework.jpg"
    image_path.write_bytes(b"fake four question homework image")
    settings = Settings(
        db_path=tmp_path / "shensi.db",
        vault_path=tmp_path / "vault" / "Shensi-Learning-Vault",
    )
    client = TestClient(create_app(settings))

    response = client.post(
        "/ingest/mistake-analysis",
        json={
            "message_id": "incomplete-extraction-001",
            "platform": "feishu",
            "sender_id": "parent-user",
            "chat_id": "chat-001",
            "image_path": str(image_path),
            "subject": "math",
            "grade": "grade8",
            "note": "vision saw four questions but returned three",
            "auto_confirm": True,
            "analysis": {
                "provider": "antigravity",
                "model": "gemini-via-antigravity",
                "title": "Four question worksheet",
                "expected_question_count": 4,
                "concepts": ["linear function", "linear system", "slope"],
                "error_types": ["calculation_error"],
                "root_cause": "One visible question was not extracted.",
                "severity": 3,
                "confidence": 0.88,
                "question_items": [
                    {
                        "id": 1,
                        "question": "Evaluate y=-2x+7 when x=-3",
                        "student_answer": "y=13",
                        "is_correct": True,
                    },
                    {
                        "id": 2,
                        "question": "Solve x+y=11, 2x-y=4",
                        "student_answer": "x=5,y=6",
                        "is_correct": True,
                    },
                    {
                        "id": 3,
                        "question": "Find slope A(-2,5), B(4,-1)",
                        "student_answer": "k=1",
                        "is_correct": False,
                    },
                ],
                "parent_guidance": "Ask for a clearer photo before confirming.",
            },
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "waiting_confirmation"
    assert body["auto_confirm_blocked"] is True
    summary = body["confirmation_summary"]
    assert summary["expected_question_count"] == 4
    assert summary["extracted_question_count"] == 3
    assert summary["missing_question_count"] == 1
    assert summary["missing_question_numbers"] == [4]
    assert summary["extraction_complete"] is False
    assert summary["needs_parent_review_count"] >= 1
    assert "missing from extraction" in summary["message"]

    pending = client.get("/hermes/pending/latest").json()
    assert pending["found"] is True
    assert pending["confirmation_summary"]["extraction_complete"] is False
    assert "只抽取到 3 题" in pending["reply_text"]


def test_hermes_pending_card_send_endpoint_requires_destination(tmp_path):
    settings = Settings(
        db_path=tmp_path / "shensi.db",
        vault_path=tmp_path / "vault" / "Shensi-Learning-Vault",
    )
    client = TestClient(create_app(settings))
    client.post(
        "/local/simulate-upload",
        json={
            "message_id": "card-send-missing-destination",
            "subject": "math",
            "grade": "grade8",
            "note": "card send destination validation",
            "auto_confirm": False,
        },
    )

    response = client.post("/hermes/pending/latest/card/send", json={})

    assert response.status_code == 400
    assert "reply_to_message_id or receive_id" in response.json()["detail"]


def test_hermes_pending_card_send_endpoint_replies_with_interactive_card(tmp_path, monkeypatch):
    settings = Settings(
        db_path=tmp_path / "shensi.db",
        vault_path=tmp_path / "vault" / "Shensi-Learning-Vault",
        feishu_app_id="cli_test_app",
        feishu_app_secret="cli_test_secret",
    )
    client = TestClient(create_app(settings))
    ingest = client.post(
        "/local/simulate-upload",
        json={
            "message_id": "card-send-reply",
            "subject": "math",
            "grade": "grade8",
            "note": "card send reply",
            "auto_confirm": False,
        },
    ).json()
    sent: dict[str, object] = {}

    def fake_reply_interactive_card(self, *, message_id, card):
        sent["message_id"] = message_id
        sent["card"] = card
        return {"code": 0, "data": {"message_id": "om_card_reply"}}

    monkeypatch.setattr("app.api.FeishuClient.reply_interactive_card", fake_reply_interactive_card)

    response = client.post(
        "/hermes/pending/latest/card/send",
        json={"reply_to_message_id": "om_parent_message"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["sent"] is True
    assert body["mistake_id"] == ingest["mistake_id"]
    assert body["delivery"]["mode"] == "reply"
    assert body["reply_text"] == ""
    assert body["final_message"] == ""
    assert body["suppress_followup_text"] is True
    assert sent["message_id"] == "om_parent_message"
    assert sent["card"]["elements"][-1]["actions"][0]["value"]["mistake_id"] == ingest["mistake_id"]


def test_hermes_pending_card_send_endpoint_sends_to_chat(tmp_path, monkeypatch):
    settings = Settings(
        db_path=tmp_path / "shensi.db",
        vault_path=tmp_path / "vault" / "Shensi-Learning-Vault",
        feishu_app_id="cli_test_app",
        feishu_app_secret="cli_test_secret",
    )
    client = TestClient(create_app(settings))
    client.post(
        "/local/simulate-upload",
        json={
            "message_id": "card-send-chat",
            "subject": "math",
            "grade": "grade8",
            "note": "card send chat",
            "auto_confirm": False,
        },
    )
    sent: dict[str, object] = {}

    def fake_send_interactive_card(self, *, receive_id, receive_id_type, card):
        sent["receive_id"] = receive_id
        sent["receive_id_type"] = receive_id_type
        sent["card"] = card
        return {"code": 0, "data": {"message_id": "om_card_send"}}

    monkeypatch.setattr("app.api.FeishuClient.send_interactive_card", fake_send_interactive_card)

    response = client.post(
        "/hermes/pending/latest/card/send",
        json={"receive_id": "oc_chat_001", "receive_id_type": "chat_id"},
    )

    assert response.status_code == 200
    assert response.json()["delivery"]["mode"] == "send"
    assert sent["receive_id"] == "oc_chat_001"
    assert sent["receive_id_type"] == "chat_id"


def test_feishu_pending_mistake_card_contract():
    card = build_pending_mistake_card(
        {
            "mistake_id": "mistake-001",
            "title": "初二数学｜一次函数与方程组小测",
            "concepts": ["一次函数"],
            "root_cause": "第3题斜率公式分子顺序反了。",
            "parent_guidance": "复习斜率公式。",
            "confirmation_summary": {
                "total_questions": 3,
                "verified_questions": 2,
                "extraction_complete": True,
            },
            "verification_summary": {
                "verified_question_count": 2,
                "unsupported_question_ids": [3],
            },
            "questions": [
                {
                    "id": 1,
                    "student_answer": "y=8",
                    "correct_answer": "y=8",
                    "concept": "代入求值",
                    "is_correct": True,
                    "verification_status": "verified",
                },
                {
                    "id": 2,
                    "student_answer": "x=4,y=6",
                    "correct_answer": "x=4,y=6",
                    "concept": "二元一次方程组",
                    "is_correct": True,
                    "verification_status": "verified",
                },
                {
                    "id": 3,
                    "student_answer": "k=-2",
                    "correct_answer": "k=2",
                    "concept": "一次函数斜率",
                    "error_reason": "斜率公式分子顺序反了",
                    "is_correct": False,
                    "verification_status": "unsupported",
                    "needs_parent_review": True,
                },
            ],
        }
    )

    assert card["header"]["title"]["content"] == "初二数学｜一次函数与方程组小测"
    card_text = "\n".join(
        element.get("text", {}).get("content", "")
        for element in card["elements"]
        if element.get("tag") == "div"
    )
    assert "k=-2" not in card_text
    assert "k=2" not in card_text
    assert "规则验算：2/3" in card_text
    assert "仅模型判断：第3题" in card_text
    assert "需确认：第3题" in card_text
    assert "逐题判断" in card_text
    assert "初判错，待确认 **第3题**" in card_text
    assert "判断依据：斜率公式分子顺序反了" in card_text
    assert "**涉及知识点**：一次函数" in card_text
    actions = card["elements"][-1]["actions"]
    assert [item["text"]["content"] for item in actions] == ["确认入库", "丢弃", "重新分析", "修改后入库"]
    assert [item["value"]["action"] for item in actions] == [
        "shensi_confirm",
        "shensi_discard",
        "shensi_reanalyze",
        "shensi_modify_confirm",
    ]
    assert all(item["value"]["mistake_id"] == "mistake-001" for item in actions)


def test_feishu_card_callback_confirms_pending_mistake(tmp_path, monkeypatch):
    settings = Settings(
        db_path=tmp_path / "shensi.db",
        vault_path=tmp_path / "vault" / "Shensi-Learning-Vault",
        feishu_app_id="cli_test_app",
        feishu_app_secret="cli_test_secret",
    )
    client = TestClient(create_app(settings))
    ingest = client.post(
        "/local/simulate-upload",
        json={
            "message_id": "card-confirm-001",
            "subject": "math",
            "grade": "grade8",
            "note": "card callback confirm",
            "auto_confirm": False,
        },
    ).json()
    replies: dict[str, str] = {}

    def fake_reply_text(self, *, message_id, text):
        replies["message_id"] = message_id
        replies["text"] = text
        return {"code": 0, "data": {"message_id": "om_confirm_reply"}}

    monkeypatch.setattr("app.feishu.webhook.FeishuClient.reply_text", fake_reply_text)

    response = client.post(
        "/feishu/card-callback",
        json={
            "event": {
                "context": {
                    "open_message_id": "om_result_card",
                }
            },
            "action": {
                "value": {
                    "action": "shensi_confirm",
                    "mistake_id": ingest["mistake_id"],
                }
            }
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["toast"]["type"] == "success"
    assert body["result"]["status"] == "confirmed"
    assert body["delivery"]["mode"] == "reply"
    assert replies["message_id"] == "om_result_card"
    assert "已确认入库" in replies["text"]
    assert client.get("/debug/counts").json()["reviews"] == 3


def test_feishu_card_callback_accepts_json_string_action_value(tmp_path):
    settings = Settings(
        db_path=tmp_path / "shensi.db",
        vault_path=tmp_path / "vault" / "Shensi-Learning-Vault",
    )
    client = TestClient(create_app(settings))
    ingest = client.post(
        "/local/simulate-upload",
        json={
            "message_id": "card-confirm-json-string-001",
            "subject": "math",
            "grade": "grade8",
            "note": "card callback confirm json string",
            "auto_confirm": False,
        },
    ).json()

    response = client.post(
        "/feishu/card-callback",
        json={
            "event": {
                "context": {"open_message_id": "om_result_card"},
                "action": {
                    "value": json.dumps(
                        {
                            "action": "shensi_confirm",
                            "mistake_id": ingest["mistake_id"],
                        }
                    )
                },
            }
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["result"]["status"] == "confirmed"
    assert client.get("/debug/counts").json()["reviews"] == 3


def test_feishu_card_callback_discards_pending_mistake(tmp_path):
    settings = Settings(
        db_path=tmp_path / "shensi.db",
        vault_path=tmp_path / "vault" / "Shensi-Learning-Vault",
    )
    client = TestClient(create_app(settings))
    ingest = client.post(
        "/local/simulate-upload",
        json={
            "message_id": "card-discard-001",
            "subject": "math",
            "grade": "grade8",
            "note": "card callback discard",
            "auto_confirm": False,
        },
    ).json()

    response = client.post(
        "/feishu/card-callback",
        json={
            "event": {
                "action": {
                    "value": {
                        "action": "shensi_discard",
                        "mistake_id": ingest["mistake_id"],
                    }
                }
            }
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["result"]["status"] == "discarded"
    assert client.get("/mistakes", params={"status": "discarded"}).json()["items"][0]["id"] == ingest["mistake_id"]
    assert client.get("/debug/counts").json()["reviews"] == 0


def test_feishu_card_callback_accepts_nested_action_payload(tmp_path):
    settings = Settings(
        db_path=tmp_path / "shensi.db",
        vault_path=tmp_path / "vault" / "Shensi-Learning-Vault",
    )
    client = TestClient(create_app(settings))
    ingest = client.post(
        "/local/simulate-upload",
        json={
            "message_id": "card-discard-nested-001",
            "subject": "math",
            "grade": "grade8",
            "note": "card callback nested discard",
            "auto_confirm": False,
        },
    ).json()

    response = client.post(
        "/feishu/card-callback",
        json={
            "event": {
                "action": {
                    "tag": "button",
                    "value": {
                        "payload": {
                            "action": "shensi_discard",
                            "mistakeId": ingest["mistake_id"],
                        }
                    },
                }
            }
        },
    )

    assert response.status_code == 200
    assert response.json()["result"]["status"] == "discarded"


def test_math_verifier_checks_point_on_line_conclusion():
    verifier = MathVerificationService()

    result = verifier.verify_item(
        {
            "question": (
                "Line MN passes through M(3,4) and N(0,-2). "
                "Judge whether point Q(6,1) is on line MN."
            ),
            "student_answer": "Q is not on line MN.",
            "is_correct": False,
        }
    )

    assert result["status"] == "verified"
    assert result["method"] == "point_on_line"
    assert result["is_correct"] is True
    assert result["correct_answer"] == "Q is not on line MN"
    assert result["checks"][0]["expected_on_line"] is False
    assert result["checks"][0]["student_claim_on_line"] is False


def test_external_analysis_math_verifier_overrides_bad_llm_verdict(tmp_path):
    image_path = tmp_path / "grade8-homework.jpg"
    image_path.write_bytes(b"fake grade8 homework image")
    settings = Settings(
        db_path=tmp_path / "shensi.db",
        vault_path=tmp_path / "vault" / "Shensi-Learning-Vault",
    )
    client = TestClient(create_app(settings))

    response = client.post(
        "/ingest/mistake-analysis",
        json={
            "message_id": "math-verifier-001",
            "platform": "feishu",
            "sender_id": "parent-user",
            "chat_id": "chat-001",
            "image_path": str(image_path),
            "subject": "math",
            "grade": "grade8",
            "note": "LLM claimed a wrong system answer was correct",
            "auto_confirm": True,
            "analysis": {
                "provider": "hermes",
                "model": "mimo-v2.5",
                "title": "Grade 8 algebra check",
                "concepts": [
                    "linear function",
                    "linear system",
                    "slope",
                    "ratio equation",
                    "like terms",
                    "rectangle perimeter",
                ],
                "error_types": ["calculation_error"],
                "root_cause": "The model should be checked by deterministic math verification.",
                "severity": 3,
                "confidence": 0.95,
                "question_items": [
                    {
                        "question": "已知一次函数 y = -3x + 2，求当 x = -2 时 y 的值。",
                        "student_answer": "y = 8",
                        "student_steps": ["y = -3 × (-2) + 2", "y = 6 + 2", "y = 8"],
                        "is_correct": True,
                    },
                    {
                        "question": "Solve the system: x+y=10, 2x-y=2",
                        "student_answer": "x=4, y=5",
                        "student_steps": ["x+y=10", "2x-y=2", "x=4,y=5"],
                        "is_correct": True,
                    },
                    {
                        "question": "Find the slope of A(1,3), B(5,11)",
                        "student_answer": "k=-2",
                        "is_correct": False,
                    },
                    {
                        "question": "Solve the proportion x/3 = 4/6",
                        "student_answer": "x=3",
                        "is_correct": True,
                    },
                    {
                        "question": "Simplify: 4x + 3 - x + 5",
                        "student_answer": "3x+7",
                        "is_correct": True,
                    },
                    {
                        "question": "A rectangle has length 8 and width 5. Find perimeter.",
                        "student_answer": "P=35",
                        "is_correct": True,
                    },
                    {
                        "question": "Prove that two base angles of an isosceles triangle are equal.",
                        "student_answer": "proof omitted",
                        "is_correct": True,
                    },
                ],
                "student_answer": "Q1 y=8; Q2 x=4,y=5; Q3 k=-2",
                "correct_answer": "",
                "parent_guidance": "Ask the child to substitute every answer back into the original equation.",
            },
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "waiting_confirmation"
    assert "confirmation" not in body
    assert body["auto_confirm_blocked"] is True
    assert body["auto_confirm_blocked_reason"] == "parent review required"
    questions = body["analysis"]["question_items"]
    assert questions[0]["is_correct"] is True
    assert questions[0]["verification"]["method"] == "function_substitution"
    assert questions[1]["llm_is_correct"] is True
    assert questions[1]["is_correct"] is False
    assert questions[1]["verified_is_correct"] is False
    assert questions[1]["correct_answer"] == "x=4, y=6"
    assert questions[1]["verification"]["conflict_with_llm"] is True
    assert questions[1]["needs_parent_review"] is True
    assert questions[2]["is_correct"] is False
    assert questions[2]["needs_parent_review"] is False
    assert questions[2]["correct_answer"] == "k=2"
    assert questions[3]["llm_is_correct"] is True
    assert questions[3]["is_correct"] is False
    assert questions[3]["correct_answer"] == "x=2"
    assert questions[3]["verification"]["method"] == "ratio_equation_cross_multiply"
    assert questions[4]["llm_is_correct"] is True
    assert questions[4]["is_correct"] is False
    assert questions[4]["correct_answer"] == "3x+8"
    assert questions[4]["verification"]["method"] == "linear_simplification"
    assert questions[5]["llm_is_correct"] is True
    assert questions[5]["is_correct"] is False
    assert questions[5]["correct_answer"] == "26"
    assert questions[5]["verification"]["method"] == "rectangle_perimeter"
    assert questions[6]["is_correct"] is True
    assert questions[6]["verification"]["status"] == "unsupported"
    assert questions[6]["needs_parent_review"] is True
    assert questions[6]["review_reason"] == "verification unsupported"
    assert body["analysis"]["math_verification"]["verified_count"] == 6
    assert body["analysis"]["math_verification"]["unsupported_count"] == 1
    assert body["analysis"]["math_verification"]["conflict_count"] == 4
    assert body["analysis"]["math_verification"]["needs_parent_review_count"] == 5
    assert body["confirmation_summary"] == body["analysis"]["confirmation_summary"]
    assert body["confirmation_summary"]["total_questions"] == 7
    assert body["confirmation_summary"]["verified_questions"] == 6
    assert body["confirmation_summary"]["wrong_questions"] == [2, 3, 4, 5, 6]
    assert body["confirmation_summary"]["needs_parent_review_questions"] == [2, 4, 5, 6, 7]
    assert body["confirmation_summary"]["needs_parent_review_count"] == 5
    assert "need parent review" in body["confirmation_summary"]["message"]
    pending = client.get("/hermes/pending/latest").json()
    assert pending["verification_summary"]["unsupported_question_ids"] == [7]
    assert "只做视觉模型判断" in pending["reply_text"]
    pending_card = client.get("/hermes/pending/latest/card").json()["card"]
    card_summary = pending_card["elements"][0]["text"]["content"]
    assert "规则验算：6/7" in card_summary
    assert "仅模型判断：第7题" in card_summary

    confirmation = client.post(
        f"/mistakes/{body['mistake_id']}/confirm",
        json={"action": "confirm", "confirmed_by": "test_parent", "overrides": {}},
    ).json()
    assert confirmation["status"] == "confirmed"

    note = Path(confirmation["note_path"]).read_text(encoding="utf-8")
    assert "linear_system_substitution" in note
    assert "ratio_equation_cross_multiply" in note
    assert "linear_simplification" in note
    assert "rectangle_perimeter" in note
    assert "overrode LLM verdict" in note
    assert "x=4, y=6" in note
    assert "3x+8" in note
    assert "26" in note
    assert "Parent review: required" in note
    assert "Parent review: not required" in note


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
