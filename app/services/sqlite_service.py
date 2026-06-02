from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any
import json
import sqlite3


SCHEMA_SQL = """
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS mistakes (
  id TEXT PRIMARY KEY,
  subject TEXT NOT NULL,
  grade TEXT NOT NULL,
  date TEXT NOT NULL,
  title TEXT NOT NULL,
  source TEXT,
  image_path TEXT,
  note_path TEXT,
  raw_json_path TEXT,
  severity INTEGER,
  confidence REAL,
  status TEXT NOT NULL,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS concepts (
  id TEXT PRIMARY KEY,
  subject TEXT NOT NULL,
  grade TEXT,
  name TEXT NOT NULL,
  chapter TEXT,
  note_path TEXT,
  status TEXT,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  UNIQUE(subject, grade, name)
);

CREATE TABLE IF NOT EXISTS mistake_concepts (
  mistake_id TEXT NOT NULL,
  concept_id TEXT NOT NULL,
  PRIMARY KEY (mistake_id, concept_id),
  FOREIGN KEY (mistake_id) REFERENCES mistakes(id),
  FOREIGN KEY (concept_id) REFERENCES concepts(id)
);

CREATE TABLE IF NOT EXISTS error_types (
  id TEXT PRIMARY KEY,
  name TEXT NOT NULL UNIQUE,
  description TEXT
);

CREATE TABLE IF NOT EXISTS mistake_error_types (
  mistake_id TEXT NOT NULL,
  error_type_id TEXT NOT NULL,
  PRIMARY KEY (mistake_id, error_type_id),
  FOREIGN KEY (mistake_id) REFERENCES mistakes(id),
  FOREIGN KEY (error_type_id) REFERENCES error_types(id)
);

CREATE TABLE IF NOT EXISTS reviews (
  id TEXT PRIMARY KEY,
  mistake_id TEXT NOT NULL,
  review_date TEXT NOT NULL,
  review_type TEXT,
  status TEXT NOT NULL,
  result TEXT,
  notes TEXT,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  FOREIGN KEY (mistake_id) REFERENCES mistakes(id)
);

CREATE TABLE IF NOT EXISTS reports (
  id TEXT PRIMARY KEY,
  report_type TEXT NOT NULL,
  date TEXT NOT NULL,
  start_date TEXT,
  end_date TEXT,
  note_path TEXT,
  summary TEXT,
  created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS feishu_messages (
  message_id TEXT PRIMARY KEY,
  chat_id TEXT,
  sender_id TEXT,
  message_type TEXT,
  raw_payload_path TEXT,
  processed_status TEXT,
  created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS ai_runs (
  id TEXT PRIMARY KEY,
  mistake_id TEXT,
  model_name TEXT,
  prompt_version TEXT,
  input_path TEXT,
  output_json_path TEXT,
  confidence REAL,
  created_at TEXT NOT NULL,
  FOREIGN KEY (mistake_id) REFERENCES mistakes(id)
);

CREATE TABLE IF NOT EXISTS parent_confirmations (
  id TEXT PRIMARY KEY,
  mistake_id TEXT,
  message_id TEXT,
  action TEXT NOT NULL,
  before_json_path TEXT,
  after_json_path TEXT,
  confirmed_by TEXT,
  confirmed_at TEXT NOT NULL,
  FOREIGN KEY (mistake_id) REFERENCES mistakes(id),
  FOREIGN KEY (message_id) REFERENCES feishu_messages(message_id)
);
"""


ERROR_TYPES = (
    ("concept_unclear", "concept unclear", "Definition or boundary is not stable."),
    ("missed_condition", "missed condition", "Skipped a condition while reading the problem."),
    ("method_missing", "method missing", "Does not know which method or model to use."),
    ("calculation_error", "calculation error", "Arithmetic, sign, or simplification error."),
    ("memory_weak", "memory weak", "Formula, word, definition, or text memory is weak."),
    ("expression_irregular", "expression irregular", "Process, unit, format, or wording is irregular."),
    ("step_skipped", "step skipped", "Skipped an intermediate reasoning step."),
    ("attention_careless", "attention careless", "Low-level careless error."),
    ("transfer_difficulty", "transfer difficulty", "Cannot transfer basics to a new problem form."),
    ("time_management", "time management", "Time allocation caused the mistake."),
)


class SQLiteService:
    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path

    def connect(self) -> sqlite3.Connection:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

    def initialize(self) -> None:
        with self.connect() as conn:
            conn.executescript(SCHEMA_SQL)
            conn.executemany(
                """
                INSERT INTO error_types (id, name, description)
                VALUES (?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                  name = excluded.name,
                  description = excluded.description
                """,
                ERROR_TYPES,
            )

    def health_check(self) -> bool:
        if not self.db_path.exists():
            return False

        with self.connect() as conn:
            row = conn.execute("SELECT COUNT(*) FROM error_types").fetchone()
            return bool(row and row[0] >= len(ERROR_TYPES))

    def upsert_feishu_message(
        self,
        *,
        message_id: str,
        chat_id: str | None,
        sender_id: str | None,
        message_type: str,
        raw_payload_path: str,
        status: str,
        created_at: str,
    ) -> bool:
        with self.connect() as conn:
            cursor = conn.execute(
                """
                INSERT INTO feishu_messages (
                  message_id, chat_id, sender_id, message_type,
                  raw_payload_path, processed_status, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(message_id) DO NOTHING
                """,
                (message_id, chat_id, sender_id, message_type, raw_payload_path, status, created_at),
            )
            return cursor.rowcount == 1

    def update_message_status(self, message_id: str, status: str) -> None:
        with self.connect() as conn:
            conn.execute(
                "UPDATE feishu_messages SET processed_status = ? WHERE message_id = ?",
                (status, message_id),
            )

    def get_message(self, message_id: str) -> dict[str, Any] | None:
        with self.connect() as conn:
            row = conn.execute(
                "SELECT * FROM feishu_messages WHERE message_id = ?",
                (message_id,),
            ).fetchone()
            return dict(row) if row else None

    def upsert_mistake(self, mistake: dict[str, Any]) -> None:
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO mistakes (
                  id, subject, grade, date, title, source, image_path, note_path,
                  raw_json_path, severity, confidence, status, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                  subject = excluded.subject,
                  grade = excluded.grade,
                  date = excluded.date,
                  title = excluded.title,
                  source = excluded.source,
                  image_path = excluded.image_path,
                  note_path = excluded.note_path,
                  raw_json_path = excluded.raw_json_path,
                  severity = excluded.severity,
                  confidence = excluded.confidence,
                  status = excluded.status,
                  updated_at = excluded.updated_at
                """,
                (
                    mistake["id"],
                    mistake["subject"],
                    mistake["grade"],
                    mistake["date"],
                    mistake["title"],
                    mistake.get("source"),
                    mistake.get("image_path"),
                    mistake.get("note_path"),
                    mistake.get("raw_json_path"),
                    mistake.get("severity"),
                    mistake.get("confidence"),
                    mistake["status"],
                    mistake["created_at"],
                    mistake["updated_at"],
                ),
            )

    def get_mistake(self, mistake_id: str) -> dict[str, Any] | None:
        with self.connect() as conn:
            row = conn.execute("SELECT * FROM mistakes WHERE id = ?", (mistake_id,)).fetchone()
            return dict(row) if row else None

    def list_mistakes(
        self,
        *,
        status: str | None = None,
        days: int | None = None,
    ) -> list[dict[str, Any]]:
        clauses: list[str] = []
        params: list[Any] = []
        if status:
            clauses.append("status = ?")
            params.append(status)
        if days is not None:
            clauses.append("date >= date('now', ?)")
            params.append(f"-{days} days")
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        with self.connect() as conn:
            rows = conn.execute(
                f"SELECT * FROM mistakes {where} ORDER BY date DESC, created_at DESC",
                params,
            ).fetchall()
            return [dict(row) for row in rows]

    def upsert_ai_run(self, run: dict[str, Any]) -> None:
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO ai_runs (
                  id, mistake_id, model_name, prompt_version,
                  input_path, output_json_path, confidence, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                  model_name = excluded.model_name,
                  prompt_version = excluded.prompt_version,
                  input_path = excluded.input_path,
                  output_json_path = excluded.output_json_path,
                  confidence = excluded.confidence
                """,
                (
                    run["id"],
                    run["mistake_id"],
                    run["model_name"],
                    run["prompt_version"],
                    run["input_path"],
                    run["output_json_path"],
                    run["confidence"],
                    run["created_at"],
                ),
            )

    def upsert_concept(self, concept: dict[str, Any]) -> None:
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO concepts (
                  id, subject, grade, name, chapter, note_path, status, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(subject, grade, name) DO UPDATE SET
                  chapter = excluded.chapter,
                  note_path = excluded.note_path,
                  status = excluded.status,
                  updated_at = excluded.updated_at
                """,
                (
                    concept["id"],
                    concept["subject"],
                    concept.get("grade"),
                    concept["name"],
                    concept.get("chapter"),
                    concept.get("note_path"),
                    concept.get("status"),
                    concept["created_at"],
                    concept["updated_at"],
                ),
            )

    def link_mistake_concept(self, mistake_id: str, concept_id: str) -> None:
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO mistake_concepts (mistake_id, concept_id)
                VALUES (?, ?)
                ON CONFLICT(mistake_id, concept_id) DO NOTHING
                """,
                (mistake_id, concept_id),
            )

    def link_mistake_error_type(self, mistake_id: str, error_type_id: str) -> None:
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO mistake_error_types (mistake_id, error_type_id)
                VALUES (?, ?)
                ON CONFLICT(mistake_id, error_type_id) DO NOTHING
                """,
                (mistake_id, error_type_id),
            )

    def upsert_review(self, review: dict[str, Any]) -> None:
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO reviews (
                  id, mistake_id, review_date, review_type, status,
                  result, notes, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                  review_date = excluded.review_date,
                  review_type = excluded.review_type,
                  status = excluded.status,
                  result = excluded.result,
                  notes = excluded.notes,
                  updated_at = excluded.updated_at
                """,
                (
                    review["id"],
                    review["mistake_id"],
                    review["review_date"],
                    review["review_type"],
                    review["status"],
                    review.get("result"),
                    review.get("notes"),
                    review["created_at"],
                    review["updated_at"],
                ),
            )

    def list_reviews(
        self,
        *,
        review_date: str | None = None,
        status: str | None = None,
    ) -> list[dict[str, Any]]:
        clauses: list[str] = []
        params: list[Any] = []
        if review_date:
            clauses.append("review_date = ?")
            params.append(review_date)
        if status:
            clauses.append("reviews.status = ?")
            params.append(status)
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        with self.connect() as conn:
            rows = conn.execute(
                f"""
                SELECT reviews.*, mistakes.title, mistakes.subject, mistakes.note_path
                FROM reviews
                JOIN mistakes ON mistakes.id = reviews.mistake_id
                {where}
                ORDER BY review_date ASC
                """,
                params,
            ).fetchall()
            return [dict(row) for row in rows]

    def upsert_report(self, report: dict[str, Any]) -> None:
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO reports (
                  id, report_type, date, start_date, end_date, note_path, summary, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                  note_path = excluded.note_path,
                  summary = excluded.summary,
                  start_date = excluded.start_date,
                  end_date = excluded.end_date
                """,
                (
                    report["id"],
                    report["report_type"],
                    report["date"],
                    report.get("start_date"),
                    report.get("end_date"),
                    report.get("note_path"),
                    report.get("summary"),
                    report["created_at"],
                ),
            )

    def list_reports(self, report_type: str | None = None) -> list[dict[str, Any]]:
        params: list[Any] = []
        where = ""
        if report_type:
            where = "WHERE report_type = ?"
            params.append(report_type)
        with self.connect() as conn:
            rows = conn.execute(f"SELECT * FROM reports {where} ORDER BY date DESC", params).fetchall()
            return [dict(row) for row in rows]

    def upsert_parent_confirmation(self, confirmation: dict[str, Any]) -> None:
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO parent_confirmations (
                  id, mistake_id, message_id, action, before_json_path,
                  after_json_path, confirmed_by, confirmed_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                  action = excluded.action,
                  after_json_path = excluded.after_json_path,
                  confirmed_by = excluded.confirmed_by,
                  confirmed_at = excluded.confirmed_at
                """,
                (
                    confirmation["id"],
                    confirmation.get("mistake_id"),
                    confirmation.get("message_id"),
                    confirmation["action"],
                    confirmation.get("before_json_path"),
                    confirmation.get("after_json_path"),
                    confirmation.get("confirmed_by"),
                    confirmation["confirmed_at"],
                ),
            )

    def table_counts(self) -> dict[str, int]:
        tables = ("mistakes", "concepts", "reviews", "reports", "feishu_messages", "ai_runs")
        with self.connect() as conn:
            return {
                table: int(conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])
                for table in tables
            }

    def concept_mistakes(self, concept_name: str) -> list[dict[str, Any]]:
        with self.connect() as conn:
            rows = conn.execute(
                """
                SELECT mistakes.*
                FROM mistakes
                JOIN mistake_concepts ON mistake_concepts.mistake_id = mistakes.id
                JOIN concepts ON concepts.id = mistake_concepts.concept_id
                WHERE concepts.name = ?
                ORDER BY mistakes.date DESC
                """,
                (concept_name,),
            ).fetchall()
            return [dict(row) for row in rows]

    def stats(self, days: int = 14) -> dict[str, Any]:
        with self.connect() as conn:
            mistakes = conn.execute(
                """
                SELECT subject, COUNT(*) AS count
                FROM mistakes
                WHERE status = 'confirmed' AND date >= date('now', ?)
                GROUP BY subject
                """,
                (f"-{days} days",),
            ).fetchall()
            error_types = conn.execute(
                """
                SELECT error_types.id, error_types.name, COUNT(*) AS count
                FROM mistake_error_types
                JOIN error_types ON error_types.id = mistake_error_types.error_type_id
                JOIN mistakes ON mistakes.id = mistake_error_types.mistake_id
                WHERE mistakes.status = 'confirmed' AND mistakes.date >= date('now', ?)
                GROUP BY error_types.id, error_types.name
                ORDER BY count DESC
                """,
                (f"-{days} days",),
            ).fetchall()
            concepts = conn.execute(
                """
                SELECT concepts.name, COUNT(*) AS count
                FROM mistake_concepts
                JOIN concepts ON concepts.id = mistake_concepts.concept_id
                JOIN mistakes ON mistakes.id = mistake_concepts.mistake_id
                WHERE mistakes.status = 'confirmed' AND mistakes.date >= date('now', ?)
                GROUP BY concepts.name
                ORDER BY count DESC
                """,
                (f"-{days} days",),
            ).fetchall()
            return {
                "days": days,
                "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                "mistakes_by_subject": [dict(row) for row in mistakes],
                "error_types": [dict(row) for row in error_types],
                "weak_concepts": [dict(row) for row in concepts],
            }

    def read_json_file(self, path: str | None) -> dict[str, Any]:
        if not path:
            return {}
        file_path = Path(path)
        if not file_path.exists():
            return {}
        return json.loads(file_path.read_text(encoding="utf-8"))
