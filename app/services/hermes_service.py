from __future__ import annotations

from typing import Any

from app.services.sqlite_service import SQLiteService


class HermesService:
    """Read-only query boundary for the future Hermes copilot."""

    def __init__(self, sqlite: SQLiteService) -> None:
        self.sqlite = sqlite

    def recent_stats(self, days: int = 14) -> dict[str, Any]:
        return self.sqlite.stats(days=days)

    def concept_mistakes(self, concept_name: str) -> list[dict[str, Any]]:
        return self.sqlite.concept_mistakes(concept_name)
