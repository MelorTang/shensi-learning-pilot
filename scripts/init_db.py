from __future__ import annotations

from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.bootstrap import initialize_storage
from app.config import Settings


def main() -> None:
    status = initialize_storage(Settings.load())
    print(f"database_ready={status.database_ready} path={status.db_path}")
    print(f"vault_ready={status.vault_ready} path={status.vault_path}")


if __name__ == "__main__":
    main()
