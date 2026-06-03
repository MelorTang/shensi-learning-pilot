from __future__ import annotations

from pathlib import Path
import base64

from fastapi.testclient import TestClient

from app.config import Settings
from app.feishu.cards import build_pending_mistake_card
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
    assert pending["questions"][0]["verification_method"] == "function_substitution"
    assert pending["questions"][0]["is_correct"] is True
    assert pending["questions"][0]["needs_parent_review"] is False
    assert pending["questions"][2]["is_correct"] is False
    card_payload = client.get("/hermes/pending/latest/card").json()
    assert card_payload["found"] is True
    assert card_payload["mistake_id"] == pending["mistake_id"]
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


def test_feishu_pending_mistake_card_contract():
    card = build_pending_mistake_card(
        {
            "mistake_id": "mistake-001",
            "title": "初二数学｜一次函数与方程组小测",
            "root_cause": "第3题斜率公式分子顺序反了。",
            "parent_guidance": "复习斜率公式。",
            "questions": [
                {"id": 1, "student_answer": "y=8", "correct_answer": "y=8", "is_correct": True},
                {"id": 2, "student_answer": "x=4,y=6", "correct_answer": "x=4,y=6", "is_correct": True},
                {"id": 3, "student_answer": "k=-2", "correct_answer": "k=2", "is_correct": False},
            ],
        }
    )

    assert card["header"]["title"]["content"] == "初二数学｜一次函数与方程组小测"
    actions = card["elements"][-1]["actions"]
    assert [item["text"]["content"] for item in actions] == ["确认入库", "丢弃", "重新分析", "修改后入库"]
    assert [item["value"]["action"] for item in actions] == [
        "shensi_confirm",
        "shensi_discard",
        "shensi_reanalyze",
        "shensi_modify_confirm",
    ]
    assert all(item["value"]["mistake_id"] == "mistake-001" for item in actions)


def test_feishu_card_callback_confirms_pending_mistake(tmp_path):
    settings = Settings(
        db_path=tmp_path / "shensi.db",
        vault_path=tmp_path / "vault" / "Shensi-Learning-Vault",
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

    response = client.post(
        "/feishu/card-callback",
        json={
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
