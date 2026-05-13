from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.api.dependencies import require_admin, require_supervisor_or_above
from app.db.database import get_db
from app.models.database_models import ClassroomObservation, User
from app.schemas.api_schemas import ClassroomObservationCreate, ClassroomObservationResponse
from app.services.classroom_service import (
    bulk_recompute_all_signals,
    create_classroom_observation,
    list_classroom_observations,
    recompute_observation_signals,
)


router = APIRouter(
    prefix="/api/v1/classroom-observations",
    tags=["Classroom Monitoring"],
)


def _serialize(item: ClassroomObservation) -> dict:
    return {
        "id": item.id,
        "faculty_id": item.faculty_id,
        "industry_id": item.industry_id,
        "observer_user_id": item.observer_user_id,
        "observed_at": item.observed_at,
        "session_status": item.session_status,
        "discipline_score": item.discipline_score,
        "teaching_quality_score": item.teaching_quality_score,
        "student_engagement_score": item.student_engagement_score,
        "notes": item.notes,
        "evidence_metadata": item.evidence_metadata,
        "anomaly_signals": item.anomaly_signals,
        "created_at": item.created_at,
    }


@router.post("", response_model=ClassroomObservationResponse)
def create_observation(
    payload: ClassroomObservationCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_supervisor_or_above),
):
    try:
        observation = create_classroom_observation(
            db,
            payload=payload,
            observer_user_id=current_user.id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return _serialize(observation)


@router.post("/{observation_id}/recompute")
def recompute_observation(
    observation_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_supervisor_or_above),
):
    """
    Recomputes anomaly_signals (including composite score and performance tier)
    for a single classroom observation.
    """
    try:
        observation = recompute_observation_signals(db, observation_id=observation_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    return _serialize(observation)


@router.post("/recompute-all")
def recompute_all_observations(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """
    Retroactively recomputes anomaly_signals for all classroom observations.

    Admin-only. Use after scoring formula updates or initial data imports.
    """
    result = bulk_recompute_all_signals(db)
    result["requested_by"] = {
        "user_id": current_user.id,
        "username": current_user.username,
        "role": current_user.role,
    }
    return result


@router.get("", response_model=list[ClassroomObservationResponse])
def list_observations(
    faculty_id: int | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_supervisor_or_above),
):
    return [_serialize(item) for item in list_classroom_observations(db, faculty_id=faculty_id, limit=limit)]
