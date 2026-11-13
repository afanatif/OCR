"""
MCQ Validator — Phase 1.

Checks each RawMCQ for structural completeness before writing to disk.
Does NOT raise exceptions — collects all issues and returns a report,
letting the caller decide whether to abort or continue with warnings.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from src.mcqs.schemas import RawMCQ
from src.core.logger import logger

REQUIRED_OPTION_LABELS = {"A", "B", "C", "D"}   # E is optional in some books


@dataclass
class ValidationReport:
    total: int = 0
    passed: int = 0
    issues: list[str] = field(default_factory=list)

    @property
    def failed(self) -> int:
        return self.total - self.passed

    @property
    def is_clean(self) -> bool:
        return self.failed == 0

    def summary(self) -> str:
        return (
            f"Validation: {self.passed}/{self.total} passed, "
            f"{self.failed} issue(s)"
        )


def validate(mcqs: list[RawMCQ]) -> ValidationReport:
    report = ValidationReport(total=len(mcqs))

    for mcq in mcqs:
        errors: list[str] = []
        q_id = f"Q{mcq.question_number}"

        if not mcq.question_text.strip():
            errors.append(f"{q_id}: Empty question text")

        present_labels = {opt.label for opt in mcq.options}
        missing = REQUIRED_OPTION_LABELS - present_labels
        if missing:
            errors.append(f"{q_id}: Missing options: {sorted(missing)}")

        if mcq.correct_answer not in present_labels:
            errors.append(
                f"{q_id}: correct_answer '{mcq.correct_answer}' "
                f"not in options {sorted(present_labels)}"
            )

        if not errors:
            report.passed += 1
        else:
            report.issues.extend(errors)
            for err in errors:
                logger.warning(err)

    logger.info(report.summary())
    return report
