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
For a reusable Hermes skill file that can be installed on the cloud host, see
[deploy/hermes-skills/README.md](deploy/hermes-skills/README.md).

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

`/home/admin/bin/shensi-feishu-analysis-latest` also accepts an optional fifth
argument for an explicit image path:

```bash
/home/admin/bin/shensi-feishu-analysis-latest <chat_id> <sender_id> <subject> <grade> <image_path>
```

If this path is provided, the script uses it directly. Otherwise it reads the
chat/sender image index first, then falls back to the newest image file in
`~/.hermes/image_cache`.

Hermes should index each received image as soon as it knows the local cached
file path:

```bash
/home/admin/bin/shensi-index-image <chat_id> <sender_id> <image_path>
```

This keeps `慎思分析` tied to the current Feishu chat and sender, while adding
only a tiny local file write.

For Feishu bot-menu analysis, Hermes must pass the latest image from the same
chat/user into the wrapper. Do not select a stale global image cache file. Use a
fresh Shensi `message_id` per image; repeated ids intentionally deduplicate and
return the old result.

Recommended Feishu UX:

**慎思错题机器人**
- Send an image → auto-analysis → interactive card with `确认入库` / `丢弃`
- Text commands: `慎思分析`, `确认入库`, `丢弃`, `帮助`
- Card buttons route directly to Shensi `/feishu/card-callback`

**慎思辅导机器人**
- `今日日报` / `复习任务` / general study questions → Hermes + shensi-tutor skill

Shensi now also runs a deterministic math verification layer after Hermes
submits extracted JSON. The current MVP verifier covers common junior-high
algebra items:

- one-variable linear equations, including simple distributive parentheses like `3(x-2)=12`
- ratio equations that stay linear after cross multiplication, such as `x/3=4/6`
- linear simplification and like-term collection, such as `4x+3-x+5`
- linear function substitution such as `y=-3x+2` or `y = -3x + 2` with a given `x`
- two-variable linear systems such as `x+y=10, 2x-y=2`
- slope from two points such as `A(1,3), B(5,11)`
- point-on-line conclusions from labeled points, such as whether `Q(6,1)` is on line `MN`
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
- Mistake-driven concept cards: `vault/Shensi-Learning-Vault/03-Concepts`
- Static curriculum cards: `vault/Shensi-Learning-Vault/05-Curriculum`
- Daily reports: `vault/Shensi-Learning-Vault/04-Reports/Daily`
- Weekly reports: `vault/Shensi-Learning-Vault/04-Reports/Weekly`

## Knowledge Base

Confirmed mistakes now maintain two lightweight Markdown knowledge layers:

- `03-Concepts/<学科>`: mistake-driven concept cards. These summarize the latest
  mistake pattern, common error types, parent guidance, and linked confirmed
  mistake notes for that concept.
- `05-Curriculum/<学科>`: static curriculum cards. These hold stable definitions,
  learning steps, common pitfalls, and parent guidance. They are created lazily
  from confirmed mistakes, so the knowledge base grows around real weak points
  instead of importing full textbooks up front.

The first built-in static profiles focus on junior-high math concepts such as
一元一次方程、一次函数求值、二元一次方程组、斜率公式、去括号、移项. Unknown concepts
still get a generic curriculum card that can be edited later in Obsidian.

Committed static curriculum source files live outside the runtime vault:

```text
knowledge/curriculum/数学/*.md
```

This keeps public, non-personal subject knowledge in GitHub while keeping
student data, raw images, generated mistake notes, and SQLite out of Git. After
pulling new curriculum cards on the cloud server, sync them into the Obsidian
vault:

```bash
python scripts/sync_curriculum.py
```

Preview without writing:

```bash
python scripts/sync_curriculum.py --dry-run
```

The sync script skips `README.md` and files beginning with `_`, and only copies
Markdown files whose frontmatter contains `type: curriculum`.

## Maintenance

Raw Feishu images are a cache, not the long-term knowledge source. Once a
mistake has been analyzed and confirmed, the durable data is in SQLite, raw JSON,
and Markdown notes. To keep a small cloud disk healthy, prune old raw images on a
fixed retention window.

Preview files older than 90 days:

```bash
python scripts/prune_raw_images.py --days 90
```

Delete files older than 90 days:

```bash
python scripts/prune_raw_images.py --days 90 --apply
```

Suggested cloud cron:

```cron
15 3 * * 0 cd /home/admin/apps/shensi-learning-pilot && mkdir -p logs && .venv/bin/python scripts/prune_raw_images.py --days 90 --apply >> logs/prune_raw_images.log 2>&1
```

For development or pre-production reset, remove SQLite and the generated vault,
then reinitialize empty storage:

```bash
python scripts/reset_storage.py --yes
```

To keep the Obsidian vault and only reset SQLite:

```bash
python scripts/reset_storage.py --yes --keep-vault
```

## Configuration

Copy `.env.example` to `.env` when local overrides are needed. The app also runs with defaults.

Key defaults:

- Database: `data/shensi.db`
- Vault: `vault/Shensi-Learning-Vault`
- App environment: `local`
- AI provider: `stub`
- Timezone: `Asia/Shanghai`

## Feishu Bot Setup

### Recommended: Shensi Direct Router (No LLM Latency)

The fastest path for the parent experience is the **Shensi Direct Router**.  It
handles `im.message.receive_v1` with fixed keyword matching — no LLM, no Hermes.

```
图片 → <1s → 下载+索引+后台启动 agy → "已收到图片，正在分析..."
慎思分析 → <1s → 后台启动 agy → "正在分析..."
确认入库 / 丢弃 → <1s → POST Shensi API
```

**Commands:** 慎思分析 / 确认入库 / 丢弃 / 帮助
**Not handled:** 今日日报、复习任务、讲题 → 请使用「慎思辅导机器人」

**Start the router locally:**

```powershell
python scripts/run_feishu_ws.py --router
```

**Cloud systemd service:**

```bash
sudo cp deploy/systemd/shensi-router.service /etc/systemd/system/shensi-router.service
sudo systemctl daemon-reload
sudo systemctl enable shensi-router
sudo systemctl start shensi-router
```

The template is at `deploy/systemd/shensi-router.service`.

**When the Shensi Direct Router is active, stop Hermes** to prevent duplicate
`im.message.receive_v1` processing on the same Feishu bot:

```bash
systemctl --user stop hermes-gateway
systemctl --user disable hermes-gateway
```

### Shensi Tutor Bot (Hermes + 只读查询)

A second Feishu bot for study coaching, mistake review, and parent guidance.
It queries Shensi data **read-only** — never ingests images or confirms mistakes.

Install the skill:

```bash
mkdir -p ~/.hermes/skills/shensi-tutor
cp /home/admin/apps/shensi-learning-pilot/deploy/hermes-skills/shensi-tutor/SKILL.md \
  ~/.hermes/skills/shensi-tutor/SKILL.md
systemctl --user restart hermes-gateway
```

- **慎思错题机器人**: shensi-router (no LLM) — 错题图片入库闭环（分析、确认、丢弃）
- **慎思辅导机器人**: Hermes + shensi-tutor skill — 日报、复习任务、讲题、学习建议、查询统计
- Do NOT install shensi-antigravity on the tutor bot — it must not take over
  the mistake-ingest flow

### Option B: Hermes Agent Gateway

Configure Hermes Agent's Feishu / Lark gateway, then have Hermes call `POST /ingest/mistake-image`.

The direct Shensi Feishu handlers below are kept as a fallback and local debugging option.

### Option C: Long Connection (card-actions-only / legacy)

This is the easiest local MVP path because it does not need a public domain.

In Feishu Developer Console:

- Event subscription mode: use long connection.
- Subscribe to `im.message.receive_v1`.
- Subscribe to `card.action.trigger` if Shensi or Hermes needs to receive
  interactive card button clicks.
- Click the connection verification button after the local client is running.

Run the local Feishu client:

```powershell
python scripts/run_feishu_ws.py
```

Keep that terminal running while testing image uploads in Feishu.

If Hermes already handles Feishu messages and Shensi only needs to receive card
button clicks, run the Shensi long-connection client in card-action-only mode:

```powershell
python scripts/run_feishu_ws.py --card-actions-only
```

Cloud systemd user-service example:

```ini
[Unit]
Description=Shensi Feishu Card Action Forwarder
After=network.target

[Service]
Type=simple
WorkingDirectory=/home/admin/apps/shensi-learning-pilot
EnvironmentFile=/home/admin/apps/shensi-learning-pilot/.env
EnvironmentFile=-/home/admin/.hermes/.env
ExecStart=/home/admin/apps/shensi-learning-pilot/.venv/bin/python scripts/run_feishu_ws.py --card-actions-only
Restart=always
RestartSec=5

[Install]
WantedBy=default.target
```

Important cloud note:

- `shensi-feishu-card.service` should load both project `.env` and
  `~/.hermes/.env`.
- `shensi.service` must also load both files if Shensi itself needs to send
  Feishu interactive cards through `/hermes/pending/latest/card/send`.
- If `shensi.service` only loads the project `.env`, the analysis may finish
  and enter `waiting_confirmation`, but card delivery can still fail with
  `HTTP 502` because the FastAPI process cannot read `FEISHU_APP_ID` /
  `FEISHU_APP_SECRET`.

Cloud `shensi-api.service` example:

```ini
[Unit]
Description=Shensi Learning Pilot FastAPI
After=network.target

[Service]
Type=simple
User=admin
WorkingDirectory=/home/admin/apps/shensi-learning-pilot
EnvironmentFile=/home/admin/apps/shensi-learning-pilot/.env
EnvironmentFile=-/home/admin/.hermes/.env
ExecStart=/home/admin/apps/shensi-learning-pilot/.venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

The same template is committed at
`deploy/systemd/shensi-api.service`. Install it on the cloud host with:

```bash
sudo cp deploy/systemd/shensi-api.service /etc/systemd/system/shensi-api.service
sudo systemctl daemon-reload
sudo systemctl enable shensi-api
sudo systemctl restart shensi-api
```

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
- Subscribe to `card.action.trigger` for result-card buttons.
- Grant at least one receive-message permission that matches your scene: p2p message, group @ message, or group message.
- Grant message resource permissions needed for downloading message resources.
- For long connection, no public URL or encryption policy is needed.
- For webhook mode, keep event encryption disabled for the MVP, or leave `SHENSI_FEISHU_ENCRYPT_KEY` empty.
- Shensi prefers `SHENSI_FEISHU_APP_ID` / `SHENSI_FEISHU_APP_SECRET`, but also accepts
  Hermes-style `FEISHU_APP_ID` / `FEISHU_APP_SECRET` and `LARK_APP_ID` /
  `LARK_APP_SECRET`.

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
chmod +x scripts/cloud/shensi-*
ln -sf /home/admin/apps/shensi-learning-pilot/scripts/cloud/shensi-feishu-analysis-latest /home/admin/bin/shensi-feishu-analysis-latest
ln -sf /home/admin/apps/shensi-learning-pilot/scripts/cloud/shensi-antigravity-submit /home/admin/bin/shensi-antigravity-submit
ln -sf /home/admin/apps/shensi-learning-pilot/scripts/cloud/shensi-antigravity-vision /home/admin/bin/shensi-antigravity-vision
sudo cp deploy/systemd/shensi-api.service /etc/systemd/system/shensi-api.service
sudo cp deploy/systemd/shensi-router.service /etc/systemd/system/shensi-router.service
sudo systemctl daemon-reload
sudo systemctl enable shensi-api
sudo systemctl restart shensi-api
sudo systemctl restart shensi-router
systemctl --user stop hermes-gateway 2>/dev/null; true
curl http://127.0.0.1:8000/health
```

If Feishu card delivery fails after analysis completes, check:

```bash
sudo systemctl cat shensi-api
sudo tr '\0' '\n' </proc/$(pgrep -f "uvicorn app.main:app" | head -1)/environ | grep -E 'FEISHU_APP_ID|FEISHU_APP_SECRET|LARK_APP_ID|LARK_APP_SECRET'
tail -n 80 ~/.hermes/logs/shensi-feishu-analysis-latest.log
tail -n 120 ~/.hermes/logs/shensi-antigravity-submit.log
```
