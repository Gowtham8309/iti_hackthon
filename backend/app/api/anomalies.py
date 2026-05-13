from __future__ import annotations

from datetime import date, datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.dependencies import require_supervisor_or_above
from app.db.database import get_db
from app.models.database_models import AnomalyFlag, AttendanceEvent, ReviewStatus, Student, User
from app.schemas.api_schemas import AnomalyFlagResponse, AnomalyReviewRequest
from app.services.export_service import export_anomalies_excel
from app.services.faculty_service import profile_type_for_student
from app.services.notification_service import queue_notification


router = APIRouter(prefix="/api/v1/anomalies", tags=["Anomalies"])


def serialize_anomaly(anomaly: AnomalyFlag, db: Session) -> dict:
    student = db.get(Student, anomaly.student_id) if anomaly.student_id else None
    event = db.get(AttendanceEvent, anomaly.attendance_event_id) if anomaly.attendance_event_id else None

    return {
        "id": anomaly.id,
        "attendance_event_id": anomaly.attendance_event_id,
        "student_id": anomaly.student_id,
        "anomaly_type": anomaly.anomaly_type,
        "severity": anomaly.severity,
        "risk_score": anomaly.risk_score,
        "explanation": anomaly.explanation,
        "review_status": anomaly.review_status,
        "reviewed_by_user_id": anomaly.reviewed_by_user_id,
        "reviewed_at": anomaly.reviewed_at.isoformat() if anomaly.reviewed_at else None,
        "review_notes": anomaly.review_notes,
        "created_at": anomaly.created_at.isoformat() if anomaly.created_at else None,
        "student": (
            {
                "id": student.id,
                "student_code": student.student_code,
                "profile_code": student.student_code,
                "full_name": student.full_name,
                "iti_name": student.iti_name,
                "trade": student.trade,
                "batch": student.batch,
                "profile_type": profile_type_for_student(db, student),
            }
            if student
            else None
        ),
        "attendance_event": (
            {
                "id": event.id,
                "event_type": event.event_type,
                "status": event.status,
                "event_time": event.event_time.isoformat() if event.event_time else None,
                "decision_reason": event.decision_reason,
            }
            if event
            else None
        ),
    }


def _normalize_review_status(value: str) -> str:
    normalized = value.strip().lower()
    allowed = {
        ReviewStatus.APPROVED.value,
        ReviewStatus.REJECTED.value,
        ReviewStatus.ESCALATED.value,
    }

    if normalized not in allowed:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid review_status. Allowed values: {sorted(allowed)}",
        )

    return normalized


@router.get("/export")
def export_anomalies(
    start_date: str | None = Query(default=None, description="Start date YYYY-MM-DD"),
    end_date: str | None = Query(default=None, description="End date YYYY-MM-DD"),
    student_id: int | None = Query(default=None),
    severity: str | None = Query(default=None),
    review_status: str | None = Query(default=None),
    limit: int = Query(default=5000, ge=1, le=10000),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_supervisor_or_above),
):
    """
    Exports anomaly flags to Excel (.xlsx).

    Returns a downloadable file with student info, anomaly type, severity,
    risk score, and review status.
    """
    def _parse(val: str | None) -> date | None:
        if not val:
            return None
        try:
            return date.fromisoformat(val)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=f"Invalid date '{val}'. Use YYYY-MM-DD.") from exc

    xlsx_bytes = export_anomalies_excel(
        db,
        start_date=_parse(start_date),
        end_date=_parse(end_date),
        student_id=student_id,
        severity=severity,
        review_status=review_status,
        limit=limit,
    )

    filename = f"anomalies_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}.xlsx"

    return Response(
        content=xlsx_bytes,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


@router.get("/health/check")
def anomalies_api_health(
    current_user: User = Depends(require_supervisor_or_above),
):
    return {
        "status": "passed",
        "message": "Anomaly API is active.",
        "requested_by": {
            "user_id": current_user.id,
            "username": current_user.username,
            "role": current_user.role,
        },
    }


@router.get("", response_model=list[AnomalyFlagResponse])
def list_anomalies(
    student_id: int | None = Query(default=None),
    severity: str | None = Query(default=None),
    review_status: str | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_supervisor_or_above),
):
    stmt = select(AnomalyFlag)

    if student_id is not None:
        stmt = stmt.where(AnomalyFlag.student_id == student_id)

    if severity:
        stmt = stmt.where(AnomalyFlag.severity == severity.strip().lower())

    if review_status:
        stmt = stmt.where(AnomalyFlag.review_status == review_status.strip().lower())

    stmt = stmt.order_by(AnomalyFlag.created_at.desc(), AnomalyFlag.id.desc()).limit(limit)

    anomalies = db.execute(stmt).scalars().all()
    return [serialize_anomaly(item, db) for item in anomalies]


@router.get("/{anomaly_id}", response_model=AnomalyFlagResponse)
def get_anomaly(
    anomaly_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_supervisor_or_above),
):
    anomaly = db.get(AnomalyFlag, anomaly_id)

    if not anomaly:
        raise HTTPException(status_code=404, detail="Anomaly not found")

    return serialize_anomaly(anomaly, db)


@router.patch("/{anomaly_id}/review", response_model=AnomalyFlagResponse)
def review_anomaly(
    anomaly_id: int,
    payload: AnomalyReviewRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_supervisor_or_above),
):
    anomaly = db.get(AnomalyFlag, anomaly_id)

    if not anomaly:
        raise HTTPException(status_code=404, detail="Anomaly not found")

    anomaly.review_status = _normalize_review_status(payload.review_status)
    anomaly.review_notes = payload.review_notes
    anomaly.reviewed_by_user_id = payload.reviewed_by_user_id or current_user.id
    anomaly.reviewed_at = datetime.now(timezone.utc)

    student = db.get(Student, anomaly.student_id) if anomaly.student_id else None

    notification = queue_notification(
        db,
        action="anomaly_review_updated",
        entity_type="anomaly_flag",
        entity_id=str(anomaly.id),
        subject=f"Anomaly #{anomaly.id} marked as {anomaly.review_status}",
        message=anomaly.review_notes or f"Anomaly {anomaly.id} marked as {anomaly.review_status}.",
        student=student,
        user_id=current_user.id,
    )

    db.commit()
    db.refresh(anomaly)

    result = serialize_anomaly(anomaly, db)
    result["notifications_generated"] = [notification]
    return result
