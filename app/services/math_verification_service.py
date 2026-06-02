from __future__ import annotations

from dataclasses import dataclass
from fractions import Fraction
from typing import Any
import re


@dataclass(frozen=True)
class LinearExpr:
    coefficients: dict[str, Fraction]
    constant: Fraction

    def subtract(self, other: "LinearExpr") -> "LinearExpr":
        variables = set(self.coefficients) | set(other.coefficients)
        return LinearExpr(
            {
                variable: self.coefficients.get(variable, Fraction(0))
                - other.coefficients.get(variable, Fraction(0))
                for variable in variables
            },
            self.constant - other.constant,
        )

    def evaluate(self, values: dict[str, Fraction]) -> Fraction:
        total = self.constant
        for variable, coefficient in self.coefficients.items():
            total += coefficient * values[variable]
        return total


class MathVerificationService:
    """Small deterministic verifier for common junior-high algebra items."""

    def verify_question_items(self, items: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
        verified_items: list[dict[str, Any]] = []
        summary = {
            "verified_count": 0,
            "unsupported_count": 0,
            "conflict_count": 0,
            "wrong_count": 0,
        }
        for item in items:
            verified = dict(item)
            result = self.verify_item(verified)
            verified["verification"] = result
            if result["status"] == "verified":
                summary["verified_count"] += 1
                if result["is_correct"] is False:
                    summary["wrong_count"] += 1
                previous = verified.get("is_correct")
                verified["verified_is_correct"] = result["is_correct"]
                if isinstance(previous, bool) and previous != result["is_correct"]:
                    verified["llm_is_correct"] = previous
                    result["conflict_with_llm"] = True
                    summary["conflict_count"] += 1
                verified["is_correct"] = result["is_correct"]
                if result.get("correct_answer"):
                    verified["correct_answer"] = result["correct_answer"]
                if not result["is_correct"] and result.get("reason"):
                    verified["error_reason"] = self._merge_error_reason(
                        verified.get("error_reason"),
                        result["reason"],
                    )
                    verified.setdefault("error_type", "calculation_error")
            else:
                summary["unsupported_count"] += 1
            verified_items.append(verified)
        return verified_items, summary

    def _merge_error_reason(self, existing: Any, verification_reason: str) -> str:
        existing_text = str(existing or "").strip()
        if not existing_text:
            return verification_reason
        return f"{existing_text} Verification: {verification_reason}"

    def verify_item(self, item: dict[str, Any]) -> dict[str, Any]:
        question = self._normalize_text(str(item.get("question") or ""))
        answer_text = self._answer_text(item)

        for verifier in (
            self._verify_slope,
            self._verify_function_substitution,
            self._verify_linear_system,
            self._verify_one_variable_equation,
        ):
            result = verifier(question, answer_text)
            if result["status"] != "unsupported":
                return result

        return {
            "status": "unsupported",
            "method": None,
            "reason": "No deterministic verifier matched this question type.",
        }

    def _verify_function_substitution(self, question: str, answer_text: str) -> dict[str, Any]:
        if "y" not in question or "x" not in question:
            return self._unsupported()
        equation = re.search(r"y=([^,，;；]+)", question)
        x_match = re.search(r"x=([+-]?\d+(?:/\d+)?(?:\.\d+)?)", question)
        if not equation or not x_match:
            return self._unsupported()
        try:
            expression = self._parse_linear_expr(equation.group(1), variables=("x",))
            x_value = self._parse_number(x_match.group(1))
            expected = expression.evaluate({"x": x_value})
        except ValueError:
            return self._parse_failed("function_substitution")

        answers = self._parse_assignments(answer_text)
        actual = answers.get("y")
        if actual is None:
            return self._parse_failed("function_substitution", "No y value found in student answer.")
        is_correct = actual == expected
        return self._verified(
            method="function_substitution",
            is_correct=is_correct,
            correct_answer=f"y={self._format_number(expected)}",
            reason=(
                ""
                if is_correct
                else (
                    f"Substituting x={self._format_number(x_value)} gives "
                    f"y={self._format_number(expected)}, not y={self._format_number(actual)}."
                )
            ),
            checks=[
                {
                    "expression": f"y={equation.group(1)}",
                    "expected": self._format_number(expected),
                    "student": self._format_number(actual),
                    "passed": is_correct,
                }
            ],
        )

    def _verify_linear_system(self, question: str, answer_text: str) -> dict[str, Any]:
        if question.count("=") < 2 or "x" not in question or "y" not in question:
            return self._unsupported()
        equations = self._extract_equations(question, variables=("x", "y"))
        if len(equations) < 2:
            return self._unsupported()
        try:
            first = self._parse_equation(equations[0], variables=("x", "y"))
            second = self._parse_equation(equations[1], variables=("x", "y"))
            solution = self._solve_two_variable_system(first, second)
        except ValueError:
            return self._parse_failed("linear_system")

        answers = self._parse_assignments(answer_text)
        if "x" not in answers or "y" not in answers:
            return self._parse_failed("linear_system", "No x/y pair found in student answer.")
        values = {"x": answers["x"], "y": answers["y"]}
        checks = []
        for raw_equation, equation in zip(equations[:2], (first, second), strict=False):
            delta = equation.evaluate(values)
            checks.append(
                {
                    "equation": raw_equation,
                    "student_substitution_delta": self._format_number(delta),
                    "passed": delta == 0,
                }
            )
        is_correct = all(check["passed"] for check in checks)
        expected_answer = f"x={self._format_number(solution['x'])}, y={self._format_number(solution['y'])}"
        actual_answer = f"x={self._format_number(values['x'])}, y={self._format_number(values['y'])}"
        return self._verified(
            method="linear_system_substitution",
            is_correct=is_correct,
            correct_answer=expected_answer,
            reason="" if is_correct else f"Substitution failed for {actual_answer}; expected {expected_answer}.",
            checks=checks,
        )

    def _verify_slope(self, question: str, answer_text: str) -> dict[str, Any]:
        if "斜率" not in question and "slope" not in question.lower() and "k" not in question:
            return self._unsupported()
        points = re.findall(
            r"\(\s*([+-]?\d+(?:/\d+)?(?:\.\d+)?)\s*[,，]\s*([+-]?\d+(?:/\d+)?(?:\.\d+)?)\s*\)",
            question,
        )
        if len(points) < 2:
            return self._unsupported()
        try:
            x1, y1 = (self._parse_number(value) for value in points[0])
            x2, y2 = (self._parse_number(value) for value in points[1])
            expected = (y2 - y1) / (x2 - x1)
        except (ValueError, ZeroDivisionError):
            return self._parse_failed("slope")
        answers = self._parse_assignments(answer_text)
        actual = answers.get("k") or self._parse_first_number(answer_text)
        if actual is None:
            return self._parse_failed("slope", "No slope value found in student answer.")
        is_correct = actual == expected
        return self._verified(
            method="slope",
            is_correct=is_correct,
            correct_answer=f"k={self._format_number(expected)}",
            reason=(
                ""
                if is_correct
                else (
                    f"Slope is ({self._format_number(y2)}-{self._format_number(y1)})/"
                    f"({self._format_number(x2)}-{self._format_number(x1)})="
                    f"{self._format_number(expected)}, not {self._format_number(actual)}."
                )
            ),
            checks=[
                {
                    "formula": "(y2-y1)/(x2-x1)",
                    "expected": self._format_number(expected),
                    "student": self._format_number(actual),
                    "passed": is_correct,
                }
            ],
        )

    def _verify_one_variable_equation(self, question: str, answer_text: str) -> dict[str, Any]:
        if question.count("=") != 1 or "x" not in question:
            return self._unsupported()
        raw_equations = self._extract_equations(question, variables=("x",))
        if not raw_equations:
            return self._unsupported()
        try:
            equation = self._parse_equation(raw_equations[0], variables=("x",))
            coefficient = equation.coefficients.get("x", Fraction(0))
            if coefficient == 0:
                return self._unsupported()
            expected = -equation.constant / coefficient
        except ValueError:
            return self._parse_failed("one_variable_equation")
        answers = self._parse_assignments(answer_text)
        actual = answers.get("x")
        if actual is None:
            return self._parse_failed("one_variable_equation", "No x value found in student answer.")
        is_correct = actual == expected
        return self._verified(
            method="one_variable_equation",
            is_correct=is_correct,
            correct_answer=f"x={self._format_number(expected)}",
            reason=(
                ""
                if is_correct
                else f"Solving gives x={self._format_number(expected)}, not x={self._format_number(actual)}."
            ),
            checks=[
                {
                    "equation": raw_equations[0],
                    "expected": self._format_number(expected),
                    "student": self._format_number(actual),
                    "passed": is_correct,
                }
            ],
        )

    def _answer_text(self, item: dict[str, Any]) -> str:
        parts = [str(item.get("student_answer") or "")]
        steps = item.get("student_steps") or []
        if isinstance(steps, list):
            parts.extend(str(step) for step in steps)
        else:
            parts.append(str(steps))
        return "\n".join(part for part in parts if part.strip())

    def _extract_equations(self, text: str, *, variables: tuple[str, ...]) -> list[str]:
        parts = re.split(r"[,，;；\n。]", text)
        equations = []
        for part in parts:
            compact = part.strip()
            if ":" in compact and "=" in compact.split(":", 1)[1]:
                compact = compact.split(":", 1)[1].strip()
            if "=" in compact and any(variable in compact for variable in variables):
                equations.append(compact)
        if not equations and "=" in text:
            equations.append(text)
        return equations

    def _parse_equation(self, text: str, *, variables: tuple[str, ...]) -> LinearExpr:
        left, right = text.split("=", 1)
        return self._parse_linear_expr(left, variables=variables).subtract(
            self._parse_linear_expr(right, variables=variables)
        )

    def _parse_linear_expr(self, text: str, *, variables: tuple[str, ...]) -> LinearExpr:
        compact = self._normalize_text(text).replace(" ", "")
        compact = self._expand_parenthesized_products(compact, variables=variables)
        compact = compact.replace("-", "+-")
        if compact.startswith("+"):
            compact = compact[1:]
        coefficients = {variable: Fraction(0) for variable in variables}
        constant = Fraction(0)
        for term in [part for part in compact.split("+") if part]:
            variable = next((candidate for candidate in variables if candidate in term), None)
            if variable:
                coefficient_text = term.replace("*", "").replace(variable, "")
                if coefficient_text in {"", "+"}:
                    coefficient = Fraction(1)
                elif coefficient_text == "-":
                    coefficient = Fraction(-1)
                else:
                    coefficient = self._parse_number(coefficient_text)
                coefficients[variable] += coefficient
            else:
                constant += self._parse_number(term)
        return LinearExpr(coefficients, constant)

    def _expand_parenthesized_products(self, text: str, *, variables: tuple[str, ...]) -> str:
        compact = text.replace("*(", "(")
        pattern = re.compile(r"([+-]?(?:\d+(?:/\d+)?(?:\.\d+)?)?)\(([^()]+)\)")

        while True:
            match = pattern.search(compact)
            if not match:
                return compact
            coefficient = self._parse_implicit_coefficient(match.group(1))
            inner = self._parse_linear_expr(match.group(2), variables=variables)
            expanded = LinearExpr(
                {
                    variable: coefficient * value
                    for variable, value in inner.coefficients.items()
                },
                coefficient * inner.constant,
            )
            replacement = self._linear_expr_to_text(expanded)
            if match.group(1).startswith("+") and not replacement.startswith("-"):
                replacement = f"+{replacement}"
            compact = compact[: match.start()] + replacement + compact[match.end() :]

    def _parse_implicit_coefficient(self, text: str) -> Fraction:
        if text in {"", "+"}:
            return Fraction(1)
        if text == "-":
            return Fraction(-1)
        return self._parse_number(text)

    def _linear_expr_to_text(self, expression: LinearExpr) -> str:
        parts: list[str] = []
        for variable, coefficient in expression.coefficients.items():
            if coefficient == 0:
                continue
            if coefficient == 1:
                parts.append(f"+{variable}")
            elif coefficient == -1:
                parts.append(f"-{variable}")
            elif coefficient > 0:
                parts.append(f"+{self._format_number(coefficient)}{variable}")
            else:
                parts.append(f"{self._format_number(coefficient)}{variable}")
        if expression.constant > 0:
            parts.append(f"+{self._format_number(expression.constant)}")
        elif expression.constant < 0:
            parts.append(self._format_number(expression.constant))
        if not parts:
            return "0"
        result = "".join(parts)
        return result[1:] if result.startswith("+") else result

    def _solve_two_variable_system(self, first: LinearExpr, second: LinearExpr) -> dict[str, Fraction]:
        a1 = first.coefficients.get("x", Fraction(0))
        b1 = first.coefficients.get("y", Fraction(0))
        c1 = -first.constant
        a2 = second.coefficients.get("x", Fraction(0))
        b2 = second.coefficients.get("y", Fraction(0))
        c2 = -second.constant
        determinant = a1 * b2 - a2 * b1
        if determinant == 0:
            raise ValueError("linear system determinant is zero")
        return {
            "x": (c1 * b2 - c2 * b1) / determinant,
            "y": (a1 * c2 - a2 * c1) / determinant,
        }

    def _parse_assignments(self, text: str) -> dict[str, Fraction]:
        normalized = self._normalize_text(text)
        assignments: dict[str, Fraction] = {}
        for variable, value in re.findall(r"\b([xyk])\s*=\s*([+-]?\d+(?:/\d+)?(?:\.\d+)?)", normalized):
            try:
                assignments[variable] = self._parse_number(value)
            except ValueError:
                continue
        return assignments

    def _parse_first_number(self, text: str) -> Fraction | None:
        match = re.search(r"([+-]?\d+(?:/\d+)?(?:\.\d+)?)", self._normalize_text(text))
        if not match:
            return None
        try:
            return self._parse_number(match.group(1))
        except ValueError:
            return None

    def _parse_number(self, text: str) -> Fraction:
        value = text.strip().strip("()")
        if not value:
            raise ValueError("empty number")
        return Fraction(value)

    def _format_number(self, value: Fraction) -> str:
        if value.denominator == 1:
            return str(value.numerator)
        return f"{value.numerator}/{value.denominator}"

    def _normalize_text(self, text: str) -> str:
        replacements = {
            "＝": "=",
            "−": "-",
            "－": "-",
            "×": "*",
            "·": "*",
            "（": "(",
            "）": ")",
            "，": ",",
            "：": ":",
        }
        normalized = text
        for source, target in replacements.items():
            normalized = normalized.replace(source, target)
        return normalized

    def _verified(
        self,
        *,
        method: str,
        is_correct: bool,
        correct_answer: str,
        reason: str,
        checks: list[dict[str, Any]],
    ) -> dict[str, Any]:
        return {
            "status": "verified",
            "method": method,
            "is_correct": is_correct,
            "correct_answer": correct_answer,
            "reason": reason,
            "checks": checks,
        }

    def _parse_failed(self, method: str, reason: str = "Could not parse enough fields to verify.") -> dict[str, Any]:
        return {"status": "parse_failed", "method": method, "reason": reason}

    def _unsupported(self) -> dict[str, Any]:
        return {"status": "unsupported", "method": None}
