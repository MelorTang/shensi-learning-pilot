from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Any


REVIEW_OFFSETS = (1, 3, 7)


class ReviewService:
    def build_reviews(self, *, mistake_id: str, base_date: date, now: str) -> list[dict[str, Any]]:
        reviews: list[dict[str, Any]] = []
        for offset in REVIEW_OFFSETS:
            review_date = base_date + timedelta(days=offset)
            reviews.append(
                {
                    "id": f"{mistake_id}:d+{offset}",
                    "mistake_id": mistake_id,
                    "review_date": review_date.isoformat(),
                    "review_type": f"D+{offset}",
                    "status": "pending",
                    "result": None,
                    "notes": None,
                    "created_at": now,
                    "updated_at": now,
                }
            )
        return reviews

    def parse_date(self, value: str) -> date:
        return datetime.strptime(value, "%Y-%m-%d").date()
