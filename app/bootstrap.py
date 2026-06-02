from __future__ import annotations

from dataclasses import dataclass

from app.config import Settings
from app.services.obsidian_service import ObsidianService
from app.services.sqlite_service import SQLiteService


@dataclass(frozen=True)
class BootstrapStatus:
    db_path: str
    vault_path: str
    database_ready: bool
    vault_ready: bool


def initialize_storage(settings: Settings) -> BootstrapStatus:
    sqlite = SQLiteService(settings.db_path)
    obsidian = ObsidianService(settings.vault_path)

    sqlite.initialize()
    obsidian.initialize_vault()

    return BootstrapStatus(
        db_path=str(settings.db_path),
        vault_path=str(settings.vault_path),
        database_ready=sqlite.health_check(),
        vault_ready=obsidian.health_check(),
    )
