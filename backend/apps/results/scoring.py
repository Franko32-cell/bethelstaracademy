from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP


def round_half_up(value, digits: int = 1):
    """Round values using standard "half up" semantics."""
    quant = Decimal("1").scaleb(-digits)
    return float(Decimal(str(value)).quantize(quant, rounding=ROUND_HALF_UP))


def result_level(result_or_school_class) -> str:
    """Return the class level for a Result-like object or a SchoolClass-like object."""
    if result_or_school_class is None:
        return "basic_7_9"

    school_class = getattr(result_or_school_class, "school_class", None)
    if school_class is None and hasattr(result_or_school_class, "student"):
        school_class = getattr(result_or_school_class.student, "school_class", None)

    if school_class is not None:
        return getattr(school_class, "level", "basic_7_9") or "basic_7_9"

    level = getattr(result_or_school_class, "level", None)
    if level:
        return level

    return "basic_7_9"


def is_exam_only(level: str | None) -> bool:
    """Nursery/KG report cards are exam-only. Other classes include SBA."""
    if not level:
        return False
    normalized = str(level).strip().lower()
    return normalized in {"nursery_kg", "nursery", "kg"}


def validate_components(level: str | None, values: dict | None) -> dict:
    """Validate numeric score components for the active class level."""
    values = values or {}
    errors: dict[str, str] = {}
    exam_only = is_exam_only(level)

    if exam_only:
        exam = float(values.get("exam") or 0)
        if exam < 0 or exam > 100:
            errors["exam"] = "Exam mark must be between 0 and 100."
        return errors

    caps = {
        "test1": 20,
        "group_work": 10,
        "test2": 30,
        "exam": 50,
    }

    for field, max_value in caps.items():
        raw = values.get(field)
        if raw in (None, ""):
            continue
        try:
            number = float(raw)
        except (TypeError, ValueError):
            errors[field] = f"{field} must be numeric."
            continue
        if number < 0 or number > max_value:
            errors[field] = f"{field} must be between 0 and {max_value}."

    test1 = float(values.get("test1") or 0)
    group_work = float(values.get("group_work") or 0)
    test2 = float(values.get("test2") or 0)
    if test1 + group_work + test2 > 60:
        errors["sba_total"] = "SBA components must not exceed 60 total."

    return errors


def result_scores(result) -> dict:
    """Return total and component scores regardless of the underlying schema."""
    exam_only = is_exam_only(result_level(result))

    if hasattr(result, "test1") or hasattr(result, "group_work") or hasattr(result, "test2") or hasattr(result, "exam"):
        test1 = float(getattr(result, "test1", 0) or 0)
        group_work = float(getattr(result, "group_work", 0) or 0)
        test2 = float(getattr(result, "test2", 0) or 0)
        exam = float(getattr(result, "exam", 0) or 0)
        sba_raw = round_half_up(test1 + group_work + test2, 1)
        sba = round_half_up((sba_raw / 60) * 50, 1) if sba_raw else 0.0
        exam_score = round_half_up(exam, 1)
        if exam_only:
            total = round_half_up(exam_score, 1)
        else:
            total = round_half_up(sba + exam_score, 1)
        return {
            "exam_only": exam_only,
            "sba_raw": sba_raw,
            "sba": sba,
            "exam_score": exam_score,
            "total": total,
        }

    reopen = float(getattr(result, "reopen", 0) or 0)
    ca = float(getattr(result, "ca", 0) or 0)
    exams = float(getattr(result, "exams", 0) or 0)
    total = round_half_up(reopen + ca + exams, 1)
    return {
        "exam_only": False,
        "sba_raw": total,
        "sba": total,
        "exam_score": total,
        "total": total,
    }
