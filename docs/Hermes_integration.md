# Hermes Integration

Hermes Agent is the recommended Feishu entry point for this MVP.

## Target Flow

```text
Parent in Feishu
-> Hermes Feishu Gateway
-> Shensi FastAPI controlled API
-> SQLite + Obsidian
```

Hermes should not write the Obsidian vault or SQLite database directly. It should call Shensi APIs so that deduplication, confirmation state, review scheduling, and reports stay consistent.

## Preferred Flow: Vision Analysis First

When Hermes can read the Feishu image with a multimodal model, it should extract
the visible homework content into structured JSON first and then submit that JSON
to Shensi. Shensi will run deterministic verification for supported algebra
items after ingest.

```text
POST http://127.0.0.1:8000/ingest/mistake-analysis
```

Request body:

```json
{
  "message_id": "feishu-message-id-or-hermes-stable-id",
  "platform": "feishu",
  "sender_id": "optional-parent-id",
  "chat_id": "optional-chat-id",
  "image_path": "optional-local-cached-image-path",
  "image_base64": "optional-base64-image-content",
  "image_filename": "mistake.jpg",
  "subject": "math",
  "grade": "grade7",
  "note": "optional parent note",
  "auto_confirm": false,
  "analysis": {
    "provider": "hermes",
    "model": "mimo-v2.5",
    "title": "初一数学｜一元一次方程练习",
    "question_items": [
      {
        "id": 2,
        "question": "3(x - 2) = 12",
        "type": "equation",
        "student_steps": ["3x - 2 = 12", "3x = 14", "x = 14/3"],
        "student_answer": "x = 14/3",
        "correct_answer": "x = 6",
        "is_correct": false,
        "error_reason": "去括号时漏乘 -2。"
      }
    ],
    "student_answer": "第2题 x=14/3；第3题 x=1/3。",
    "correct_answer": "第2题 x=6；第3题 x=5。",
    "concepts": ["一元一次方程", "去括号", "移项"],
    "error_types": ["漏乘", "移项符号错"],
    "root_cause": "第2题去括号时漏乘 -2，第3题移项时符号处理错误。",
    "severity": 4,
    "confidence": 0.91,
    "parent_guidance": "重点复盘去括号分配律和移项变号。"
  }
}
```

Shensi normalizes common Chinese error labels such as `漏乘`, `移项符号错`,
`跳步`, and `计算错误` into internal error type ids before writing SQLite.

Each `question_items` entry should include:

- `id`
- `question`
- `type`
- `student_steps`
- `student_answer`
- `correct_answer`
- `is_correct`
- `error_reason`
- `concept`
- `error_type`

Shensi also accepts common aliases such as `student_solution`,
`student_process`, `solution_steps`, `recognized_steps`, `answer`, `verdict`,
and `mistake_reason`, but the explicit field names above are preferred.

For supported junior-high algebra items, Shensi will add `verification`,
`verified_is_correct`, and sometimes `llm_is_correct` to each question item. If
the deterministic verifier disagrees with the LLM verdict, Shensi keeps the
original verdict in `llm_is_correct` and uses the verified result as
`is_correct`.

## Fallback Flow: Image Only

Use this only when Hermes cannot produce a structured analysis yet. In the
current MVP this route may use the Shensi stub AI provider.

```text
POST http://127.0.0.1:8000/ingest/mistake-image
```

Request body:

```json
{
  "message_id": "feishu-message-id-or-hermes-stable-id",
  "platform": "feishu",
  "platform_message_id": "optional-feishu-message-id",
  "sender_id": "optional-parent-id",
  "chat_id": "optional-chat-id",
  "image_path": "optional-local-cached-image-path",
  "image_base64": "optional-base64-image-content",
  "image_filename": "mistake.jpg",
  "subject": "math",
  "grade": "grade7",
  "note": "optional parent note",
  "auto_confirm": false
}
```

Use either `image_path` or `image_base64`.

- Use `image_path` when Hermes and Shensi run on the same machine and Shensi can read the cached image file.
- Use `image_base64` when Hermes runs in a different container, VM, or host.

Response includes:

- `message_id`
- `mistake_id`
- `status`
- `image_path`
- `analysis`
- `next.confirm`
- `next.discard`

## Confirmation APIs

```text
POST /mistakes/{mistake_id}/confirm
POST /mistakes/{mistake_id}/discard
```

Confirm body:

```json
{
  "action": "confirm",
  "confirmed_by": "feishu_parent",
  "overrides": {}
}
```

## Hermes Instruction Draft

Add this as a project instruction or skill for Hermes:

```text
You are the Feishu entry agent for Shensi Learning Pilot.

When the parent sends a mistake image, read the image with your multimodal model
first and extract the visible text, formulas, student steps, and student answers
into JSON. Do not write SQLite or Obsidian directly.

Create a structured JSON analysis with title, question_items, student_answer,
correct_answer, concepts, error_types, root_cause, severity, confidence, and
parent_guidance. Every question_items entry must include question, student_steps,
student_answer, correct_answer when visible or inferable, is_correct if you have
a preliminary judgment, and error_reason if you see a likely mistake. Shensi will
run deterministic verification after ingest for supported math types.

Then call POST http://127.0.0.1:8000/ingest/mistake-analysis with a stable
message_id, platform="feishu", sender_id, chat_id, subject, grade, note, the
image_path or image_base64, and the analysis JSON.

After Shensi returns status="waiting_confirmation", show the parent the top-level
confirmation_summary first, then the key fields from analysis: title, concepts,
error_types, root_cause, confidence, and ask whether to confirm, discard, or
modify.

If Shensi returns `auto_confirm_blocked=true`, do not retry auto-confirm. Show
the parent the confirmation_summary and wait for explicit confirmation,
discard, or modification.

If the parent confirms, call POST /mistakes/{mistake_id}/confirm.
If the parent discards, call POST /mistakes/{mistake_id}/discard.
If the parent edits fields, call confirm with action="modify" and put allowed edits
in overrides.

Never bypass the Shensi APIs for writes.
```
