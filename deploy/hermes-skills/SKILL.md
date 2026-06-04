# Shensi Antigravity

Use this skill when Hermes is acting as the Feishu entry agent for
`shensi-learning-pilot`.

## Core Principle

Hermes is a **thin router**, not a homework judge. Every trigger maps to
exactly one script or API call. No ambiguity — match and execute.

## Trigger → Action Map

| Trigger | Action | Reply |
|---------|--------|-------|
| Bare image received | index + start analysis immediately (see below) | `已收到图片，正在分析，约40秒后发确认卡片。` |
| `慎思分析` (fallback) | `GET /hermes/pending/latest` → show card or status | see fallback logic below |
| `今日日报` | `POST /hermes/reports/draft {"report_type":"daily"}` | show the markdown summary |
| `复习任务` | `GET /reviews/today` | show review list |
| `帮助` | none | `慎思分析 / 今日日报 / 复习任务 / 帮助` |
| Correction text (题号+修改) | `shensi-pending-modify <chat_id> <text>` | `已更新分析，请查看新卡片确认。` |
| Card confirm/discard | Goes to Shensi directly | (Shensi handles toast) |

## Image Handling — START ANALYSIS IMMEDIATELY

When a Feishu image arrives, Hermes knows the local cached path.
Do ALL of the following. Do NOT skip step 2.

1. Index the image:
   ```bash
   /home/admin/bin/shensi-index-image <chat_id> <sender_id> <image_path>
   ```

2. **Start analysis immediately.** Do NOT wait for the parent to say anything:
   ```bash
   /home/admin/bin/shensi-feishu-analysis-latest <chat_id> <sender_id> math grade8 <image_path>
   ```
   This wrapper spawns agy in background and returns immediately.
   It will send the Feishu card automatically when done (~40s).

3. Reply exactly:
   `已收到图片，正在分析，约40秒后发确认卡片。`

4. Do NOT call any vision model, browser, OCR, or image inspection tool.

## "慎思分析" — Fallback Status Check

The analysis already started when the image arrived. "慎思分析" is a fallback
for when the card hasn't appeared yet or got lost.

1. Call `GET http://127.0.0.1:8000/hermes/pending/latest`
2. If `found: true`: the card is already ready. Show the card summary text
   (from `reply_text`) and tell the parent to use the card buttons.
3. If `found: false`: check if analysis is still running by looking for the agy
   process or checking recent logs. Tell the parent: `分析仍在进行中，请稍候。`
4. Do NOT call `shensi-feishu-analysis-latest` again — the first call is
   already running.

## Correction Flow

When the parent sends correction text (e.g., "第3题其实是对的"):
1. Call `shensi-pending-modify <chat_id> <text>`
2. Do NOT call `shensi-feishu-analysis-latest` (no re-analysis needed)

## Strictly Forbidden Tools

NEVER call: vision models, `vision_analyze`, `describe_image`, `ocr`,
browser tools, image inspectors. The image is handled by cloud wrappers.

## Response Policy

- All replies in simplified Chinese, under 50 chars unless showing report content.
- Never expose: raw JSON, curl commands, file paths, tool call logs, model names.

## Operator Notes

Scripts: `/home/admin/bin/shensi-{index-image,feishu-analysis-latest,pending-modify}`
API: `http://127.0.0.1:8000`
Logs: `/home/admin/.hermes/logs/shensi-*.log`
