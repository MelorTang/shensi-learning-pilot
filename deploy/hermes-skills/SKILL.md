# Shensi Antigravity — DEPRECATED

> **Do not install this root skill for current production.**
> It was the original Hermes entry-point skill.  当前架构已经改为双机器人分工。

## Current architecture (2026-06)

| 机器人 | 入口 | Skill |
|--------|------|-------|
| 慎思错题机器人 | `systemd shensi-router` (`run_feishu_ws.py --router`) | 不需要 Hermes skill |
| 慎思辅导机器人 | Hermes gateway | `deploy/hermes-skills/shensi-tutor/SKILL.md` |

## What this file used to do

- Route Feishu images through Antigravity/Gemini via shell wrappers
- Handle `慎思分析`, `今日日报`, `复习任务`, parent corrections
- Call `shensi-pending-modify` for correction text

All of this has been replaced:

- Image analysis → `run_feishu_ws.py --router` (keywords, no LLM)
- Daily reports / review tasks → `shensi-tutor` skill (Hermes + read-only APIs)
- Parent correction / pending modify → no longer supported (discard + re-analyze instead)

## Historical reference

The detailed wrapper-based flow is documented in:

- `deploy/hermes-skills/shensi-antigravity/SKILL.md`
- `scripts/cloud/shensi-feishu-analysis-latest`
- `scripts/cloud/shensi-antigravity-submit`
- `scripts/cloud/shensi-antigravity-vision`
