from __future__ import annotations

from datetime import date, datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.api.dependencies import require_supervisor_or_above
from app.db.database import SessionLocal, get_db
from app.models.database_models import User
from app.services.dashboard_service import (
    get_attendance_analytics,
    get_dashboard_data,
    get_dashboard_summary,
    get_latest_attendance_events_by_student_today,
    get_today_anomalies,
    build_status_breakdown_from_latest_events,
    build_anomaly_breakdown,
)


router = APIRouter(
    prefix="/api/v1/dashboard",
    tags=["Dashboard"],
)


def _parse_target_date(date_value: str | None) -> datetime | None:
    """
    Optional dashboard date parser.

    Input format:
    YYYY-MM-DD

    If no date is provided, dashboard_service uses current UTC date.
    """
    if not date_value:
        return None

    try:
        parsed_date = datetime.strptime(date_value, "%Y-%m-%d").date()
    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail="date must be in YYYY-MM-DD format.",
        ) from exc

    return datetime.combine(parsed_date, datetime.min.time(), tzinfo=timezone.utc)


@router.get("/summary")
def dashboard_summary(
    date: str | None = Query(default=None, description="Optional date in YYYY-MM-DD format"),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_supervisor_or_above),
):
    """
    Main dashboard endpoint used by frontend index.html.

    Returns:
    - summary
    - status_breakdown_today
    - anomaly_breakdown_today
    """
    target_date = _parse_target_date(date)

    data = get_dashboard_data(db, target_date=target_date)

    data["requested_by"] = {
        "user_id": current_user.id,
        "username": current_user.username,
        "role": current_user.role,
    }

    return data


@router.get("/overview")
def dashboard_overview(
    date: str | None = Query(default=None, description="Optional date in YYYY-MM-DD format"),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_supervisor_or_above),
):
    """
    Alias endpoint for dashboard summary.
    Useful if older frontend/API calls use /overview.
    """
    target_date = _parse_target_date(date)

    data = get_dashboard_data(db, target_date=target_date)

    data["requested_by"] = {
        "user_id": current_user.id,
        "username": current_user.username,
        "role": current_user.role,
    }

    return data


@router.get("/status-breakdown")
def dashboard_status_breakdown(
    date: str | None = Query(default=None, description="Optional date in YYYY-MM-DD format"),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_supervisor_or_above),
):
    """
    Returns status breakdown based on latest attendance event per student.
    """
    target_date = _parse_target_date(date)

    latest_events = get_latest_attendance_events_by_student_today(
        db,
        target_date=target_date,
    )

    return {
        "items": build_status_breakdown_from_latest_events(latest_events),
        "requested_by": {
            "user_id": current_user.id,
            "username": current_user.username,
            "role": current_user.role,
        },
    }


@router.get("/anomaly-breakdown")
def dashboard_anomaly_breakdown(
    date: str | None = Query(default=None, description="Optional date in YYYY-MM-DD format"),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_supervisor_or_above),
):
    """
    Returns anomaly breakdown for anomaly flags created today.
    """
    target_date = _parse_target_date(date)

    anomalies = get_today_anomalies(
        db,
        target_date=target_date,
    )

    return {
        "items": build_anomaly_breakdown(anomalies),
        "requested_by": {
            "user_id": current_user.id,
            "username": current_user.username,
            "role": current_user.role,
        },
    }


@router.get("/analytics")
def dashboard_analytics(
    start_date: str = Query(..., description="Start date in YYYY-MM-DD format"),
    end_date: str = Query(..., description="End date in YYYY-MM-DD format"),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_supervisor_or_above),
):
    """
    Historical attendance analytics for a date range (max 90 days).

    Returns day-by-day breakdown: checked_in, present, late, absent,
    outside_geofence, face_mismatch, needs_review, anomaly_count,
    attendance_percentage — plus totals and average percentage.
    """
    try:
        parsed_start = date.fromisoformat(start_date)
        parsed_end = date.fromisoformat(end_date)
    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail="start_date and end_date must be in YYYY-MM-DD format.",
        ) from exc

    try:
        result = get_attendance_analytics(db, start_date=parsed_start, end_date=parsed_end)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    result["requested_by"] = {
        "user_id": current_user.id,
        "username": current_user.username,
        "role": current_user.role,
    }

    return result


@router.get("/health")
def dashboard_api_health(
    current_user: User = Depends(require_supervisor_or_above),
):
    """
    Confirms dashboard API router is active.
    """
    return {
        "status": "passed",
        "message": "Dashboard API is active.",
        "requested_by": {
            "user_id": current_user.id,
            "username": current_user.username,
            "role": current_user.role,
        },
    }


def run_dashboard_api_self_test() -> dict:
    """
    Real DB dashboard API self-test without FastAPI request context.
    """
    db = SessionLocal()

    try:
        data = get_dashboard_data(db)

        return {
            "dashboard_api_self_test": "passed",
            "summary": data["summary"],
            "status_breakdown_today": data["status_breakdown_today"],
            "anomaly_breakdown_today": data["anomaly_breakdown_today"],
        }

    finally:
        db.close()


if __name__ == "__main__":
    result = run_dashboard_api_self_test()
    print(result)