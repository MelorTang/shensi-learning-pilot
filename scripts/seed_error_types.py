from __future__ import annotations

from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.config import Settings
from app.services.sqlite_service import SQLiteService


def main() -> None:
    service = SQLiteService(Settings.load().db_path)
    service.initialize()
    print("error_types_seeded=true")


if __name__ == "__main__":
    main()
