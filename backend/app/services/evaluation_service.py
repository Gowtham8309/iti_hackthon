from __future__ import annotations

from datetime import datetime, timezone
from statistics import mean

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.database_models import (
    AnomalyFlag,
    AttendanceEvent,
    ClassroomObservation,
    Industry,
    ReviewStatus,
    Student,
    TrainingRoster,
)
from app.services.attendance_state_service import compute_daily_attendance_states
from app.services.faculty_service import is_faculty_profile


def _percentage(numerator: int, denominator: int) -> float:
    if denominator <= 0:
        return 0.0
    return round((numerator / denominator) * 100, 2)


def build_evaluation_report(
    db: Session,
    *,
    target_date: datetime | None = None,
) -> dict:
    run_at = datetime.now(timezone.utc)
    states = compute_daily_attendance_states(db, target_date=target_date)

    total_students = int(db.execute(select(func.count()).select_from(Student)).scalar() or 0)
    people = db.execute(select(Student)).scalars().all()
    total_faculty = sum(1 for item in people if is_faculty_profile(db, item))
    total_industries = int(db.execute(select(func.count()).select_from(Industry)).scalar() or 0)
    total_rosters = int(db.execute(select(func.count()).select_from(TrainingRoster)).scalar() or 0)
    active_rosters = int(
        db.execute(
            select(func.count())
            .select_from(TrainingRoster)
            .where(TrainingRoster.is_active.is_(True))
        ).scalar()
        or 0
    )
    enrolled_students = int(
        db.execute(
            select(func.count()).select_from(Student).where(Student.face_enrolled.is_(True))
        ).scalar()
        or 0
    )
    consented_students = int(
        db.execute(
            select(func.count()).select_from(Student).where(Student.consent_status.is_(True))
        ).scalar()
        or 0
    )

    events = db.execute(select(AttendanceEvent)).scalars().all()
    anomalies = db.execute(select(AnomalyFlag)).scalars().all()
    classroom_observations = db.execute(select(ClassroomObservation)).scalars().all()

    face_scores = [float(event.face_match_score) for event in events if event.face_match_score is not None]
    liveness_scores = [float(event.liveness_score) for event in events if event.liveness_score is not None]
    geofence_breaches = sum(1 for event in events if event.status == "outside_geofence")
    needs_review_events = sum(1 for event in events if event.status == "needs_review")
    pending_anomalies = sum(1 for anomaly in anomalies if anomaly.review_status == ReviewStatus.PENDING.value)
    escalated_anomalies = sum(1 for anomaly in anomalies if anomaly.review_status == ReviewStatus.ESCALATED.value)

    state_summary: dict[str, int] = {}
    for item in states:
        state_summary[item.state] = state_summary.get(item.state, 0) + 1

    missing_geofence_data = int(
        db.execute(
            select(func.count())
            .select_from(Industry)
            .where(Industry.latitude == 0.0)
            .where(Industry.longitude == 0.0)
        ).scalar()
        or 0
    )

    recommendations: list[str] = []
    if total_students and enrolled_students < total_students:
        recommendations.append("Increase face enrollment coverage before claiming face-recognition accuracy.")
    if total_students and consented_students < total_students:
        recommendations.append("Collect missing biometric consent records before expanding the pilot.")
    if missing_geofence_data:
        recommendations.append("Replace placeholder industry coordinates with real geofence centers.")
    if pending_anomalies:
        recommendations.append("Reduce pending anomaly review backlog to improve audit readiness.")
    if not face_scores:
        recommendations.append("Capture more attendance events with face scores before tuning thresholds.")
    if not classroom_observations:
        recommendations.append("Start classroom observation capture so teaching-quality KPIs are evidence-backed.")
    if not recommendations:
        recommendations.append("Operational telemetry is healthy enough for threshold tuning and pilot dry-runs.")

    evaluation_date = (target_date or run_at).date().isoformat()

    return {
        "generated_at": run_at.isoformat(),
        "evaluation_date": evaluation_date,
        "framework_mode": "no_labeled_data_framework_only",
        "summary": {
            "total_students": total_students,
            "total_faculty": total_faculty,
            "total_monitored_profiles": total_students,
            "total_industries": total_industries,
            "total_rosters": total_rosters,
            "active_rosters": active_rosters,
            "attendance_events": len(events),
            "anomaly_flags": len(anomalies),
            "pending_anomaly_reviews": pending_anomalies,
            "escalated_anomaly_reviews": escalated_anomalies,
        },
        "coverage": {
            "face_enrollment_pct": _percentage(enrolled_students, total_students),
            "biometric_consent_pct": _percentage(consented_students, total_students),
            "active_roster_pct": _percentage(active_rosters, total_rosters),
            "industries_with_placeholder_coordinates": missing_geofence_data,
        },
        "face_verification": {
            "events_with_face_scores": len(face_scores),
            "average_face_match_score": round(mean(face_scores), 4) if face_scores else None,
            "low_face_match_events": sum(1 for score in face_scores if score < 0.75),
            "events_with_liveness_scores": len(liveness_scores),
            "average_liveness_score": round(mean(liveness_scores), 4) if liveness_scores else None,
            "low_liveness_events": sum(1 for score in liveness_scores if score < 0.70),
        },
        "attendance_quality": {
            "daily_state_summary": state_summary,
            "needs_review_events": needs_review_events,
            "geofence_breaches": geofence_breaches,
            "anomalies_per_100_events": round((len(anomalies) / len(events)) * 100, 2) if events else 0.0,
        },
        "classroom_quality": {
            "sessions_observed": len(classroom_observations),
            "average_discipline_score": round(mean([item.discipline_score for item in classroom_observations]), 2) if classroom_observations else None,
            "average_teaching_quality_score": round(mean([item.teaching_quality_score for item in classroom_observations]), 2) if classroom_observations else None,
            "average_student_engagement_score": round(mean([item.student_engagement_score for item in classroom_observations]), 2) if classroom_observations else None,
            "sessions_needing_attention": sum(1 for item in classroom_observations if (item.anomaly_signals or {}).get("needs_attention") is True),
        },
        "review_pipeline": {
            "pending": pending_anomalies,
            "approved": sum(1 for anomaly in anomalies if anomaly.review_status == ReviewStatus.APPROVED.value),
            "rejected": sum(1 for anomaly in anomalies if anomaly.review_status == ReviewStatus.REJECTED.value),
            "escalated": escalated_anomalies,
        },
        "dataset_requirements": {
            "labeled_face_pairs_required": True,
            "labeled_spoof_samples_required": True,
            "labeled_anomaly_ground_truth_required": True,
            "current_status": "framework_ready_waiting_for_labeled_data",
        },
        "recommendations": recommendations,
    }
