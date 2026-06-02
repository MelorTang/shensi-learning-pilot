# PRD Gaps and Adjustments

## Before Phase 2

- Define Feishu event verification precisely: token challenge, encrypted payload support, and failure response shape.
- Define message state transitions: received, duplicated, downloaded, analyzed, waiting_confirmation, confirmed, discarded, failed.
- Decide whether raw payloads are retained forever or rotated after a fixed period.

## Before Phase 4

- Lock the AI provider and model configuration contract.
- Add a strict JSON schema for mistake analysis output.
- Define confidence thresholds, especially the cutoff for `pending_more_info`.
- Add test fixtures for blurry image, incomplete question, missing student answer, and unsupported subject.

## Before Phase 6

- Clarify parent edit surface: which fields can be changed directly, which require a second confirmation, and which are AI-only suggestions.
- Add a durable confirmation token or session id for Feishu card actions.
- Define whether a discarded analysis should keep the raw payload and AI JSON for audit.

## Before Reports

- Define report regeneration rules: overwrite, versioned draft, or append-only report history.
- Define timezone behavior. Current environment is Asia/Shanghai, so scheduled jobs should use that explicitly.

## Suggested PRD Changes

- Add an explicit status model for mistakes, reviews, Feishu messages, and AI runs.
- Add operational acceptance criteria: logs, retry behavior, and failure notification to parent.
- Add a privacy retention section with concrete retention windows for images, raw payloads, and AI outputs.
- Add a small local development section: `.env`, `python scripts/init_db.py`, and `uvicorn app.main:app --reload`.
