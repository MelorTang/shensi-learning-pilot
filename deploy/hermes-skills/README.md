# Hermes Skills

This folder contains Hermes skill files that are meant to be installed on the
cloud server, not loaded automatically by the FastAPI app.

## Install on cloud

### shensi-antigravity (慎思错题机器人)

```bash
mkdir -p ~/.hermes/skills/shensi-antigravity
cp /home/admin/apps/shensi-learning-pilot/deploy/hermes-skills/shensi-antigravity/SKILL.md \
  ~/.hermes/skills/shensi-antigravity/SKILL.md
```

### shensi-tutor (慎思辅导机器人)

```bash
mkdir -p ~/.hermes/skills/shensi-tutor
cp /home/admin/apps/shensi-learning-pilot/deploy/hermes-skills/shensi-tutor/SKILL.md \
  ~/.hermes/skills/shensi-tutor/SKILL.md
systemctl --user restart hermes-gateway
```

Then restart the Hermes gateway session or start a new Hermes session so the
skills are picked up.

## Skill assignments

| 机器人 | Skill | 职责 |
|--------|-------|------|
| 慎思错题机器人 | `shensi-antigravity`（历史/备用） | 图片分析、Antigravity 识图、错题入库 |
| 慎思辅导机器人 | `shensi-tutor` | 日报、复习任务、讲题、学习建议、查询统计 |

- 慎思错题机器人当前推荐走 **Shensi Direct Router**（`run_feishu_ws.py --router`），不使用 Hermes LLM。
- 辅导机器人**不要**安装 shensi-antigravity skill，避免它接管错题入库流程。

## Purpose

`shensi-antigravity` (historical / backup only) tells Hermes to:

- treat itself as a thin Feishu router
- call the trusted Shensi wrappers
- avoid doing final homework judgment with Hermes' own vision model

> This skill is **no longer the recommended path**.  Use the Shensi Direct
> Router (`run_feishu_ws.py --router`) for the mistake-entry bot instead.

`shensi-tutor` tells Hermes to:

- act as a study coach and review-explainer
- query Shensi APIs for stats, reviews, reports, and concept mistakes
- also call `POST /reports/daily/regenerate` to generate daily reports
- never ingest images, confirm, discard, or call Antigravity wrappers
- keep replies warm, concrete, and actionable
