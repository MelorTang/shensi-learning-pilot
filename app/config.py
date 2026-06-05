from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
import os


BASE_DIR = Path(__file__).resolve().parent.parent


def _load_dotenv(path: Path) -> None:
    if not path.exists():
        return

    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def _resolve_path(value: str) -> Path:
    path = Path(value)
    if path.is_absolute():
        return path
    return BASE_DIR / path


def _csv(value: str) -> tuple[str, ...]:
    return tuple(item.strip() for item in value.split(",") if item.strip())


def _bool(value: str) -> bool:
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _env_first(*keys: str, default: str = "") -> str:
    for key in keys:
        value = os.getenv(key)
        if value:
            return value
    return default


@dataclass(frozen=True)
class Settings:
    app_name: str = "shensi-learning-pilot"
    env: str = "local"
    log_level: str = "INFO"
    db_path: Path = field(default_factory=lambda: BASE_DIR / "data" / "shensi.db")
    vault_path: Path = field(default_factory=lambda: BASE_DIR / "vault" / "Shensi-Learning-Vault")
    allowed_parent_ids: tuple[str, ...] = ()
    feishu_app_id: str = ""
    feishu_app_secret: str = ""
    feishu_base_url: str = "https://open.feishu.cn"
    feishu_verification_token: str = ""
    feishu_encrypt_key: str = ""
    feishu_download_resources: bool = True
    feishu_reply_enabled: bool = False
    ai_provider: str = "stub"
    ai_model: str = ""
    timezone: str = "Asia/Shanghai"

    @classmethod
    def load(cls, *, load_dotenv: bool = True) -> "Settings":
        if load_dotenv:
            _load_dotenv(BASE_DIR / ".env")

        return cls(
            env=os.getenv("SHENSI_ENV", "local"),
            log_level=os.getenv("SHENSI_LOG_LEVEL", "INFO"),
            db_path=_resolve_path(os.getenv("SHENSI_DB_PATH", "data/shensi.db")),
            vault_path=_resolve_path(
                os.getenv("SHENSI_VAULT_PATH", "vault/Shensi-Learning-Vault")
            ),
            allowed_parent_ids=_csv(os.getenv("SHENSI_ALLOWED_PARENT_IDS", "")),
            feishu_app_id=_env_first("SHENSI_FEISHU_APP_ID", "FEISHU_APP_ID", "LARK_APP_ID"),
            feishu_app_secret=_env_first(
                "SHENSI_FEISHU_APP_SECRET",
                "FEISHU_APP_SECRET",
                "LARK_APP_SECRET",
            ),
            feishu_base_url=_env_first(
                "SHENSI_FEISHU_BASE_URL",
                "FEISHU_BASE_URL",
                "LARK_BASE_URL",
                default="https://open.feishu.cn",
            ),
            feishu_verification_token=_env_first(
                "SHENSI_FEISHU_VERIFICATION_TOKEN",
                "FEISHU_VERIFICATION_TOKEN",
                "LARK_VERIFICATION_TOKEN",
            ),
            feishu_encrypt_key=_env_first(
                "SHENSI_FEISHU_ENCRYPT_KEY",
                "FEISHU_ENCRYPT_KEY",
                "LARK_ENCRYPT_KEY",
            ),
            feishu_download_resources=_bool(
                os.getenv("SHENSI_FEISHU_DOWNLOAD_RESOURCES", "true")
            ),
            feishu_reply_enabled=_bool(os.getenv("SHENSI_FEISHU_REPLY_ENABLED", "false")),
            ai_provider=os.getenv("SHENSI_AI_PROVIDER", "stub"),
            ai_model=os.getenv("SHENSI_AI_MODEL", ""),
            timezone=os.getenv("SHENSI_TIMEZONE", "Asia/Shanghai"),
        )
