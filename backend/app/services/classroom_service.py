from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.database_models import ClassroomObservation
from app.schemas.api_schemas import ClassroomObservationCreate
from app.services.crud_service import get_industry_by_id, get_student_by_id


def compute_composite_score(
    discipline_score: float,
    teaching_quality_score: float,
    student_engagement_score: float,
) -> float:
    """
    Weighted composite session quality score (0-100).

    Weights: teaching quality 40%, discipline 35%, student engagement 25%.
    """
    return round(
        teaching_quality_score * 0.40
        + discipline_score * 0.35
        + student_engagement_score * 0.25,
        2,
    )


def _performance_tier(composite: float) -> str:
    if composite >= 80:
        return "excellent"
    if composite >= 65:
        return "satisfactory"
    if composite >= 50:
        return "needs_improvement"
    return "critical"


def _build_anomaly_signals_from_scores(
    session_status: str,
    discipline_score: float,
    teaching_quality_score: float,
    student_engagement_score: float,
) -> dict:
    alerts: list[str] = []

    if session_status in {"late_start", "absent_faculty", "needs_review"}:
        alerts.append(session_status)
    if discipline_score < 60:
        alerts.append("discipline_breach_risk")
    if teaching_quality_score < 60:
        alerts.append("teaching_quality_risk")
    if student_engagement_score < 60:
        alerts.append("low_student_engagement")

    composite = compute_composite_score(discipline_score, teaching_quality_score, student_engagement_score)

    return {
        "count": len(alerts),
        "items": alerts,
        "needs_attention": bool(alerts),
        "composite_score": composite,
        "performance_tier": _performance_tier(composite),
    }


def _build_anomaly_signals(payload: ClassroomObservationCreate) -> dict:
    return _build_anomaly_signals_from_scores(
        session_status=payload.session_status,
        discipline_score=payload.discipline_score,
        teaching_quality_score=payload.teaching_quality_score,
        student_engagement_score=payload.student_engagement_score,
    )


def create_classroom_observation(
    db: Session,
    *,
    payload: ClassroomObservationCreate,
    observer_user_id: int | None,
) -> ClassroomObservation:
    faculty = get_student_by_id(db, payload.faculty_id)
    if not faculty:
        raise ValueError(f"Faculty profile not found with id: {payload.faculty_id}")

    if payload.industry_id is not None and not get_industry_by_id(db, payload.industry_id):
        raise ValueError(f"Location not found with id: {payload.industry_id}")

    observation = ClassroomObservation(
        faculty_id=payload.faculty_id,
        industry_id=payload.industry_id,
        observer_user_id=observer_user_id,
        observed_at=payload.observed_at or datetime.now(timezone.utc),
        session_status=payload.session_status.strip().lower(),
        discipline_score=float(payload.discipline_score),
        teaching_quality_score=float(payload.teaching_quality_score),
        student_engagement_score=float(payload.student_engagement_score),
        notes=payload.notes,
        evidence_metadata={
            "captured_from": "manual_supervision_console",
            "explainability": {
                "discipline_score": payload.discipline_score,
                "teaching_quality_score": payload.teaching_quality_score,
                "student_engagement_score": payload.student_engagement_score,
            },
        },
        anomaly_signals=_build_anomaly_signals(payload),
    )

    db.add(observation)
    db.commit()
    db.refresh(observation)
    return observation


def recompute_observation_signals(
    db: Session,
    *,
    observation_id: int,
) -> ClassroomObservation:
    """
    Retroactively recomputes anomaly_signals for a single observation.

    Use after score corrections or when the scoring formula is updated.
    """
    observation = db.get(ClassroomObservation, observation_id)
    if not observation:
        raise ValueError(f"Classroom observation {observation_id} not found.")

    observation.anomaly_signals = _build_anomaly_signals_from_scores(
        session_status=observation.session_status,
        discipline_score=observation.discipline_score,
        teaching_quality_score=observation.teaching_quality_score,
        student_engagement_score=observation.student_engagement_score,
    )

    db.commit()
    db.refresh(observation)
    return observation


def bulk_recompute_all_signals(db: Session) -> dict:
    """
    Retroactively recomputes anomaly_signals for every observation in the database.

    Returns counts of updated and skipped records.
    """
    observations = db.execute(select(ClassroomObservation)).scalars().all()

    updated = 0
    for obs in observations:
        obs.anomaly_signals = _build_anomaly_signals_from_scores(
            session_status=obs.session_status,
            discipline_score=obs.discipline_score,
            teaching_quality_score=obs.teaching_quality_score,
            student_engagement_score=obs.student_engagement_score,
        )
        updated += 1

    db.commit()
    return {"total_observations": len(observations), "updated": updated}


def list_classroom_observations(
    db: Session,
    *,
    faculty_id: int | None = None,
    limit: int = 100,
) -> list[ClassroomObservation]:
    stmt = select(ClassroomObservation).order_by(
        ClassroomObservation.observed_at.desc(),
        ClassroomObservation.id.desc(),
    )

    if faculty_id is not None:
        stmt = stmt.where(ClassroomObservation.faculty_id == faculty_id)

    stmt = stmt.limit(limit)
    return db.execute(stmt).scalars().all()
