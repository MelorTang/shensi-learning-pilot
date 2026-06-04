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

    def scale(self, coefficient: Fraction) -> "LinearExpr":
        return LinearExpr(
            {variable: value * coefficient for variable, value in self.coefficients.items()},
            self.constant * coefficient,
        )

    def has_variable_terms(self) -> bool:
        return any(coefficient != 0 for coefficient in self.coefficients.values())

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
            "needs_parent_review_count": 0,
        }
        for item in items:
            verified = dict(item)
            result = self.verify_item(verified)
            verified["verification"] = result
            needs_parent_review = False
            review_reason = ""
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
                    needs_parent_review = True
                    review_reason = "deterministic verifier overrode the LLM verdict"
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
                needs_parent_review = True
                review_reason = f"verification {result['status']}"
            verified["needs_parent_review"] = needs_parent_review
            if review_reason:
                verified["review_reason"] = review_reason
                summary["needs_parent_review_count"] += 1
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
        first_parse_failed: dict[str, Any] | None = None

        for verifier in (
            self._verify_point_on_line,
            self._verify_slope,
            self._verify_geometry_measure,
            self._verify_function_substitution,
            self._verify_linear_system,
            self._verify_ratio_equation,
            self._verify_linear_simplification,
            self._verify_one_variable_equation,
        ):
            result = verifier(question, answer_text)
            if result["status"] == "verified":
                return result
            if result["status"] == "parse_failed" and first_parse_failed is None:
                first_parse_failed = result
                continue
            if result["status"] != "unsupported":
                return result

        if first_parse_failed is not None:
            return first_parse_failed

        return {
            "status": "unsupported",
            "method": None,
            "reason": "No deterministic verifier matched this question type.",
        }

    def _verify_geometry_measure(self, question: str, answer_text: str) -> dict[str, Any]:
        lower = question.lower()
        is_area = self._contains_any(lower, ("area", "面积"))
        is_perimeter = self._contains_any(lower, ("perimeter", "周长"))
        if not is_area and not is_perimeter:
            return self._unsupported()

        if self._contains_any(lower, ("rectangle", "rectangular", "长方形", "矩形")):
            result = self._verify_rectangle_measure(question, answer_text, is_area, is_perimeter)
            if result["status"] != "unsupported":
                return result

        if self._contains_any(lower, ("triangle", "三角形")):
            result = self._verify_triangle_measure(question, answer_text, is_area)
            if result["status"] != "unsupported":
                return result

        return self._unsupported()

    def _verify_rectangle_measure(
        self,
        question: str,
        answer_text: str,
        is_area: bool,
        is_perimeter: bool,
    ) -> dict[str, Any]:
        length = self._extract_dimension(question, ("length", "long", "长"))
        width = self._extract_dimension(question, ("width", "wide", "宽"))
        if length is None or width is None:
            return self._unsupported()
        expected = length * width if is_area else 2 * (length + width)
        label = "area" if is_area else "perimeter"
        actual = self._parse_measure_answer(answer_text)
        if actual is None:
            return self._parse_failed("geometry_measure", "No numeric measure found in student answer.")
        is_correct = actual == expected
        return self._verified(
            method=f"rectangle_{label}",
            is_correct=is_correct,
            correct_answer=self._format_number(expected),
            reason=(
                ""
                if is_correct
                else (
                    f"Rectangle {label} is {self._format_number(expected)}, "
                    f"not {self._format_number(actual)}."
                )
            ),
            checks=[
                {
                    "shape": "rectangle",
                    "measure": label,
                    "length": self._format_number(length),
                    "width": self._format_number(width),
                    "expected": self._format_number(expected),
                    "student": self._format_number(actual),
                    "passed": is_correct,
                }
            ],
        )

    def _verify_triangle_measure(
        self,
        question: str,
        answer_text: str,
        is_area: bool,
    ) -> dict[str, Any]:
        if not is_area:
            return self._unsupported()
        base = self._extract_dimension(question, ("base", "底"))
        height = self._extract_dimension(question, ("height", "高"))
        if base is None or height is None:
            return self._unsupported()
        expected = base * height / 2
        actual = self._parse_measure_answer(answer_text)
        if actual is None:
            return self._parse_failed("geometry_measure", "No numeric measure found in student answer.")
        is_correct = actual == expected
        return self._verified(
            method="triangle_area",
            is_correct=is_correct,
            correct_answer=self._format_number(expected),
            reason=(
                ""
                if is_correct
                else (
                    f"Triangle area is {self._format_number(expected)}, "
                    f"not {self._format_number(actual)}."
                )
            ),
            checks=[
                {
                    "shape": "triangle",
                    "measure": "area",
                    "base": self._format_number(base),
                    "height": self._format_number(height),
                    "expected": self._format_number(expected),
                    "student": self._format_number(actual),
                    "passed": is_correct,
                }
            ],
        )

    def _verify_function_substitution(self, question: str, answer_text: str) -> dict[str, Any]:
        if "y" not in question or "x" not in question:
            return self._unsupported()
        equation = re.search(r"y\s*=\s*([^,，;；]+)", question)
        x_match = re.search(r"x\s*=\s*([+-]?\d+(?:/\d+)?(?:\.\d+)?)", question)
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

    def _verify_point_on_line(self, question: str, answer_text: str) -> dict[str, Any]:
        lower_question = question.lower()
        lower_answer = answer_text.lower()
        if not self._looks_like_point_on_line_question(lower_question, lower_answer):
            return self._unsupported()

        points = self._extract_labeled_points(question)
        if len(points) < 3:
            return self._unsupported()

        target = self._pick_target_point(points, lower_question)
        line_points = self._pick_line_points(points, target)
        if target is None or len(line_points) < 2:
            return self._unsupported()

        target_name, target_x, target_y = target
        first_name, x1, y1 = line_points[0]
        second_name, x2, y2 = line_points[1]
        dx = x2 - x1
        dy = y2 - y1
        if dx == 0:
            expected_on_line = target_x == x1
            lhs = Fraction(0) if expected_on_line else Fraction(1)
            rhs = Fraction(0)
        else:
            lhs = (target_y - y1) * dx
            rhs = dy * (target_x - x1)
            expected_on_line = lhs == rhs

        claimed_on_line = self._parse_on_line_claim(answer_text)
        if claimed_on_line is None:
            return self._parse_failed("point_on_line", "No on-line/not-on-line conclusion found.")

        is_correct = claimed_on_line == expected_on_line
        correct_answer = (
            f"{target_name} is on line {first_name}{second_name}"
            if expected_on_line
            else f"{target_name} is not on line {first_name}{second_name}"
        )
        student_claim = "on" if claimed_on_line else "not on"
        expected_claim = "on" if expected_on_line else "not on"
        return self._verified(
            method="point_on_line",
            is_correct=is_correct,
            correct_answer=correct_answer,
            reason=(
                ""
                if is_correct
                else (
                    f"Point {target_name} should be {expected_claim} line "
                    f"{first_name}{second_name}, but the answer says {student_claim}."
                )
            ),
            checks=[
                {
                    "line": f"{first_name}{second_name}",
                    "target": target_name,
                    "collinearity_left": self._format_number(lhs),
                    "collinearity_right": self._format_number(rhs),
                    "expected_on_line": expected_on_line,
                    "student_claim_on_line": claimed_on_line,
                    "passed": is_correct,
                }
            ],
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

    def _verify_ratio_equation(self, question: str, answer_text: str) -> dict[str, Any]:
        if "/" not in question or question.count("=") != 1 or "x" not in question:
            return self._unsupported()
        raw_equations = self._extract_equations(question, variables=("x",))
        if not raw_equations:
            return self._unsupported()
        raw_equation = raw_equations[0]
        try:
            left_text, right_text = raw_equation.split("=", 1)
            left_numerator, left_denominator = self._parse_ratio_side(left_text, variables=("x",))
            right_numerator, right_denominator = self._parse_ratio_side(right_text, variables=("x",))
            left_product = self._multiply_linear_exprs(left_numerator, right_denominator)
            right_product = self._multiply_linear_exprs(right_numerator, left_denominator)
            equation = left_product.subtract(right_product)
            expected = self._solve_one_variable_zero(equation)
            if left_denominator.evaluate({"x": expected}) == 0:
                return self._parse_failed("ratio_equation", "Solution makes the left denominator zero.")
            if right_denominator.evaluate({"x": expected}) == 0:
                return self._parse_failed("ratio_equation", "Solution makes the right denominator zero.")
        except ValueError:
            return self._parse_failed("ratio_equation")

        answers = self._parse_assignments(answer_text)
        actual = answers.get("x")
        if actual is None:
            return self._parse_failed("ratio_equation", "No x value found in student answer.")
        is_correct = actual == expected
        return self._verified(
            method="ratio_equation_cross_multiply",
            is_correct=is_correct,
            correct_answer=f"x={self._format_number(expected)}",
            reason=(
                ""
                if is_correct
                else (
                    f"Cross multiplication gives x={self._format_number(expected)}, "
                    f"not x={self._format_number(actual)}."
                )
            ),
            checks=[
                {
                    "equation": raw_equation,
                    "expected": self._format_number(expected),
                    "student": self._format_number(actual),
                    "passed": is_correct,
                }
            ],
        )

    def _verify_linear_simplification(self, question: str, answer_text: str) -> dict[str, Any]:
        if "=" in question or "x" not in question:
            return self._unsupported()
        if not self._looks_like_simplification(question):
            return self._unsupported()
        expression_text = self._extract_expression_text(question)
        student_text = self._extract_student_expression(answer_text)
        if not expression_text or not student_text:
            return self._unsupported()
        try:
            expected = self._parse_linear_expr(expression_text, variables=("x",))
            actual = self._parse_linear_expr(student_text, variables=("x",))
        except ValueError:
            return self._parse_failed("linear_simplification")

        is_correct = self._linear_expr_equal(expected, actual)
        expected_text = self._linear_expr_to_text(expected)
        actual_text = self._linear_expr_to_text(actual)
        return self._verified(
            method="linear_simplification",
            is_correct=is_correct,
            correct_answer=expected_text,
            reason=(
                ""
                if is_correct
                else f"Simplifying gives {expected_text}, not {actual_text}."
            ),
            checks=[
                {
                    "expression": expression_text,
                    "expected": expected_text,
                    "student": actual_text,
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
            expected = self._solve_one_variable_zero(equation)
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

    def _looks_like_point_on_line_question(self, question: str, answer_text: str) -> bool:
        combined = f"{question}\n{answer_text}".lower()
        return (
            ("line" in combined and (" on " in combined or "not on" in combined))
            or "在直线" in combined
            or "不在直线" in combined
            or "是否在" in combined
        )

    def _extract_labeled_points(self, text: str) -> list[tuple[str, Fraction, Fraction]]:
        normalized = self._normalize_text(text)
        matches = re.findall(
            r"\b([A-Z])\s*\(\s*([+-]?\d+(?:/\d+)?(?:\.\d+)?)\s*[,，]\s*([+-]?\d+(?:/\d+)?(?:\.\d+)?)\s*\)",
            normalized,
        )
        points: list[tuple[str, Fraction, Fraction]] = []
        for name, x_text, y_text in matches:
            try:
                points.append((name, self._parse_number(x_text), self._parse_number(y_text)))
            except ValueError:
                continue
        return points

    def _pick_target_point(
        self,
        points: list[tuple[str, Fraction, Fraction]],
        lower_question: str,
    ) -> tuple[str, Fraction, Fraction] | None:
        for point in points:
            if point[0] == "Q":
                return point
        for point in reversed(points):
            lower_name = point[0].lower()
            if f"point {lower_name}" in lower_question or f"点{point[0]}" in lower_question:
                return point
        return points[-1] if points else None

    def _pick_line_points(
        self,
        points: list[tuple[str, Fraction, Fraction]],
        target: tuple[str, Fraction, Fraction] | None,
    ) -> list[tuple[str, Fraction, Fraction]]:
        if target is None:
            return []
        target_name = target[0]
        named = {point[0]: point for point in points}
        if "M" in named and "N" in named and target_name not in {"M", "N"}:
            return [named["M"], named["N"]]
        if "A" in named and "B" in named and target_name not in {"A", "B"}:
            return [named["A"], named["B"]]
        return [point for point in points if point[0] != target_name][:2]

    def _parse_on_line_claim(self, text: str) -> bool | None:
        normalized = self._normalize_text(text).lower()
        if re.search(r"\bnot\s+on\b", normalized) or "不在" in normalized:
            return False
        if re.search(r"\bon\s+(?:the\s+)?line\b", normalized) or "在直线" in normalized:
            return True
        return None

    def _parse_ratio_side(
        self,
        text: str,
        *,
        variables: tuple[str, ...],
    ) -> tuple[LinearExpr, LinearExpr]:
        numerator_text, denominator_text = self._split_top_level_fraction(text)
        numerator = self._parse_linear_expr(numerator_text, variables=variables)
        denominator = self._parse_linear_expr(denominator_text, variables=variables)
        if not denominator.has_variable_terms() and denominator.constant == 0:
            raise ValueError("ratio denominator is zero")
        return numerator, denominator

    def _split_top_level_fraction(self, text: str) -> tuple[str, str]:
        compact = self._normalize_text(text).replace(" ", "")
        depth = 0
        for index, char in enumerate(compact):
            if char == "(":
                depth += 1
            elif char == ")":
                depth -= 1
            elif char == "/" and depth == 0:
                return compact[:index], compact[index + 1 :]
        return compact, "1"

    def _multiply_linear_exprs(self, first: LinearExpr, second: LinearExpr) -> LinearExpr:
        if first.has_variable_terms() and second.has_variable_terms():
            raise ValueError("nonlinear product is not supported")
        if first.has_variable_terms():
            return first.scale(second.constant)
        return second.scale(first.constant)

    def _solve_one_variable_zero(self, equation: LinearExpr) -> Fraction:
        coefficient = equation.coefficients.get("x", Fraction(0))
        if coefficient == 0:
            raise ValueError("equation has no x coefficient")
        return -equation.constant / coefficient

    def _looks_like_simplification(self, text: str) -> bool:
        lower = text.lower()
        keywords = (
            "simplify",
            "combine",
            "like terms",
            "化简",
            "合并",
            "同类项",
        )
        return any(keyword in lower for keyword in keywords)

    def _extract_expression_text(self, text: str) -> str:
        normalized = self._normalize_text(text)
        if ":" in normalized:
            normalized = normalized.split(":", 1)[1]
        leading_expression = re.search(r"([xyk]\b|[+-]?\d|\()", normalized)
        if leading_expression:
            normalized = normalized[leading_expression.start() :]
        return self._strip_trailing_prompt_text(normalized)

    def _extract_student_expression(self, text: str) -> str:
        normalized = self._normalize_text(text)
        for line in normalized.splitlines():
            candidate = line.strip()
            if not candidate:
                continue
            if "=" in candidate:
                left, right = candidate.split("=", 1)
                if len(right.strip()) >= len(left.strip()):
                    candidate = right.strip()
            return self._strip_trailing_prompt_text(candidate)
        return ""

    def _strip_trailing_prompt_text(self, text: str) -> str:
        allowed = set("0123456789xyk+-*/(). ")
        chars: list[str] = []
        for char in text:
            if char in allowed:
                chars.append(char)
                continue
            if chars:
                break
        return "".join(chars).strip()

    def _linear_expr_equal(self, first: LinearExpr, second: LinearExpr) -> bool:
        variables = set(first.coefficients) | set(second.coefficients)
        coefficients_equal = all(
            first.coefficients.get(variable, Fraction(0))
            == second.coefficients.get(variable, Fraction(0))
            for variable in variables
        )
        return coefficients_equal and first.constant == second.constant

    def _contains_any(self, text: str, needles: tuple[str, ...]) -> bool:
        return any(needle in text for needle in needles)

    def _extract_dimension(self, text: str, labels: tuple[str, ...]) -> Fraction | None:
        normalized = self._normalize_text(text)
        for label in labels:
            match = re.search(
                rf"{re.escape(label)}\s*(?:is|=|:|为|是)?\s*([+-]?\d+(?:/\d+)?(?:\.\d+)?)",
                normalized,
                flags=re.IGNORECASE,
            )
            if match:
                try:
                    return self._parse_number(match.group(1))
                except ValueError:
                    return None
        return None

    def _parse_measure_answer(self, text: str) -> Fraction | None:
        normalized = self._normalize_text(text)
        assignment = re.search(r"=\s*([+-]?\d+(?:/\d+)?(?:\.\d+)?)", normalized)
        if assignment:
            try:
                return self._parse_number(assignment.group(1))
            except ValueError:
                return None
        matches = re.findall(r"([+-]?\d+(?:/\d+)?(?:\.\d+)?)", normalized)
        if not matches:
            return None
        try:
            return self._parse_number(matches[0])
        except ValueError:
            return None

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
            leading_equation = re.search(r"([xyk]\b|[+-]?\d|\()", compact)
            if leading_equation and leading_equation.start() > 0:
                compact = compact[leading_equation.start() :].strip()
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
        delimiters = re.compile(r"[,，;；\n。]")
        pattern = re.compile(r"(?<![A-Za-z0-9_+\-*/])([xyk])\s*=")
        for match in pattern.finditer(normalized):
            variable = match.group(1)
            remainder = normalized[match.end() :]
            delimiter = delimiters.search(remainder)
            segment = remainder[: delimiter.start()] if delimiter else remainder
            values = re.findall(r"([+-]?\d+(?:/\d+)?(?:\.\d+)?)", segment)
            if not values:
                continue
            try:
                assignments[variable] = self._parse_number(values[-1])
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
