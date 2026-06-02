from __future__ import annotations

from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.config import Settings
from app.models.schemas import LocalUploadRequest
from app.services.workflow_service import MistakeWorkflowService


def main() -> None:
    root = Path(__file__).resolve().parent.parent
    sample_image = root / "examples" / "sample_mistake.svg"
    workflow = MistakeWorkflowService(Settings.load())
    result = workflow.submit_local(
        LocalUploadRequest(
            message_id="local-demo-001",
            local_image_path=str(sample_image),
            subject="math",
            grade="grade7",
            note="Local demo: equation transform mistake.",
            auto_confirm=True,
        )
    )
    print(f"status={result['status']} mistake_id={result['mistake_id']}")
    confirmation = result.get("confirmation") or {}
    print(f"confirmation_status={confirmation.get('status')}")
    print(f"mistake_note={confirmation.get('note_path')}")
    print(f"review_count={len(confirmation.get('reviews', []))}")
    print(f"daily_report={confirmation.get('daily_report', {}).get('note_path')}")
    print(f"weekly_report={confirmation.get('weekly_report', {}).get('note_path')}")


if __name__ == "__main__":
    main()
