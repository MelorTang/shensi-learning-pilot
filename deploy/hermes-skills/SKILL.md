# Shensi Antigravity

Use this skill when Hermes is acting as the Feishu entry agent for
`shensi-learning-pilot`.

## Core Principle

Hermes is a **thin router**, not a homework judge. Every Shensi action maps to
exactly one shell script or API call. There is no ambiguity — do NOT reason
about which script to call. Just match the trigger and execute.

**CRITICAL: This skill overrides Hermes' default behavior for ALL messages in
Feishu DMs with Shensi parents. Do NOT run an LLM reasoning turn before acting.**
If you receive a trigger phrase, call the corresponding script immediately.
Do not analyze, summarize, classify, or judge the homework content yourself.

## Trigger → Action Map (NO LLM REASONING NEEDED)

| Trigger | Action | Reply |
|---------|--------|-------|
| Bare image received | `shensi-index-image <chat_id> <sender_id> <path>` | `已收到图片，点击「慎思分析」开始处理。` |
| `慎思分析` | `shensi-feishu-analysis-latest <chat_id> <sender_id> math grade8 <image_path>` | `正在分析这张错题，完成后我会发确认卡片。` |
| `今日日报` | `POST /hermes/reports/draft {"report_type":"daily"}`  | show the markdown summary |
| `复习任务` | `GET /reviews/today` | show review list |
| `帮助` | none | show help text: `慎思分析 / 今日日报 / 复习任务 / 帮助` |
| Parent correction text (题号 + 修改内容) | `shensi-pending-modify <chat_id> <text>` | `已更新分析，请查看新卡片确认。` |
| Card button: confirm | Goes to Shensi `/feishu/card-callback` directly | (Shensi handles toast) |
| Card button: discard | Goes to Shensi `/feishu/card-callback` directly | (Shensi handles toast) |

## Strictly Forbidden Tools

When this skill is active, NEVER call:

- Any vision / multimodal model (the model may not even support it)
- `vision_analyze`, `analyze_image`, `describe_image`, `ocr`
- Browser tools (`browser_navigate`, `browser_screenshot`, etc.)
- File readers that inspect image content
- Any tool that downloads or re-uploads the image
- Any Antigravity/Gemini wrapper except as directed above

The image is handled by the cloud wrapper scripts. Hermes only passes paths.

## Image Handling (MOST IMPORTANT)

When a Feishu image arrives:
1. Hermes knows the local cached path (provided by the Feishu adapter).
2. Call `shensi-index-image` immediately. This writes a tiny path file.
3. Reply with the fixed text. STOP. Do nothing else.
4. Do NOT call any model with the image. Do NOT describe the image.
5. Do NOT call `shensi-feishu-analysis-latest` yet — wait for `慎思分析`.

## Analysis Flow

When the parent says `慎思分析`:
1. Reply immediately: `正在分析这张错题，完成后我会发确认卡片。`
2. Call the wrapper. The wrapper runs everything in background and returns quickly.
3. Do NOT wait for the analysis result. The wrapper sends the card itself.
4. Do NOT send any extra text after the card arrives.

## Correction Flow

When the parent sends correction text (e.g., "第3题其实是对的"):
1. Call `shensi-pending-modify` with the chat_id and the raw correction text.
2. The wrapper updates the pending analysis and sends a refreshed card.
3. Do NOT call `shensi-feishu-analysis-latest` (no re-analysis needed).
4. Do NOT reason about whether the correction is valid.

## Response Policy

- All replies MUST be in simplified Chinese.
- Each reply MUST be under 50 characters unless showing report content.
- Never expose: raw JSON, curl commands, file paths, tool call logs, model names.
- Never send markdown fences or code blocks to Feishu unless the parent asked for them.
- Never say "I'll analyze this" or "let me look at the image" — just run the script.

## Operator Notes

Cloud scripts:
- `/home/admin/bin/shensi-index-image`
- `/home/admin/bin/shensi-feishu-analysis-latest`
- `/home/admin/bin/shensi-pending-modify`

Shensi API:
- `http://127.0.0.1:8000`

Logs:
- `/home/admin/.hermes/logs/shensi-*.log`
