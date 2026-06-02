from __future__ import annotations

from contextlib import asynccontextmanager
from collections.abc import AsyncIterator

from fastapi import FastAPI

from app.api import router as api_router
from app.bootstrap import initialize_storage
from app.config import Settings
from app.feishu.webhook import router as feishu_router


def create_app(settings: Settings | None = None) -> FastAPI:
    loaded_settings = settings or Settings.load()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        initialize_storage(loaded_settings)
        yield

    app = FastAPI(title="Shensi Learning Pilot", version="0.1.0", lifespan=lifespan)
    app.state.settings = loaded_settings
    app.include_router(feishu_router)
    app.include_router(api_router)

    @app.get("/health")
    def health() -> dict[str, object]:
        status = initialize_storage(loaded_settings)
        return {
            "ok": status.database_ready and status.vault_ready,
            "app": loaded_settings.app_name,
            "env": loaded_settings.env,
            "database": {
                "ready": status.database_ready,
                "path": status.db_path,
            },
            "vault": {
                "ready": status.vault_ready,
                "path": status.vault_path,
            },
        }

    return app


settings = Settings.load()
app = create_app(settings)
