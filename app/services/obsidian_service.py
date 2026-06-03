from __future__ import annotations

from typing import Any
import json
from pathlib import Path
import shutil


VAULT_DIRECTORIES = (
    "00-Dashboard",
    "01-Daily",
    "02-Mistakes/数学",
    "02-Mistakes/英语",
    "02-Mistakes/语文",
    "03-Concepts/数学",
    "03-Concepts/英语",
    "03-Concepts/语文",
    "04-Reports/Daily",
    "04-Reports/Weekly",
    "05-Curriculum/数学",
    "05-Curriculum/英语",
    "05-Curriculum/语文",
    "06-Methods/数学",
    "06-Methods/英语",
    "06-Methods/语文",
    "07-Parent-QA",
    "08-Raw-Images",
    "09-AI-Raw-JSON",
    "99-System/prompts",
    "99-System/templates",
)

SUBJECT_DIR_NAMES = {
    "math": "数学",
    "mathematics": "数学",
    "数学": "数学",
    "english": "英语",
    "英语": "英语",
    "chinese": "语文",
    "语文": "语文",
}

CURRICULUM_PROFILES = {
    "一元一次方程": {
        "definition": "只含一个未知数，且未知数最高次数为 1 的方程。",
        "steps": ["去分母", "去括号", "移项", "合并同类项", "系数化为 1"],
        "pitfalls": ["移项后符号忘记改变", "去括号时漏乘括号内某一项", "等式两边没有做同样的运算"],
        "parent_guidance": "让孩子每一步都说出“我对等式两边做了什么”，先保证等式变形合法。",
    },
    "一次函数求值": {
        "definition": "把给定的 x 代入 y = kx + b，并按运算顺序求出 y。",
        "steps": ["确认 x 的值", "整体代入表达式", "先乘除后加减", "负数代入时加括号"],
        "pitfalls": ["负数代入漏括号", "把 -3x 看成 -3+x", "先加减后乘除"],
        "parent_guidance": "让孩子先口头复述“代入、乘法、加减”三步，再动笔计算。",
    },
    "二元一次方程组": {
        "definition": "含两个未知数，且每个方程都是一次方程的方程组。",
        "steps": ["选择代入法或加减消元法", "消去一个未知数", "求出第一个未知数", "回代求另一个未知数", "代回原方程验算"],
        "pitfalls": ["加减消元时符号处理错误", "回代时抄错数", "只求出一个未知数就停止"],
        "parent_guidance": "引导孩子在最后把 x、y 同时代回两个原方程，检查左右是否相等。",
    },
    "斜率公式": {
        "definition": "两点 A(x1,y1)、B(x2,y2) 的直线斜率 k = (y2-y1)/(x2-x1)。",
        "steps": ["标出两个点的 x、y", "写出 y 的差", "写出 x 的差", "保持同一方向相减", "化简结果"],
        "pitfalls": ["分子分母顺序不一致", "把 x 差和 y 差写反", "负号处理错误"],
        "parent_guidance": "让孩子在草稿纸上先标出 x1、y1、x2、y2，再代公式。",
    },
    "去括号": {
        "definition": "根据乘法分配律把括号外的因数乘到括号内每一项。",
        "steps": ["看清括号前的符号和系数", "把系数乘给括号内每一项", "括号前是负号时每一项都变号", "再合并同类项"],
        "pitfalls": ["只乘第一项", "括号前负号只改了一项", "漏写常数项"],
        "parent_guidance": "让孩子用箭头标出括号外的数分别乘向括号内每一项。",
    },
    "移项": {
        "definition": "把等式一边的项移到另一边，移动后该项符号改变。",
        "steps": ["确定要移动的项", "跨过等号改变符号", "同类项放在同一边", "合并同类项"],
        "pitfalls": ["跨等号不变号", "把乘除运算误当成移项", "漏移常数项"],
        "parent_guidance": "提醒孩子只要“跨过等号”，加减号就要反过来。",
    },
}


class ObsidianService:
    def __init__(self, vault_path: Path) -> None:
        self.vault_path = vault_path

    def initialize_vault(self) -> None:
        for directory in VAULT_DIRECTORIES:
            (self.vault_path / directory).mkdir(parents=True, exist_ok=True)

        config_path = self.vault_path / "99-System" / "config.yaml"
        if not config_path.exists():
            config_path.write_text(
                "name: Shensi Learning Vault\nversion: 0.1\n",
                encoding="utf-8",
            )

    def health_check(self) -> bool:
        required = (
            self.vault_path / "00-Dashboard",
            self.vault_path / "08-Raw-Images",
            self.vault_path / "09-AI-Raw-JSON",
            self.vault_path / "99-System" / "config.yaml",
        )
        return all(path.exists() for path in required)

    def save_raw_payload(self, message_id: str, payload: dict[str, Any]) -> Path:
        path = self.vault_path / "09-AI-Raw-JSON" / "raw_payloads" / f"{message_id}.json"
        return self.write_json(path, payload)

    def save_ai_output(self, mistake_id: str, output: dict[str, Any]) -> Path:
        path = self.vault_path / "09-AI-Raw-JSON" / "ai_outputs" / f"{mistake_id}.json"
        return self.write_json(path, output)

    def save_confirmation_json(self, mistake_id: str, output: dict[str, Any]) -> Path:
        path = self.vault_path / "09-AI-Raw-JSON" / "confirmations" / f"{mistake_id}.json"
        return self.write_json(path, output)

    def write_json(self, path: Path, data: dict[str, Any]) -> Path:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True),
            encoding="utf-8",
        )
        return path

    def save_local_image(self, message_id: str, source_path: str | None) -> Path:
        raw_dir = self.vault_path / "08-Raw-Images"
        raw_dir.mkdir(parents=True, exist_ok=True)
        if source_path:
            source = Path(source_path)
            if source.exists() and source.is_file():
                suffix = source.suffix or ".img"
                target = raw_dir / f"{message_id}{suffix}"
                if not target.exists() or target.stat().st_size != source.stat().st_size:
                    shutil.copyfile(source, target)
                return target

        target = raw_dir / f"{message_id}.svg"
        if not target.exists():
            target.write_text(
                """<svg xmlns="http://www.w3.org/2000/svg" width="900" height="520" viewBox="0 0 900 520">
  <rect width="900" height="520" fill="#fbfaf7"/>
  <rect x="56" y="54" width="788" height="412" rx="18" fill="#ffffff" stroke="#222222" stroke-width="3"/>
  <text x="96" y="130" font-family="Arial, sans-serif" font-size="34" fill="#202020">Shensi local sample mistake</text>
  <text x="96" y="205" font-family="Arial, sans-serif" font-size="30" fill="#202020">Solve: 2x + 5 = 17</text>
  <text x="96" y="275" font-family="Arial, sans-serif" font-size="30" fill="#b42318">Student answer: x = 5</text>
  <text x="96" y="345" font-family="Arial, sans-serif" font-size="30" fill="#116329">Correct answer: x = 6</text>
  <text x="96" y="415" font-family="Arial, sans-serif" font-size="24" fill="#555555">Generated because no local image path was provided.</text>
</svg>
""",
                encoding="utf-8",
            )
        return target

    def save_image_bytes(self, message_id: str, data: bytes, suffix: str = ".jpg") -> Path:
        raw_dir = self.vault_path / "08-Raw-Images"
        raw_dir.mkdir(parents=True, exist_ok=True)
        clean_suffix = suffix if suffix.startswith(".") else f".{suffix}"
        target = raw_dir / f"{message_id}{clean_suffix}"
        if not target.exists() or target.read_bytes() != data:
            target.write_bytes(data)
        return target

    def write_mistake_note(self, analysis: dict[str, Any]) -> Path:
        subject = str(analysis.get("subject", "math"))
        mistake_id = str(analysis["mistake_id"])
        safe_subject = self._subject_dir(subject)
        title = self._safe_name(str(analysis.get("title") or mistake_id))
        path = self.vault_path / "02-Mistakes" / safe_subject / f"{analysis['date']}-{title}-{mistake_id}.md"
        image_file = Path(str(analysis.get("image_path", ""))).name
        concepts = ", ".join(analysis.get("concepts", [])) or "pending"
        error_types = ", ".join(analysis.get("error_types", [])) or "pending"
        question_items = self._format_question_items(analysis.get("question_items", []))
        question_section = question_items or str(analysis.get("question_text", ""))
        content = f"""---
type: mistake
mistake_id: "{mistake_id}"
grade: "{analysis.get("grade", "")}"
subject: "{subject}"
date: "{analysis.get("date", "")}"
status: confirmed
---

# {analysis.get("title", mistake_id)}

## Original Image

![[{image_file}]]

## AI Recognized Question

{question_section}

## Student Answer

{analysis.get("student_answer", "")}

## Correct Answer

{analysis.get("correct_answer", "")}

## Concepts

{concepts}

## Error Types

{error_types}

## Root Cause

{analysis.get("root_cause", "")}

## Parent Guidance

{analysis.get("parent_guidance", "")}
"""
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        return path

    def _format_question_items(self, items: Any) -> str:
        if not isinstance(items, list) or not items:
            return ""

        sections: list[str] = []
        for index, item in enumerate(items, start=1):
            if not isinstance(item, dict):
                sections.append(f"### Question {index}\n\n{item}")
                continue

            question = item.get("question") or item.get("title") or f"Question {index}"
            student_steps = self._format_steps(item.get("student_steps") or item.get("steps"))
            student_answer = item.get("student_answer") or item.get("answer") or ""
            correct_answer = item.get("correct_answer") or ""
            is_correct = item.get("is_correct")
            if is_correct is None:
                is_correct = item.get("verdict")
            error_reason = item.get("error_reason") or item.get("reason") or item.get("mistake_reason") or ""
            concept = item.get("concept") or item.get("knowledge_point") or ""
            error_type = item.get("error_type") or item.get("error_types") or ""
            verification = self._format_verification(item.get("verification"))
            review_status = self._format_parent_review(item)

            sections.append(
                "\n".join(
                    [
                        f"### Question {index}: {question}",
                        "",
                        f"- Result: {self._format_verdict(is_correct)}",
                        f"- Student answer: {student_answer or 'Not provided'}",
                        f"- Correct answer: {correct_answer or 'Not provided'}",
                        f"- Concept: {concept or 'Not provided'}",
                        f"- Error type: {self._format_inline(error_type) or 'Not provided'}",
                        f"- Error reason: {error_reason or 'Not provided'}",
                        f"- Verification: {verification}",
                        f"- Parent review: {review_status}",
                        "",
                        "Student steps:",
                        "",
                        student_steps or "Not provided",
                    ]
                )
            )
        return "\n\n".join(sections)

    def _format_parent_review(self, item: dict[str, Any]) -> str:
        if not item.get("needs_parent_review"):
            return "not required"
        reason = item.get("review_reason")
        return f"required ({reason})" if reason else "required"

    def _format_verification(self, value: Any) -> str:
        if not isinstance(value, dict):
            return "not run"
        status = value.get("status") or "unknown"
        method = value.get("method")
        result = value.get("is_correct")
        pieces = [str(status)]
        if method:
            pieces.append(str(method))
        if isinstance(result, bool):
            pieces.append("correct" if result else "wrong")
        if value.get("conflict_with_llm"):
            pieces.append("overrode LLM verdict")
        reason = value.get("reason")
        if reason:
            pieces.append(str(reason))
        return " | ".join(pieces)

    def _format_steps(self, value: Any) -> str:
        if isinstance(value, list):
            return "\n".join(f"{index}. {step}" for index, step in enumerate(value, start=1))
        if isinstance(value, dict):
            return json.dumps(value, ensure_ascii=False, indent=2)
        if value is None:
            return ""
        return str(value)

    def _format_verdict(self, value: Any) -> str:
        if isinstance(value, bool):
            return "correct" if value else "wrong"
        if value is None or value == "":
            return "unknown"
        return str(value)

    def _format_inline(self, value: Any) -> str:
        if isinstance(value, list):
            return ", ".join(str(item) for item in value)
        if value is None:
            return ""
        return str(value)

    def concept_note_path(self, concept: dict[str, Any]) -> Path:
        subject = self._subject_dir(str(concept.get("subject", "math")))
        name = str(concept["name"])
        return self.vault_path / "03-Concepts" / subject / f"{self._safe_name(name)}.md"

    def curriculum_note_path(self, concept: dict[str, Any]) -> Path:
        subject = self._subject_dir(str(concept.get("subject", "math")))
        name = str(concept["name"])
        return self.vault_path / "05-Curriculum" / subject / f"{self._safe_name(name)}.md"

    def write_concept_note(
        self,
        concept: dict[str, Any],
        *,
        related_mistakes: list[dict[str, Any]] | None = None,
        analysis: dict[str, Any] | None = None,
    ) -> Path:
        name = str(concept["name"])
        path = self.concept_note_path(concept)
        related_mistakes = related_mistakes or []
        curriculum_link = self.curriculum_note_path(concept).stem
        error_types = ", ".join((analysis or {}).get("error_types", [])) or "待积累"
        root_cause = (analysis or {}).get("root_cause") or "待从更多错题中归纳。"
        parent_guidance = (analysis or {}).get("parent_guidance") or "待从更多错题中归纳。"
        content = f"""---
type: concept
subject: "{concept.get("subject", "")}"
grade: "{concept.get("grade", "")}"
status: "{concept.get("status", "active")}"
---

# {name}

## Static Knowledge

[[{curriculum_link}]]

## Mistake Pattern

{root_cause}

## Common Error Types

{error_types}

## Parent Guidance

{parent_guidance}

## Related Mistakes

{self._format_related_mistakes(related_mistakes)}
"""
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        return path

    def write_curriculum_note(self, concept: dict[str, Any]) -> Path:
        name = str(concept["name"])
        path = self.curriculum_note_path(concept)
        if path.exists():
            return path

        profile = CURRICULUM_PROFILES.get(name, {})
        content = f"""---
type: curriculum
subject: "{concept.get("subject", "")}"
grade: "{concept.get("grade", "")}"
status: active
---

# {name}

## Core Idea

{profile.get("definition") or "这个知识点由已确认错题触发创建，后续可补充教材定义和例题。"}

## Learning Steps

{self._format_bullets(profile.get("steps") or ["先理解概念", "再完成基础例题", "最后回看相关错题"])}

## Common Pitfalls

{self._format_bullets(profile.get("pitfalls") or ["概念边界不稳定", "解题步骤跳步", "检查环节不足"])}

## Parent Guidance

{profile.get("parent_guidance") or "让孩子先说清楚题目考的是什么，再说明每一步为什么可以这样做。"}

## Linked Mistake Concepts

[[{self.concept_note_path(concept).stem}]]
"""
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        return path

    def write_daily_report(self, report_date: str, markdown: str) -> Path:
        path = self.vault_path / "04-Reports" / "Daily" / f"{report_date}.md"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(markdown, encoding="utf-8")
        return path

    def write_weekly_report(self, week_label: str, markdown: str) -> Path:
        path = self.vault_path / "04-Reports" / "Weekly" / f"{week_label}.md"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(markdown, encoding="utf-8")
        return path

    def _safe_name(self, value: str) -> str:
        cleaned = "".join(ch if ch.isalnum() or ch in ("-", "_") else "-" for ch in value.strip())
        return cleaned.strip("-") or "untitled"

    def _subject_dir(self, subject: str) -> str:
        return SUBJECT_DIR_NAMES.get(subject.strip().lower(), self._safe_name(subject))

    def _format_bullets(self, items: Any) -> str:
        if not isinstance(items, list):
            return f"- {items}"
        return "\n".join(f"- {item}" for item in items) or "- 待补充"

    def _format_related_mistakes(self, mistakes: list[dict[str, Any]]) -> str:
        if not mistakes:
            return "待关联已确认错题。"
        lines = []
        for item in mistakes[:20]:
            note_path = Path(str(item.get("note_path") or ""))
            title = item.get("title") or item.get("id") or "未命名错题"
            if note_path.name:
                lines.append(f"- [[{note_path.stem}|{title}]]")
            else:
                lines.append(f"- {title}")
        return "\n".join(lines)
