# Hermes Integration

Hermes Agent is the recommended Feishu entry point for this MVP.

## Target Flow

```text
Parent in Feishu
-> Hermes Feishu Gateway
-> controlled wrapper script, e.g. shensi-antigravity-submit
-> Antigravity/Gemini vision JSON
-> Shensi FastAPI deterministic verification
-> parent confirmation
-> SQLite + Obsidian
```

Hermes should stay a thin Feishu gateway and command router. It does not need a
strong LLM for the production path if it only calls fixed wrapper scripts and
posts their result back to Feishu. The heavier image reading and first-pass
analysis can be delegated to Antigravity/Gemini through a controlled wrapper
such as `/home/admin/bin/shensi-antigravity-submit`.

Hermes should not write the Obsidian vault or SQLite database directly. It
should call Shensi APIs so that deduplication, confirmation state, review
scheduling, and reports stay consistent.

## Preferred Flow: Vision Analysis First

When Hermes receives a Feishu image, the preferred cloud flow is to pass the
cached image path to `shensi-antigravity-submit`. The wrapper should call
Antigravity/Gemini to extract the visible homework content into structured JSON,
then submit that JSON to Shensi. Shensi will run deterministic verification for
supported algebra items after ingest.

For menu-driven analysis, Hermes must use the most recent image from the same
Feishu chat/user that triggered the menu action. Do not reuse a stale global
`~/.hermes/image_cache` entry. The Shensi `message_id` should be unique for that
image, for example the Feishu image message id or a stable id built from chat id,
sender id, image filename, and image mtime. Reusing an old message id correctly
returns the old Shensi result because Shensi writes are idempotent.

The helper wrapper accepts an explicit image path as argument 5:

```bash
/home/admin/bin/shensi-feishu-analysis-latest <chat_id> <sender_id> <subject> <grade> <image_path>
```

Prefer this explicit-path mode whenever Hermes can recover the exact cached
image file for the current chat/session. The global cache fallback should remain
only as a compatibility fallback.

Hermes should also index images as soon as they are received:

```bash
/home/admin/bin/shensi-index-image <chat_id> <sender_id> <image_path>
```

This writes:

```text
~/.hermes/shensi_image_index/<safe_chat_id>/<safe_sender_id>.path
```

When argument 5 is omitted, `shensi-feishu-analysis-latest` reads this index
before falling back to the global newest file in `~/.hermes/image_cache`.

Timing logs:

- image indexing: `~/.hermes/logs/shensi-image-index.log`
- analysis phases: `~/.hermes/logs/shensi-feishu-analysis-latest.log`

Important timing fields:

- `phase=resolve_image`
- `phase=submit_start`
- `phase=submit_done elapsed_ms=...`
- `phase=card_send_start`
- `phase=card_send_done elapsed_ms=...`
- `phase=done total_elapsed_ms=...`

## Feishu UX Plan

Use bot menus for starting Shensi workflows, and use interactive cards for
deciding what to do with one specific analysis result.

Recommended bot menu items:

- 慎思分析: send text `慎思：分析刚才图片`
- 今日日报: send text `慎思：查看今日日报`
- 复习任务: send text `慎思：查看复习任务`
- 帮助: send text `慎思：帮助`

Do not put confirmation actions in the menu. Confirmation is tied to a specific
analysis result, so it belongs on the result card.

Recommended result card buttons:

- 确认入库: `value.action = shensi_confirm`
- 丢弃: `value.action = shensi_discard`
- 重新分析: `value.action = shensi_reanalyze`
- 修改后入库: `value.action = shensi_modify_confirm`

Each card button should include `value.mistake_id`. The future Feishu card
callback handler can route these actions to Shensi confirm, discard, reanalyze,
or modify-confirm APIs without asking the parent to type IDs.

Shensi exposes the latest pending card JSON for Hermes:

```text
GET /hermes/pending/latest/card
```

Hermes should call this after `shensi-antigravity-submit` succeeds, then send
the returned `card` as a Feishu interactive card. This is the missing step if
Hermes currently replies with plain text only.

The response also includes a Feishu-ready envelope:

```json
{
  "feishu_message": {
    "msg_type": "interactive",
    "content": "<JSON string of the card>"
  }
}
```

When Hermes has a Feishu send/reply tool, pass `feishu_message.msg_type` and
`feishu_message.content` to that tool. Do not paste the card JSON as plain text.

If Hermes' `send_message` tool converts the interactive payload into visible
JSON text, bypass that tool and ask Shensi to send the card through the Feishu
OpenAPI:

```text
POST /hermes/pending/latest/card/send
```

Reply mode:

```json
{"reply_to_message_id":"<feishu message id>"}
```

Chat send mode:

```json
{"receive_id":"<chat id>","receive_id_type":"chat_id"}
```

Shensi card action callback endpoint:

```text
POST /feishu/card-callback
```

Implemented button actions:

- `shensi_confirm`: confirm the given `mistake_id`
- `shensi_discard`: discard the given `mistake_id`

Draft button actions that return guidance for now:

- `shensi_reanalyze`
- `shensi_modify_confirm`

There are two callback modes:

- HTTP callback mode: configure the Feishu card callback URL to:

```text
https://<your-domain>/feishu/card-callback
```

- Long-connection mode: no domain is required. Hermes receives
  `card.action.trigger` through the Feishu long connection and forwards the
  payload to local Shensi:

```text
POST http://127.0.0.1:8000/feishu/card-callback
```

If Hermes does not forward card actions, Shensi can run a small card-action
forwarder without handling normal Feishu messages:

```text
python scripts/run_feishu_ws.py --card-actions-only
```

Feishu Developer Console must subscribe the app to `card.action.trigger`.

Cloud deployment note:

- `shensi-feishu-card.service` should load both
  `/home/admin/apps/shensi-learning-pilot/.env` and `/home/admin/.hermes/.env`.
- `shensi.service` must load the same two environment files when Shensi is the
  process that sends Feishu interactive cards.
- Otherwise the workflow can reach `waiting_confirmation`, but
  `/hermes/pending/latest/card/send` may fail with `HTTP 502` because the
  running FastAPI process does not have Feishu credentials in its environment.

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

Before extracting details, count the visible numbered questions. Include
`expected_question_count` in the analysis JSON. Return every visible question in
`question_items`; if a question is partly unreadable, still include a placeholder
item with the visible text, empty unknown fields, and a low confidence note
instead of silently omitting it.

Then call POST http://127.0.0.1:8000/ingest/mistake-analysis with a stable
message_id, platform="feishu", sender_id, chat_id, subject, grade, note, the
image_path or image_base64, and the analysis JSON.

When the parent clicks the bot menu item, use the latest image in this same chat
as the `image_path`. If there is no recent image in the chat, ask the parent to
send a picture first. Never analyze an older cached image just because it is the
newest file on disk.

Only call the Shensi workflow when the parent clearly asks to process learning
material. Good trigger phrases include "提交这张错题", "分析刚才的图片",
"慎思：分析刚才图片", "慎思：查看今日日报", "慎思：查看复习任务", and "慎思：帮助".
For normal chat, study encouragement, or general questions, answer normally and
do not call Shensi APIs or wrapper scripts.

After Shensi returns status="waiting_confirmation", call
GET /hermes/pending/latest only as a fallback text source. If a Feishu
interactive card can be sent, do not show this text separately.

Do not paste raw JSON, curl commands, local file paths, stack traces, API
details, tool names, model names, execution logs, approval receipts, or
intermediate analysis output unless the parent explicitly asks for debugging.

If Hermes can send Feishu interactive cards, prefer:

```text
GET /hermes/pending/latest/card
```

Then send the returned `card` object as `msg_type=interactive`. If card sending
fails, fall back to the plain `reply_text`.

If the response includes `feishu_message`, prefer sending that exact envelope:
`msg_type=interactive`, `content=feishu_message.content`.

After a card is sent successfully, do not send any additional final answer.
If the API response includes `suppress_followup_text=true` or
`final_message=""`, the Feishu-visible final response must be empty. The card is
the only parent-facing result.

If Hermes cannot send interactive cards and pastes JSON as plain text, call
`POST /hermes/pending/latest/card/send` with the current Feishu message id or
chat id so Shensi sends the card directly.

If Shensi returns `auto_confirm_blocked=true`, do not retry auto-confirm. Show
the parent a short summary and wait for explicit confirmation, discard, or
modification.

If the parent clicks a result card button, route by `value.action`. If the
parent types a fallback command like "确认入库" or "丢弃", call
POST /hermes/pending/latest/confirm or POST /hermes/pending/latest/discard.
When Shensi receives `card.action.trigger`, it returns a toast and also tries to
send a normal Feishu text reply back to the card message or chat, so the action
has a visible conversation record.
If the parent edits fields, call confirm with action="modify" and put allowed edits
in overrides. If there are multiple pending items and the parent is ambiguous,
ask which one they mean before confirming or discarding.

Parent-facing output style:

- Keep it short: title, which questions are wrong, one root cause, one parent
  guidance sentence, then ask the parent to use the card buttons.
- Use natural Chinese.
- Hide implementation details by default.
- Do not mention Hermes, Antigravity, Gemini, SQLite, Obsidian, curl, JSON,
  local paths, terminal output, `execute_code`, `skill_view`, or "Approved
  permanently" unless debugging.
- Do not send both the interactive card and a long Markdown report. The card is
  the report.
- Do not echo recognized image contents back to the parent. Recognition details
  belong in Shensi JSON/Markdown, not in Feishu chat.
- Do not compare or restate your own preliminary analysis after Shensi returns a
  card. Shensi/card output is the source of truth.
- Tool execution and permission events are internal. Never forward approval UI
  text, tool call text, or "Approved for session/permanently" messages to
  Feishu.

Visible Feishu messages should be limited to these shapes:

- After receiving an image: "已收到图片，点击「慎思分析」开始处理。"
- While analyzing: "正在分析这张错题，完成后我会发确认卡片。"
- After sending the card: no extra text.
- After confirm: "已确认入库。错题卡和 D+1/D+3/D+7 复习任务已更新。"
- After discard: "已丢弃这条分析，不会写入错题卡或复习计划。"

Never bypass the Shensi APIs for writes.
```

Hermes runtime permissions:

- Configure Hermes/tool runtime so Shensi wrapper calls are auto-approved in the
  cloud session.
- Do not route permission approval cards/messages into Feishu. Approval UI is
  an operator concern, not a parent-facing chat message.
- If the runtime cannot hide approval messages, run the Shensi wrapper in a
  trusted service account/session where approvals are pre-granted, or move the
  wrapper call behind a small server-side endpoint that Hermes can call without
  interactive approval.
