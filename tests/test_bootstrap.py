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
