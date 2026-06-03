from __future__ import annotations

from app.bootstrap import initialize_storage
from app.config import Settings
from scripts.sync_curriculum import sync_curriculum


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


def test_sync_curriculum_copies_reviewed_cards(tmp_path):
    source = tmp_path / "knowledge" / "curriculum"
    math_dir = source / "数学"
    math_dir.mkdir(parents=True)
    (math_dir / "_TEMPLATE.md").write_text("# skipped", encoding="utf-8")
    (math_dir / "README.md").write_text("# skipped", encoding="utf-8")
    (math_dir / "一元一次方程.md").write_text(
        """---
type: curriculum
subject: math
grade: grade7
status: active
---

# 一元一次方程
""",
        encoding="utf-8",
    )
    (math_dir / "bad.md").write_text("# missing frontmatter", encoding="utf-8")
    target = tmp_path / "vault" / "Shensi-Learning-Vault" / "05-Curriculum"

    result = sync_curriculum(source_root=source, target_root=target)

    assert result == {"copied": 1, "deleted": 0, "skipped": 1}
    assert (target / "数学" / "一元一次方程.md").exists()
    assert not (target / "数学" / "_TEMPLATE.md").exists()
    assert not (target / "数学" / "bad.md").exists()
