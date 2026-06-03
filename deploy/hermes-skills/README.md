# Hermes Skills

This folder contains Hermes skill files that are meant to be installed on the
cloud server, not loaded automatically by the FastAPI app.

## Install on cloud

```bash
mkdir -p ~/.hermes/skills/shensi-antigravity
cp /home/admin/apps/shensi-learning-pilot/deploy/hermes-skills/shensi-antigravity/SKILL.md \
  ~/.hermes/skills/shensi-antigravity/SKILL.md
```

Then restart the Hermes gateway session or start a new Hermes session so the
skill is picked up.

## Purpose

`shensi-antigravity` tells Hermes to:

- treat itself as a thin Feishu router
- call the trusted Shensi wrappers
- avoid doing final homework judgment with Hermes' own vision model
- avoid leaking tool logs and debug text into the parent chat
