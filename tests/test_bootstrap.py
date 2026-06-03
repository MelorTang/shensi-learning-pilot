from __future__ import annotations

from app.bootstrap import initialize_storage
from app.config import Settings


def test_initialize_storage(tmp_path):
    settings = Settings(
        db_path=tmp_path / "shensi.db",
        vault_path=tmp_path / "vault" / "Shensi-Learning-Vault",
    )

    status = initialize_storage(settings)

    assert status.database_ready is True
    assert status.vault_ready is True
    assert (tmp_path / "shensi.db").exists()
    assert (tmp_path / "vault" / "Shensi-Learning-Vault" / "08-Raw-Images").exists()


def test_settings_accepts_hermes_feishu_env_aliases(monkeypatch):
    monkeypatch.delenv("SHENSI_FEISHU_APP_ID", raising=False)
    monkeypatch.delenv("SHENSI_FEISHU_APP_SECRET", raising=False)
    monkeypatch.setenv("FEISHU_APP_ID", "cli_from_hermes")
    monkeypatch.setenv("FEISHU_APP_SECRET", "secret_from_hermes")

    settings = Settings.load()

    assert settings.feishu_app_id == "cli_from_hermes"
    assert settings.feishu_app_secret == "secret_from_hermes"
