from datetime import date
from typing import Any


def calculate_expected_progress(
    start_date: date,
    due_date: date,
    evaluation_date: date,
) -> float:
    total_days = (due_date - start_date).days

    if total_days <= 0:
        return 100.0

    if evaluation_date < start_date:
        return 0.0

    if evaluation_date >= due_date:
        return 100.0

    elapsed_days = (evaluation_date - start_date).days
    expected_progress = elapsed_days / total_days * 100

    return round(expected_progress, 1)


def analyze_schedule_task(
    task: dict[str, Any],
    evaluation_date: date,
) -> dict[str, Any]:
    progress = float(task.get("progress", 0))
    status = str(task.get("status", "TODO")).upper()

    start_date = task["start_date"]
    due_date = task["due_date"]

    expected_progress = calculate_expected_progress(
        start_date=start_date,
        due_date=due_date,
        evaluation_date=evaluation_date,
    )

    progress_gap = round(expected_progress - progress, 1)

    overdue_days = max(
        (evaluation_date - due_date).days,
        0,
    )

    completed = (
        status in {"DONE", "COMPLETED", "CLOSED"}
        or progress >= 100
    )

    score = 0
    reasons = []

    if overdue_days > 0 and not completed:
        score += 60
        reasons.append(
            f"마감일을 {overdue_days}일 초과했습니다."
        )

    if progress_gap >= 30:
        score += 40
        reasons.append(
            f"예상 진척률보다 {progress_gap}%p 부족합니다."
        )
    elif progress_gap >= 15:
        score += 25
        reasons.append(
            f"예상 진척률보다 {progress_gap}%p 낮습니다."
        )
    elif progress_gap >= 5:
        score += 10
        reasons.append(
            f"예상 진척률보다 {progress_gap}%p 다소 낮습니다."
        )

    days_until_due = (due_date - evaluation_date).days

    if (
        0 <= days_until_due <= 2
        and progress < 80
        and not completed
    ):
        score += 20
        reasons.append(
            "마감일까지 2일 이하이지만 진행률이 80% 미만입니다."
        )

    if (
        status == "TODO"
        and evaluation_date > start_date
        and progress == 0
    ):
        score += 20
        reasons.append(
            "시작 예정일이 지났지만 업무가 시작되지 않았습니다."
        )

    score = min(score, 100)

    if score >= 60:
        traffic_light = "RED"
        risk_level = "위험"
    elif score >= 25:
        traffic_light = "YELLOW"
        risk_level = "보통"
    else:
        traffic_light = "GREEN"
        risk_level = "양호"

    if not reasons:
        reasons.append(
            "현재 일정과 진행률이 정상 범위입니다."
        )

    return {
        "task_id": task["task_id"],
        "task_name": task["task_name"],
        "progress": progress,
        "expected_progress": expected_progress,
        "progress_gap": progress_gap,
        "overdue_days": overdue_days,
        "risk_score": score,
        "traffic_light": traffic_light,
        "risk_level": risk_level,
        "reasons": reasons,
    }