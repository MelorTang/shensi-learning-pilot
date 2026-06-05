# Shensi Antigravity — HISTORICAL / BACKUP

> **当前生产推荐使用 Shensi Direct Router**（`run_feishu_ws.py --router`）。
> 日报和复习任务已迁移到 `shensi-tutor` skill（慎思辅导机器人）。
> 本 skill 仅供历史参考和紧急回退。

## Goal

Keep Hermes as a thin router. Do not let Hermes do the final homework judgment
itself. Route image analysis through Antigravity/Gemini, then submit the
structured result to Shensi so Shensi can run deterministic verification,
deduplication, parent confirmation, review scheduling, and report generation.

## Trigger

Typical trigger phrases:

- `慎思分析`
- `提交这张错题`
- `分析刚才的图片`
- `慎思：分析刚才图片`
- `慎思：帮助`

For normal chat, encouragement, or general study questions, answer normally and
do not call Shensi or Antigravity wrappers.

## Image Indexing

When a Feishu image is received and Hermes knows the local cached file path,
index it immediately:

```bash
/home/admin/bin/shensi-index-image <chat_id> <sender_id> <image_path>
```

This is a lightweight local file write. The index lets later menu actions use
the latest image from the same chat and sender.

On image receipt, do not inspect the image content. Do not call `vision_analyze`,
Antigravity, `agy`, browser tools, OCR tools, or any multimodal model. The only
parent-facing reply after a bare image is:

`已收到图片，点击「慎思分析」开始处理。`

## Main Flow

1. On image receipt, index the local cached image path with
   `shensi-index-image`, then stop. Do not analyze the image yet.
2. When the parent triggers analysis, send only:
   `正在分析这张错题，完成后我会发确认卡片。`
3. Call the trusted cloud wrapper:

   ```bash
   /home/admin/bin/shensi-feishu-analysis-latest <chat_id> <sender_id> <subject> <grade> <image_path>
   ```

4. Let the wrapper call:
   - `/home/admin/bin/shensi-antigravity-submit`
   - `/home/admin/bin/shensi-antigravity-vision`
   - `POST http://127.0.0.1:8000/ingest/mistake-analysis`
   - `POST http://127.0.0.1:8000/hermes/pending/latest/card/send`
5. After the card is successfully sent, do not send any extra summary text.

## Card Actions

If the parent clicks a Feishu card button, route by `value.action`:

- `shensi_confirm`
- `shensi_discard`

Let Shensi receive the card callback directly.

**If the parent thinks the analysis is wrong**, tell them to tap 「丢弃」
and then re-send the image for a fresh analysis.  Do **not** attempt to modify
the pending analysis inline.  Pending modification is no longer supported.

Fallback text commands (if cards are not available):

- `POST /hermes/pending/latest/confirm`
- `POST /hermes/pending/latest/discard`

## Output Policy

Parent-facing messages must stay short and natural Chinese.

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

Never expose: raw JSON, curl commands, local file paths, tool call logs,
approval prompts, provider/model names, Hermes / Antigravity / Gemini /
SQLite / Obsidian internals.

## Guardrails

- Hermes must not write SQLite or Obsidian directly.
- Hermes must not use its own multimodal judgment as the final answer.
- Shensi is the source of truth after wrapper submission.
- If Shensi returns an interactive card payload, send the card only.
- If the runtime shows approval UI, keep that out of Feishu.

## Operator Notes

This skill assumes the cloud server already has:

- `/home/admin/bin/shensi-index-image`
- `/home/admin/bin/shensi-feishu-analysis-latest`
- `/home/admin/bin/shensi-antigravity-submit`
- `/home/admin/bin/shensi-antigravity-vision`

Timing logs: `/home/admin/.hermes/logs/shensi-*.log`
