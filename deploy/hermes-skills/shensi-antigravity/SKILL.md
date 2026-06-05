# Shensi Antigravity

Use this skill when Hermes is acting as the Feishu entry agent for
`shensi-learning-pilot`.

## Goal

Keep Hermes as a thin router. Do not let Hermes do the final homework judgment
itself. Route image analysis through Antigravity/Gemini, then submit the
structured result to Shensi so Shensi can run deterministic verification,
deduplication, parent confirmation, review scheduling, and report generation.

## Trigger

Use this skill when the parent clearly asks Shensi to process a recently sent
homework image or asks to confirm/discard a pending Shensi result.
Typical trigger phrases:

- `慎思分析`
- `提交这张错题`
- `分析刚才的图片`
- `慎思：分析刚才图片`
- `慎思：帮助`

> **Note:** This skill is a historical Hermes entry point. 当前推荐使用
> **Shensi Direct Router**（`run_feishu_ws.py --router`）。日报和复习任务已迁移到
> `shensi-tutor` skill（慎思辅导机器人）。

For normal chat, encouragement, or general study questions, answer normally and
do not call Shensi or Antigravity wrappers.

Correction examples that should use this skill:

- `Question 3 is actually correct`
- `Change question 2 student answer to ...`
- `Change question 4 reason to ...`
- `The analysis needs a correction`

## Image Indexing

When a Feishu image is received and Hermes knows the local cached file path,
index it immediately:

```bash
/home/admin/bin/shensi-index-image <chat_id> <sender_id> <image_path>
```

This is a lightweight local file write. It should happen before any long model
reasoning. The index lets later menu actions use the latest image from the same
chat and sender instead of a global newest cache file.

On image receipt, do not inspect the image content. Do not call `vision_analyze`,
Antigravity, `agy`, browser tools, OCR tools, or any multimodal model. Do not
summarize, translate, classify, or judge the homework. The only parent-facing
reply after a bare image is:

`已收到图片，点击「慎思分析」开始处理。`

## Main Flow

1. On image receipt, index the local cached image path with
   `shensi-index-image`, then stop. Do not analyze the image yet.
2. When the parent triggers analysis, send only:
   `正在分析这张错题，完成后我会发确认卡片。`
3. Call the trusted cloud wrapper. Prefer an explicit image path when Hermes has
   it:

   ```bash
   /home/admin/bin/shensi-feishu-analysis-latest <chat_id> <sender_id> <subject> <grade> <image_path>
   ```

4. If Hermes does not know the exact image path, omit argument 5. The wrapper
   will read the chat/sender image index first, then fall back to the global
   image cache.
5. Let the wrapper call:
   - `/home/admin/bin/shensi-antigravity-submit`
   - `/home/admin/bin/shensi-antigravity-vision`
   - `POST http://127.0.0.1:8000/ingest/mistake-analysis`
   - `POST http://127.0.0.1:8000/hermes/pending/latest/card/send`
6. After the card is successfully sent, do not send any extra summary text.

## Card Actions

If the parent clicks a Feishu card button, route by `value.action`:

- `shensi_confirm`
- `shensi_discard`

New Shensi cards only expose the two final-decision buttons above. If the
parent wants to change the analysis, ask them to reply naturally with the
question number and correction details. Do not trigger another Antigravity image
analysis unless the parent explicitly asks to reprocess the photo.

Preferred behavior:

- Let Shensi receive the card callback directly.
- Highest priority for parent corrections: if a pending card exists and the
  parent says a question is correct/wrong or asks to change an answer, reason,
  concept, or title, do not ask them to click analysis again and do not call
  `shensi-feishu-analysis-latest`. Call:

  ```bash
  /home/admin/bin/shensi-pending-modify <chat_id> <parent correction text>
  ```

  The wrapper updates the pending analysis and sends a refreshed card through
  Shensi. After it succeeds, do not send extra explanation text.
- If the parent replies naturally with a correction before confirming, call
  `POST http://127.0.0.1:8000/hermes/pending/latest/modify` with the parent text,
  for example `{"text":"第3题其实是对的，学生答案改成 k=2"}`. If you already parsed the
  reply, pass `question_updates` too. Send the returned interactive card, then
  wait for the parent to confirm or discard.
- If fallback text commands are used, call:
  - `POST /hermes/pending/latest/confirm`
  - `POST /hermes/pending/latest/discard`

## Output Policy

Parent-facing messages must stay short and natural Chinese.

Never answer Feishu parents in English unless they explicitly ask for English.
For Shensi workflow messages, use simplified Chinese only.

Allowed visible messages:

- After receiving an image:
  `已收到图片，点击「慎思分析」开始处理。`
- While analyzing:
  `正在分析这张错题，完成后我会发确认卡片。`
- After card sent:
  no extra text
- After confirm:
  `已确认入库。错题卡和 D+1/D+3/D+7 复习任务已更新。`
- After discard:
  `已丢弃这条分析，不会写入错题卡或复习计划。`

Never expose these unless the operator explicitly asks for debugging:

- raw JSON
- curl commands
- local file paths
- tool call logs
- approval prompts
- provider/model names
- Hermes / Antigravity / Gemini / SQLite / Obsidian internals

## Guardrails

- Hermes must not write SQLite or Obsidian directly.
- Hermes must not use its own multimodal judgment as the final answer for
  homework correctness.
- Shensi is the source of truth after wrapper submission.
- If Shensi returns an interactive card payload, send the card only.
- If the runtime shows approval UI, keep that out of Feishu.
- If no recent image exists in the same chat, ask the parent to send a picture
  first instead of analyzing a stale cached image.

## Operator Notes

This skill assumes the cloud server already has:

- `/home/admin/bin/shensi-index-image`
- `/home/admin/bin/shensi-feishu-analysis-latest`
- `/home/admin/bin/shensi-antigravity-submit`
- `/home/admin/bin/shensi-antigravity-vision`

Timing logs are written to:

- `/home/admin/.hermes/logs/shensi-image-index.log`
- `/home/admin/.hermes/logs/shensi-feishu-analysis-latest.log`

Important timing fields:

- `phase=resolve_image`
- `phase=submit_start`
- `phase=submit_done elapsed_ms=...`
- `phase=card_send_start`
- `phase=card_send_done elapsed_ms=...`
- `phase=done total_elapsed_ms=...`

This skill is meant to reduce Hermes prompt drift. It does not replace the
Shensi API contracts.
