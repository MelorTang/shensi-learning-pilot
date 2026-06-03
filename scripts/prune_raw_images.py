from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.config import Settings


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Prune old Feishu/raw image cache files from the Shensi Obsidian vault."
    )
    parser.add_argument(
        "--days",
        type=int,
        default=90,
        help="Delete raw images older than this many days. Default: 90.",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Actually delete files. Without this flag the script only prints a dry run.",
    )
    args = parser.parse_args()

    if args.days < 1:
        raise SystemExit("--days must be at least 1")

    settings = Settings.load()
    raw_dir = settings.vault_path / "08-Raw-Images"
    cutoff = datetime.now(timezone.utc) - timedelta(days=args.days)
    files = _old_files(raw_dir, cutoff)
    total_bytes = sum(path.stat().st_size for path in files)

    mode = "apply" if args.apply else "dry-run"
    print(f"mode={mode} raw_dir={raw_dir} retention_days={args.days}")
    print(f"matched_files={len(files)} matched_bytes={total_bytes}")

    for path in files:
        age_days = (datetime.now(timezone.utc) - _mtime(path)).days
        print(f"{'delete' if args.apply else 'would_delete'} age_days={age_days} size={path.stat().st_size} path={path}")
        if args.apply:
            path.unlink()


def _old_files(raw_dir: Path, cutoff: datetime) -> list[Path]:
    if not raw_dir.exists():
        return []
    return sorted(
        path
        for path in raw_dir.iterdir()
        if path.is_file() and _mtime(path) < cutoff
    )


def _mtime(path: Path) -> datetime:
    return datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc)


if __name__ == "__main__":
    main()
