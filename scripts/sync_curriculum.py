from __future__ import annotations

import argparse
from pathlib import Path
import shutil
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.config import BASE_DIR, Settings


DEFAULT_SOURCE_ROOT = BASE_DIR / "knowledge" / "curriculum"


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Sync committed curriculum Markdown cards into the Obsidian vault."
    )
    parser.add_argument(
        "--source",
        type=Path,
        default=DEFAULT_SOURCE_ROOT,
        help="Source curriculum root. Default: knowledge/curriculum.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print planned writes without copying files.",
    )
    parser.add_argument(
        "--delete",
        action="store_true",
        help="Delete target Markdown files that do not exist in the source tree.",
    )
    args = parser.parse_args()

    settings = Settings.load()
    target_root = settings.vault_path / "05-Curriculum"
    result = sync_curriculum(
        source_root=args.source,
        target_root=target_root,
        dry_run=args.dry_run,
        delete=args.delete,
    )
    print(
        f"source={args.source} target={target_root} "
        f"copied={result['copied']} deleted={result['deleted']} skipped={result['skipped']}"
    )


def sync_curriculum(
    *,
    source_root: Path,
    target_root: Path,
    dry_run: bool = False,
    delete: bool = False,
) -> dict[str, int]:
    if not source_root.exists():
        raise SystemExit(f"Source curriculum directory does not exist: {source_root}")

    source_files = _curriculum_files(source_root)
    copied = 0
    skipped = 0
    for source_file in source_files:
        relative = source_file.relative_to(source_root)
        target_file = target_root / relative
        if not _looks_like_curriculum_card(source_file):
            print(f"skip invalid_frontmatter path={source_file}")
            skipped += 1
            continue
        print(f"{'would_copy' if dry_run else 'copy'} {source_file} -> {target_file}")
        if not dry_run:
            target_file.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source_file, target_file)
        copied += 1

    deleted = 0
    if delete:
        source_relatives = {path.relative_to(source_root) for path in source_files}
        for target_file in _curriculum_files(target_root):
            relative = target_file.relative_to(target_root)
            if relative in source_relatives:
                continue
            print(f"{'would_delete' if dry_run else 'delete'} {target_file}")
            if not dry_run:
                target_file.unlink()
            deleted += 1

    return {"copied": copied, "deleted": deleted, "skipped": skipped}


def _curriculum_files(root: Path) -> list[Path]:
    if not root.exists():
        return []
    return sorted(
        path
        for path in root.rglob("*.md")
        if path.is_file() and not path.name.startswith("_") and path.name.lower() != "readme.md"
    )


def _looks_like_curriculum_card(path: Path) -> bool:
    text = path.read_text(encoding="utf-8")
    if not text.startswith("---"):
        return False
    end = text.find("\n---", 3)
    if end == -1:
        return False
    frontmatter = text[3:end].lower()
    return "type: curriculum" in frontmatter


if __name__ == "__main__":
    main()
