from datetime import datetime, date, time, timedelta, timezone
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.database import SessionLocal
from app.models.database_models import (
    AnomalyFlag,
    AttendanceEvent,
    AttendanceStatus,
    ClassroomObservation,
    Industry,
    ReviewStatus,
    Student,
    TrainingRoster,
)
from app.services.faculty_service import is_faculty_profile


def _today_window_utc(target_date: datetime | None = None) -> tuple[datetime, datetime]:
    """
    Returns UTC start/end datetime for the requested date.

    For POC, dashboard uses UTC because backend event_time is stored as timezone-aware UTC.
    """
    now = target_date or datetime.now(timezone.utc)
    day = now.date()

    start_dt = datetime.combine(day, time.min, tzinfo=timezone.utc)
    end_dt = datetime.combine(day, time.max, tzinfo=timezone.utc)

    return start_dt, end_dt


def _safe_status(value: Any) -> str:
    """
    Converts enum/string status safely to string.
    """
    if value is None:
        return "unknown"

    if hasattr(value, "value"):
        return str(value.value)

    return str(value)


def get_latest_attendance_events_by_student_today(
    db: Session,
    *,
    target_date: datetime | None = None,
) -> list[AttendanceEvent]:
    """
    Returns only the latest attendance event per student for today.

    This prevents repeated test check-ins from inflating:
    - present count
    - needs review count
    - outside geofence count
    - status breakdown
    """
    start_dt, end_dt = _today_window_utc(target_date)

    stmt = (
        select(AttendanceEvent)
        .where(AttendanceEvent.event_time >= start_dt)
        .where(AttendanceEvent.event_time <= end_dt)
        .order_by(AttendanceEvent.event_time.asc(), AttendanceEvent.id.asc())
    )

    events = db.execute(stmt).scalars().all()

    latest_by_student: dict[int, AttendanceEvent] = {}

    for event in events:
        student_id = int(event.student_id)

        existing = latest_by_student.get(student_id)

        if existing is None:
            latest_by_student[student_id] = event
            continue

        existing_time = existing.event_time
        event_time = event.event_time

        if event_time > existing_time:
            latest_by_student[student_id] = event
        elif event_time == existing_time and event.id > existing.id:
            latest_by_student[student_id] = event

    return list(latest_by_student.values())


def get_today_anomalies(
    db: Session,
    *,
    target_date: datetime | None = None,
) -> list[AnomalyFlag]:
    """
    Returns all anomaly flags created today.

    Unlike attendance status, anomalies should remain event-based because each anomaly
    is a separate review item.
    """
    start_dt, end_dt = _today_window_utc(target_date)

    stmt = (
        select(AnomalyFlag)
        .where(AnomalyFlag.created_at >= start_dt)
        .where(AnomalyFlag.created_at <= end_dt)
        .order_by(AnomalyFlag.id.desc())
    )

    return db.execute(stmt).scalars().all()


def count_active_rosters_today(
    db: Session,
    *,
    target_date: datetime | None = None,
) -> int:
    """
    Counts active rosters for today.

    Assumes TrainingRoster has:
    - start_date
    - end_date
    - is_active

    If your model does not have is_active, remove that filter.
    """
    today = (target_date or datetime.now(timezone.utc)).date()

    stmt = (
        select(func.count())
        .select_from(TrainingRoster)
        .where(TrainingRoster.start_date <= today)
        .where(TrainingRoster.end_date >= today)
    )

    if hasattr(TrainingRoster, "is_active"):
        stmt = stmt.where(TrainingRoster.is_active.is_(True))

    return int(db.execute(stmt).scalar() or 0)


def build_status_breakdown_from_latest_events(
    latest_events: list[AttendanceEvent],
) -> list[dict[str, Any]]:
    """
    Builds status breakdown from latest event per student only.
    """
    counts: dict[str, int] = {}

    for event in latest_events:
        status = _safe_status(event.status)
        counts[status] = counts.get(status, 0) + 1

    return [
        {
            "status": status,
            "count": count,
        }
        for status, count in sorted(counts.items())
    ]


def build_anomaly_breakdown(
    anomalies: list[AnomalyFlag],
) -> list[dict[str, Any]]:
    """
    Builds anomaly breakdown from anomaly records.
    """
    counts: dict[tuple[str, str], int] = {}

    for anomaly in anomalies:
        anomaly_type = str(anomaly.anomaly_type)
        severity = str(anomaly.severity)

        key = (anomaly_type, severity)
        counts[key] = counts.get(key, 0) + 1

    return [
        {
            "anomaly_type": anomaly_type,
            "severity": severity,
            "count": count,
        }
        for (anomaly_type, severity), count in sorted(counts.items())
    ]


def get_dashboard_summary(
    db: Session,
    *,
    target_date: datetime | None = None,
) -> dict[str, Any]:
    """
    Main dashboard summary.

    Attendance counts are based on latest attendance event per student for today.
    Anomaly counts remain event-based.
    """
    today = (target_date or datetime.now(timezone.utc)).date()

    total_students = int(
        db.execute(select(func.count()).select_from(Student)).scalar() or 0
    )
    faculty_profiles = db.execute(select(Student)).scalars().all()
    total_faculty = sum(1 for item in faculty_profiles if is_faculty_profile(db, item))

    total_industries = int(
        db.execute(select(func.count()).select_from(Industry)).scalar() or 0
    )

    active_rosters_today = count_active_rosters_today(db, target_date=target_date)

    latest_events = get_latest_attendance_events_by_student_today(
        db,
        target_date=target_date,
    )

    today_anomalies = get_today_anomalies(
        db,
        target_date=target_date,
    )

    checked_in_students_today = len(latest_events)

    status_counts: dict[str, int] = {}

    for event in latest_events:
        status = _safe_status(event.status)
        status_counts[status] = status_counts.get(status, 0) + 1

    present_today = status_counts.get(AttendanceStatus.PRESENT.value, 0)
    late_today = status_counts.get(AttendanceStatus.LATE.value, 0)
    outside_geofence_today = status_counts.get(AttendanceStatus.OUTSIDE_GEOFENCE.value, 0)
    face_mismatch_today = status_counts.get(AttendanceStatus.FACE_MISMATCH.value, 0)
    needs_review_today = status_counts.get(AttendanceStatus.NEEDS_REVIEW.value, 0)

    absent_today = max(active_rosters_today - checked_in_students_today, 0)

    anomalies_today = len(today_anomalies)

    pending_reviews = sum(
        1
        for anomaly in today_anomalies
        if str(anomaly.review_status) == ReviewStatus.PENDING.value
    )

    if active_rosters_today > 0:
        attendance_percentage = round(
            (checked_in_students_today / active_rosters_today) * 100,
            2,
        )
    else:
        attendance_percentage = 0.0

    return {
        "summary_date": today.isoformat(),
        "total_students": total_students,
        "total_faculty": total_faculty,
        "total_monitored_profiles": total_students,
        "total_industries": total_industries,
        "active_rosters_today": active_rosters_today,
        "checked_in_students_today": checked_in_students_today,
        "present_today": present_today,
        "late_today": late_today,
        "outside_geofence_today": outside_geofence_today,
        "face_mismatch_today": face_mismatch_today,
        "needs_review_today": needs_review_today,
        "absent_today": absent_today,
        "anomalies_today": anomalies_today,
        "pending_reviews": pending_reviews,
        "attendance_percentage": attendance_percentage,
    }


def get_dashboard_data(
    db: Session,
    *,
    target_date: datetime | None = None,
) -> dict[str, Any]:
    """
    Full dashboard payload used by API.
    """
    latest_events = get_latest_attendance_events_by_student_today(
        db,
        target_date=target_date,
    )

    today_anomalies = get_today_anomalies(
        db,
        target_date=target_date,
    )

    summary = get_dashboard_summary(
        db,
        target_date=target_date,
    )

    status_breakdown_today = build_status_breakdown_from_latest_events(
        latest_events
    )

    anomaly_breakdown_today = build_anomaly_breakdown(
        today_anomalies
    )

    faculty_profiles = db.execute(select(Student)).scalars().all()
    faculty_ids = {
        item.id
        for item in faculty_profiles
        if is_faculty_profile(db, item)
    }

    faculty_latest_events = [
        event for event in latest_events
        if int(event.student_id) in faculty_ids
    ]
    faculty_status_counts: dict[str, int] = {}
    for event in faculty_latest_events:
        status = _safe_status(event.status)
        faculty_status_counts[status] = faculty_status_counts.get(status, 0) + 1

    classroom_stmt = (
        select(ClassroomObservation)
        .where(ClassroomObservation.observed_at >= _today_window_utc(target_date)[0])
        .where(ClassroomObservation.observed_at <= _today_window_utc(target_date)[1])
        .order_by(ClassroomObservation.observed_at.desc(), ClassroomObservation.id.desc())
    )
    classroom_observations = db.execute(classroom_stmt).scalars().all()
    classroom_attention_count = sum(
        1
        for item in classroom_observations
        if (item.anomaly_signals or {}).get("needs_attention") is True
    )
    average_discipline = round(
        sum(item.discipline_score for item in classroom_observations) / len(classroom_observations),
        2,
    ) if classroom_observations else None
    average_teaching_quality = round(
        sum(item.teaching_quality_score for item in classroom_observations) / len(classroom_observations),
        2,
    ) if classroom_observations else None
    average_student_engagement = round(
        sum(item.student_engagement_score for item in classroom_observations) / len(classroom_observations),
        2,
    ) if classroom_observations else None

    recurrent_anomaly_profiles = {}
    for anomaly in today_anomalies:
        recurrent_anomaly_profiles[anomaly.student_id] = recurrent_anomaly_profiles.get(anomaly.student_id, 0) + 1
    recurrent_discipline_cases = sum(1 for count in recurrent_anomaly_profiles.values() if count >= 2)

    return {
        "summary": summary,
        "status_breakdown_today": status_breakdown_today,
        "anomaly_breakdown_today": anomaly_breakdown_today,
        "faculty_summary": {
            "total_faculty": len(faculty_ids),
            "faculty_checked_in_today": len(faculty_latest_events),
            "faculty_present_today": faculty_status_counts.get(AttendanceStatus.PRESENT.value, 0),
            "faculty_late_today": faculty_status_counts.get(AttendanceStatus.LATE.value, 0),
            "faculty_needs_review_today": faculty_status_counts.get(AttendanceStatus.NEEDS_REVIEW.value, 0),
            "recurrent_discipline_cases_today": recurrent_discipline_cases,
        },
        "classroom_quality": {
            "sessions_observed_today": len(classroom_observations),
            "sessions_needing_attention_today": classroom_attention_count,
            "average_discipline_score": average_discipline,
            "average_teaching_quality_score": average_teaching_quality,
            "average_student_engagement_score": average_student_engagement,
        },
        "district_overview": {
            "districts_covered": len({
                (item.district or "").strip().lower()
                for item in db.execute(select(Industry)).scalars().all()
                if (item.district or "").strip()
            }),
            "pending_reviews": summary.get("pending_reviews", 0),
            "anomalies_today": summary.get("anomalies_today", 0),
            "classroom_alerts_today": classroom_attention_count,
        },
    }


def get_attendance_analytics(
    db: Session,
    *,
    start_date: date,
    end_date: date,
) -> dict[str, Any]:
    """
    Returns day-by-day attendance analytics for the given date range.

    For each calendar day in [start_date, end_date]:
    - total active rosters (expected attendees)
    - checked-in count (unique students with any event)
    - present / late / absent / needs_review / face_mismatch / outside_geofence counts
    - anomaly count
    - attendance_percentage
    """
    if end_date < start_date:
        raise ValueError("end_date must be >= start_date.")

    max_days = 90
    delta = (end_date - start_date).days + 1
    if delta > max_days:
        raise ValueError(f"Date range too large. Maximum is {max_days} days.")

    days = [start_date + timedelta(days=i) for i in range(delta)]
    results: list[dict[str, Any]] = []

    for day in days:
        target_dt = datetime.combine(day, time.min, tzinfo=timezone.utc)
        day_summary = get_dashboard_summary(db, target_date=target_dt)

        anomalies_today = get_today_anomalies(db, target_date=target_dt)

        results.append({
            "date": day.isoformat(),
            "active_rosters": day_summary["active_rosters_today"],
            "checked_in": day_summary["checked_in_students_today"],
            "present": day_summary["present_today"],
            "late": day_summary["late_today"],
            "absent": day_summary["absent_today"],
            "outside_geofence": day_summary["outside_geofence_today"],
            "face_mismatch": day_summary["face_mismatch_today"],
            "needs_review": day_summary["needs_review_today"],
            "anomaly_count": len(anomalies_today),
            "attendance_percentage": day_summary["attendance_percentage"],
        })

    totals: dict[str, Any] = {k: 0 for k in ("present", "late", "absent", "anomaly_count")}
    for r in results:
        for k in totals:
            totals[k] += r[k]

    avg_pct = round(
        sum(r["attendance_percentage"] for r in results) / len(results), 2
    ) if results else 0.0

    return {
        "start_date": start_date.isoformat(),
        "end_date": end_date.isoformat(),
        "days_analysed": len(results),
        "totals": totals,
        "average_attendance_percentage": avg_pct,
        "daily": results,
    }


def get_dashboard_overview(
    db: Session,
    *,
    target_date: datetime | None = None,
) -> dict[str, Any]:
    """
    Alias for compatibility with older API code.
    """
    return get_dashboard_data(db, target_date=target_date)


def run_dashboard_self_test() -> dict[str, Any]:
    """
    Self-test against real Neon DB.

    This does not insert data.
    It reads:
    - students
    - industries
    - rosters
    - latest attendance events per student
    - anomaly flags
    """
    db = SessionLocal()

    try:
        dashboard_data = get_dashboard_data(db)

        return {
            "dashboard_self_test": "passed",
            "summary": dashboard_data["summary"],
            "status_breakdown_today": dashboard_data["status_breakdown_today"],
            "anomaly_breakdown_today": dashboard_data["anomaly_breakdown_today"],
        }

    finally:
        db.close()


if __name__ == "__main__":
    result = run_dashboard_self_test()
    print(result)
