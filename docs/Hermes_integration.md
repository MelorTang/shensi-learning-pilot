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

## Ingest API

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

When the parent sends a mistake image, do not write SQLite or Obsidian directly.
Call POST http://127.0.0.1:8000/ingest/mistake-image with a stable message_id,
platform="feishu", sender_id, chat_id, subject, grade, note, and either image_path
or image_base64.

After Shensi returns status="waiting_confirmation", show the parent the key fields
from analysis: title, concepts, error_types, root_cause, confidence, and ask whether
to confirm, discard, or modify.

If the parent confirms, call POST /mistakes/{mistake_id}/confirm.
If the parent discards, call POST /mistakes/{mistake_id}/discard.
If the parent edits fields, call confirm with action="modify" and put allowed edits
in overrides.

Never bypass the Shensi APIs for writes.
```
