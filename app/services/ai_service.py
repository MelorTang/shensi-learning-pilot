from __future__ import annotations

from pathlib import Path
from typing import Any
import hashlib


PROMPT_VERSION = "mistake-analysis-v0.1-stub"


class AIService:
    """AI provider boundary.

    The MVP uses a deterministic stub so the full local loop works without real
    model credentials. A real provider can later implement this same method.
    """

    def __init__(self, provider: str = "stub", model: str = "") -> None:
        self.provider = provider or "stub"
        self.model = model or "stub-mistake-analyzer"

    def analyze_mistake(
        self,
        *,
        mistake_id: str,
        image_path: Path,
        subject: str,
        grade: str,
        note: str,
        today: str,
    ) -> dict[str, Any]:
        if self.provider != "stub":
            raise NotImplementedError(
                "Only the stub AI provider is implemented in the MVP. "
                "Set SHENSI_AI_PROVIDER=stub to run locally."
            )

        fingerprint = hashlib.sha256(f"{mistake_id}:{image_path.name}:{note}".encode()).hexdigest()
        severity = 2 + (int(fingerprint[0], 16) % 3)
        if subject.lower() in {"english", "英语"}:
            title = "Vocabulary usage and sentence correction"
            concepts = ["vocabulary in context", "sentence correction"]
            error_types = ["memory_weak", "expression_irregular"]
            question = "Choose the correct word form and rewrite the sentence."
            student_answer = "Uses the base word form without checking tense."
            correct_answer = "Use the word form that matches tense and grammar."
        elif subject.lower() in {"chinese", "语文"}:
            title = "Reading comprehension evidence selection"
            concepts = ["reading evidence", "text inference"]
            error_types = ["missed_condition", "expression_irregular"]
            question = "Find evidence from the passage and explain the reason."
            student_answer = "Gives a conclusion but misses textual evidence."
            correct_answer = "Quote the key sentence, then explain the inference."
        else:
            title = "Linear equation transformation"
            concepts = ["linear equation", "inverse operation"]
            error_types = ["calculation_error", "step_skipped"]
            question = "Solve the equation: 2x + 5 = 17."
            student_answer = "x = 5"
            correct_answer = "x = 6"

        return {
            "schema_version": "0.1",
            "provider": self.provider,
            "model": self.model,
            "prompt_version": PROMPT_VERSION,
            "mistake_id": mistake_id,
            "subject": subject,
            "grade": grade,
            "date": today,
            "title": title,
            "question_text": question,
            "student_answer": student_answer,
            "correct_answer": correct_answer,
            "concepts": concepts,
            "error_types": error_types,
            "root_cause": "The student skipped one stable intermediate step before calculating.",
            "severity": severity,
            "confidence": 0.86,
            "status": "waiting_confirmation",
            "parent_guidance": "Ask the child to say the inverse operation out loud before writing the next line.",
            "image_path": str(image_path),
            "note": note,
        }
