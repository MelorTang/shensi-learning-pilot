# Shensi Learning Pilot

MVP for "慎思 | AI 学习诊断与复盘系统".

The current local loop can run without Feishu, Hermes, or AI credentials:

```text
local/Hermes payload
-> raw payload + image saved
-> stub AI mistake analysis JSON
-> parent confirm/discard/modify API
-> SQLite records
-> Obsidian mistake card
-> D+1/D+3/D+7 reviews
-> daily report
-> weekly report
-> Hermes read-only query API
```

## Quick Start

```powershell
python scripts/init_db.py
python scripts/run_local_demo.py
python -m uvicorn app.main:app --reload
```

Then open:

```text
http://127.0.0.1:8000/health
```

## Local MVP Demo API

Submit and auto-confirm one sample mistake:

```powershell
Invoke-RestMethod `
  -Method Post `
  -Uri http://127.0.0.1:8000/local/simulate-upload `
  -ContentType "application/json" `
  -Body (Get-Content examples/sample_payload.json -Raw)
```

Submit without auto-confirm:

```powershell
Invoke-RestMethod `
  -Method Post `
  -Uri http://127.0.0.1:8000/local/simulate-upload `
  -ContentType "application/json" `
  -Body '{"message_id":"local-manual-001","subject":"math","grade":"grade7","note":"manual confirm demo","auto_confirm":false}'
```

Then confirm:

```powershell
Invoke-RestMethod `
  -Method Post `
  -Uri http://127.0.0.1:8000/mistakes/<mistake_id>/confirm `
  -ContentType "application/json" `
  -Body '{"action":"confirm","confirmed_by":"local_parent","overrides":{}}'
```

Discard is also available:

```text
POST /mistakes/<mistake_id>/discard
```

## Hermes Gateway Flow

Recommended production-ish MVP flow:

```text
Parent in Feishu
-> Hermes Agent Feishu Gateway
-> POST /ingest/mistake-image
-> Shensi workflow
-> SQLite + Obsidian
```

Hermes should not write SQLite or Obsidian directly. It should call Shensi APIs so deduplication, parent confirmation, review tasks, reports, and indexes stay consistent.

Preferred Hermes ingest endpoint when Hermes/MiMo has already read the image:

```text
POST http://127.0.0.1:8000/ingest/mistake-analysis
```

Fallback image-only endpoint:

```text
POST http://127.0.0.1:8000/ingest/mistake-image
```

Example:

```powershell
Invoke-RestMethod `
  -Method Post `
  -Uri http://127.0.0.1:8000/ingest/mistake-image `
  -ContentType "application/json" `
  -Body '{"message_id":"hermes-feishu-001","platform":"feishu","image_path":"examples/sample_mistake.svg","subject":"math","grade":"grade7","note":"from Hermes","auto_confirm":false}'
```

See [docs/Hermes_integration.md](docs/Hermes_integration.md) for the Hermes instruction draft.

For real Feishu homework images, the recommended cloud path is:

```text
Feishu -> Hermes -> shensi-antigravity-submit -> Antigravity/Gemini vision JSON
-> Shensi deterministic verification -> parent confirmation -> SQLite/Obsidian
```

Hermes can use a cheap routing model in this path because it only needs to call
fixed wrapper scripts and paste the result back into Feishu. It should not make
the grading decision itself, and it should not write SQLite or Obsidian
directly. The wrapper should send per-question fields in
`analysis.question_items`, which lets Obsidian cards show every question,
student steps, verdict, correct answer, and error reason instead of a flat
summary.

For Feishu bot-menu analysis, Hermes must pass the latest image from the same
chat/user into the wrapper. Do not select a stale global image cache file. Use a
fresh Shensi `message_id` per image; repeated ids intentionally deduplicate and
return the old result.

Recommended Feishu UX:

- Bot menu: `慎思分析`, `今日日报`, `复习任务`, `帮助`
- Result card buttons: `确认入库`, `丢弃`, `重新分析`, `修改后入库`
- Keep confirm/discard actions on the card, because they belong to one specific
  analysis result.
- Feishu card callback endpoint: `POST /feishu/card-callback`

Shensi now also runs a deterministic math verification layer after Hermes
submits extracted JSON. The current MVP verifier covers common junior-high
algebra items:

- one-variable linear equations, including simple distributive parentheses like `3(x-2)=12`
- ratio equations that stay linear after cross multiplication, such as `x/3=4/6`
- linear simplification and like-term collection, such as `4x+3-x+5`
- linear function substitution such as `y=-3x+2` or `y = -3x + 2` with a given `x`
- two-variable linear systems such as `x+y=10, 2x-y=2`
- slope from two points such as `A(1,3), B(5,11)`
- rectangle area/perimeter and triangle area when dimensions are explicit

If the verifier can calculate the answer and disagrees with the LLM verdict,
Shensi stores the original LLM verdict as `llm_is_correct`, overrides
`is_correct` with the verified result, and writes the verification method into
the Obsidian mistake card. Unsupported, parse-failed, or conflicting items are
marked with `needs_parent_review=true` so the parent confirmation step can treat
them cautiously.

`POST /ingest/mistake-analysis` also returns a top-level
`confirmation_summary` for Hermes to show in Feishu. It includes total question
count, Shensi-verified count, wrong question ids, and question ids that need
parent review. If `auto_confirm=true` is sent but any question needs parent
review, Shensi returns `auto_confirm_blocked=true` and keeps the mistake in
`waiting_confirmation`.

Recommended Hermes prompt shape:

```text
Step 1: read the image and extract structured JSON only.
Step 2: include expected_question_count and every visible question in question_items.
Step 3: send that JSON to POST /ingest/mistake-analysis.
Do not write SQLite or Obsidian directly. Do not use /ingest/mistake-image if
you already have structured analysis.
```

## Useful APIs

- `GET /health`
- `POST /ingest/mistake-analysis`
- `POST /ingest/mistake-image`
- `POST /feishu/webhook`
- `POST /feishu/card-callback`
- `POST /local/simulate-upload`
- `POST /mistakes/{mistake_id}/confirm`
- `POST /mistakes/{mistake_id}/discard`
- `GET /mistakes`
- `GET /reviews/today`
- `GET /hermes/pending/latest`
- `GET /hermes/pending/latest/card`
- `POST /hermes/pending/latest/card/send`
- `POST /hermes/pending/latest/confirm`
- `POST /hermes/pending/latest/discard`
- `POST /reports/daily/regenerate`
- `POST /reports/weekly/regenerate`
- `GET /reports`
- `GET /hermes/stats?days=14`
- `GET /hermes/concepts/{concept_name}/mistakes`
- `POST /hermes/reports/draft`

`GET /hermes/pending/latest/card` returns both the raw card object and a
Feishu-ready `feishu_message` envelope with `msg_type="interactive"` and
`content` as the card JSON string. Hermes should send that envelope through the
Feishu send/reply tool instead of pasting JSON into chat.

If Hermes' own Feishu send tool turns interactive cards into plain text, call
Shensi's direct sender instead:

```text
POST /hermes/pending/latest/card/send
```

Use either `{"reply_to_message_id":"<feishu message id>"}` to reply with a card,
or `{"receive_id":"<chat id>","receive_id_type":"chat_id"}` to send the card to
a chat.

## Generated Files

Defaults:

- SQLite: `data/shensi.db`
- Obsidian vault: `vault/Shensi-Learning-Vault`
- Raw images: `vault/Shensi-Learning-Vault/08-Raw-Images`
- Raw payloads and AI JSON: `vault/Shensi-Learning-Vault/09-AI-Raw-JSON`
- Mistake cards: `vault/Shensi-Learning-Vault/02-Mistakes`
- Daily reports: `vault/Shensi-Learning-Vault/04-Reports/Daily`
- Weekly reports: `vault/Shensi-Learning-Vault/04-Reports/Weekly`

## Configuration

Copy `.env.example` to `.env` when local overrides are needed. The app also runs with defaults.

Key defaults:

- Database: `data/shensi.db`
- Vault: `vault/Shensi-Learning-Vault`
- App environment: `local`
- AI provider: `stub`
- Timezone: `Asia/Shanghai`

## Feishu Bot Setup

The recommended path is to let Hermes Agent handle Feishu. Configure Hermes Agent's Feishu / Lark gateway, then have Hermes call `POST /ingest/mistake-image`.

The direct Shensi Feishu handlers below are kept as a fallback and local debugging option.

### Option A: Long Connection

This is the easiest local MVP path because it does not need a public domain.

In Feishu Developer Console:

- Event subscription mode: use long connection.
- Subscribe to `im.message.receive_v1`.
- Click the connection verification button after the local client is running.

Run the local Feishu client:

```powershell
python scripts/run_feishu_ws.py
```

Keep that terminal running while testing image uploads in Feishu.

### Option B: Webhook URL

Use this when you have a public HTTPS domain or tunnel. The app can receive Feishu message events at:

```text
POST http://<your-public-domain>/feishu/webhook
```

For local development, expose the FastAPI server with a tunnel such as ngrok or another HTTPS tunnel, then put the tunneled URL in the Feishu app event subscription callback.

Add these values to `.env`:

```dotenv
SHENSI_FEISHU_APP_ID=cli_xxx
SHENSI_FEISHU_APP_SECRET=xxx
SHENSI_FEISHU_VERIFICATION_TOKEN=xxx
SHENSI_FEISHU_ENCRYPT_KEY=
SHENSI_FEISHU_DOWNLOAD_RESOURCES=true
SHENSI_FEISHU_REPLY_ENABLED=false
```

Recommended Feishu app settings for either mode:

- Enable bot capability.
- Subscribe to `im.message.receive_v1`.
- Grant at least one receive-message permission that matches your scene: p2p message, group @ message, or group message.
- Grant message resource permissions needed for downloading message resources.
- For long connection, no public URL or encryption policy is needed.
- For webhook mode, keep event encryption disabled for the MVP, or leave `SHENSI_FEISHU_ENCRYPT_KEY` empty.

When a user sends an image, Feishu includes an `image_key` in the message `content`. The app uses `message_id + image_key` to download the image into `08-Raw-Images`. If credentials are missing or download fails, the local stub image is used so the MVP remains runnable.

## Verification

```powershell
python scripts/init_db.py
python -m pytest
python scripts/run_local_demo.py
```

The demo is idempotent for `message_id=local-demo-001`; rerunning it will not create duplicate mistakes or review tasks.

## Cloud Update

After pushing local code to GitHub, update the running cloud service with:

```bash
cd ~/apps/shensi-learning-pilot
git pull
source .venv/bin/activate
python -m pytest
sudo systemctl restart shensi
curl http://127.0.0.1:8000/health
```
