from __future__ import annotations

import argparse
from pathlib import Path
import shutil
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.bootstrap import initialize_storage
from app.config import Settings


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Remove local Shensi SQLite/vault data and initialize empty storage."
    )
    parser.add_argument(
        "--yes",
        action="store_true",
        help="Required safety flag. Without it no files are removed.",
    )
    parser.add_argument(
        "--keep-vault",
        action="store_true",
        help="Only remove SQLite files, keeping the Obsidian vault.",
    )
    args = parser.parse_args()

    settings = Settings.load()
    targets = _targets(settings, keep_vault=args.keep_vault)
    print("The following paths will be reset:")
    for path in targets:
        print(path)

    if not args.yes:
        raise SystemExit("Refusing to reset storage without --yes")

    for path in targets:
        if path.is_dir():
            shutil.rmtree(path)
        elif path.exists():
            path.unlink()

    status = initialize_storage(settings)
    print(f"database_ready={status.database_ready} path={status.db_path}")
    print(f"vault_ready={status.vault_ready} path={status.vault_path}")


def _targets(settings: Settings, *, keep_vault: bool) -> list[Path]:
    db_path = settings.db_path
    targets = [
        db_path,
        db_path.with_name(f"{db_path.name}-shm"),
        db_path.with_name(f"{db_path.name}-wal"),
    ]
    if not keep_vault:
        targets.append(settings.vault_path)
    return targets


if __name__ == "__main__":
    main()
