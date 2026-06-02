from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Any

from app.services.obsidian_service import ObsidianService
from app.services.sqlite_service import SQLiteService


class ReportService:
    def __init__(self, sqlite: SQLiteService, obsidian: ObsidianService) -> None:
        self.sqlite = sqlite
        self.obsidian = obsidian

    def generate_daily(self, report_date: date, now: str) -> dict[str, Any]:
        date_text = report_date.isoformat()
        markdown, summary = self._daily_markdown(report_date)
        path = self.obsidian.write_daily_report(date_text, markdown)
        report = {
            "id": f"daily:{date_text}",
            "report_type": "daily",
            "date": date_text,
            "start_date": date_text,
            "end_date": date_text,
            "note_path": str(path),
            "summary": summary,
            "created_at": now,
        }
        self.sqlite.upsert_report(report)
        return report | {"markdown": markdown}

    def generate_weekly(self, anchor_date: date, now: str) -> dict[str, Any]:
        start = anchor_date - timedelta(days=anchor_date.weekday())
        week_label = f"{start.isocalendar().year}-W{start.isocalendar().week:02d}"
        end = start + timedelta(days=6)
        markdown, summary = self._weekly_markdown(anchor_date)
        path = self.obsidian.write_weekly_report(week_label, markdown)
        report = {
            "id": f"weekly:{week_label}",
            "report_type": "weekly",
            "date": anchor_date.isoformat(),
            "start_date": start.isoformat(),
            "end_date": end.isoformat(),
            "note_path": str(path),
            "summary": summary,
            "created_at": now,
        }
        self.sqlite.upsert_report(report)
        return report | {"markdown": markdown}

    def draft(self, report_type: str, anchor_date: date, now: str) -> dict[str, Any]:
        if report_type == "daily":
            markdown, summary = self._daily_markdown(anchor_date)
            return {
                "id": f"draft:daily:{anchor_date.isoformat()}",
                "report_type": "daily",
                "date": anchor_date.isoformat(),
                "summary": summary,
                "markdown": markdown,
                "created_at": now,
                "draft": True,
            }
        if report_type == "weekly":
            start = anchor_date - timedelta(days=anchor_date.weekday())
            week_label = f"{start.isocalendar().year}-W{start.isocalendar().week:02d}"
            markdown, summary = self._weekly_markdown(anchor_date)
            return {
                "id": f"draft:weekly:{week_label}",
                "report_type": "weekly",
                "date": anchor_date.isoformat(),
                "summary": summary,
                "markdown": markdown,
                "created_at": now,
                "draft": True,
            }
        raise ValueError(f"Unsupported report type: {report_type}")

    def parse_date(self, value: str | None) -> date:
        if not value:
            return date.today()
        return datetime.strptime(value, "%Y-%m-%d").date()

    def _mistake_lines(self, mistakes: list[dict[str, Any]]) -> str:
        return "\n".join(f"- {item['title']} ({item['subject']})" for item in mistakes) or "- None."

    def _rank_lines(self, rows: list[dict[str, Any]], label_key: str) -> str:
        return "\n".join(
            f"{index}. {row[label_key]}: {row['count']}"
            for index, row in enumerate(rows, start=1)
        ) or "No data yet."

    def _daily_markdown(self, report_date: date) -> tuple[str, str]:
        date_text = report_date.isoformat()
        mistakes = [
            item for item in self.sqlite.list_mistakes(status="confirmed") if item["date"] == date_text
        ]
        tomorrow = (report_date + timedelta(days=1)).isoformat()
        reviews = self.sqlite.list_reviews(review_date=tomorrow, status="pending")
        subjects = sorted({item["subject"] for item in mistakes}) or ["none"]
        checklist = "\n".join(
            f"- {item['review_type']}: {item['title']} ({item['subject']})" for item in reviews
        ) or "- No scheduled review tomorrow."
        markdown = f"""# Shensi Daily Report | {date_text}

## Overview

- New confirmed mistakes: {len(mistakes)}
- Reviews due tomorrow: {len(reviews)}
- Main subjects: {", ".join(subjects)}

## Today Mistakes

{self._mistake_lines(mistakes)}

## Tomorrow Checklist

{checklist}

## Parent Prompt

Pick one mistake and ask the child to explain the first skipped step.
"""
        return markdown, f"{len(mistakes)} new mistakes, {len(reviews)} reviews due tomorrow."

    def _weekly_markdown(self, anchor_date: date) -> tuple[str, str]:
        start = anchor_date - timedelta(days=anchor_date.weekday())
        end = start + timedelta(days=6)
        mistakes = [
            item
            for item in self.sqlite.list_mistakes(status="confirmed")
            if start.isoformat() <= item["date"] <= end.isoformat()
        ]
        stats = self.sqlite.stats(days=14)
        weak_concepts = stats["weak_concepts"][:5]
        error_types = stats["error_types"][:5]
        week_label = f"{start.isocalendar().year}-W{start.isocalendar().week:02d}"
        markdown = f"""# Shensi Weekly Report | {week_label}

## Conclusion

This week has {len(mistakes)} confirmed mistake(s). Keep the review loop small and explicit.

## Frequent Error Types

{self._rank_lines(error_types, "name")}

## Weak Concepts

{self._rank_lines(weak_concepts, "name")}

## Next Week Priorities

- Re-solve the D+1/D+3/D+7 review items before adding extra practice.
- Ask for one spoken explanation before checking the answer.
- Keep each review session under 30 minutes.
"""
        return markdown, f"{len(mistakes)} confirmed mistakes in {week_label}."
