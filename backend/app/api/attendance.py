from __future__ import annotations

from datetime import date, datetime, time, timezone
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import FileResponse, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.dependencies import get_current_user, require_attendance_user, require_supervisor_or_above
from app.db.database import get_db
from app.models.database_models import (
    AttendanceEvent,
    Industry,
    Student,
    TrainingRoster,
    User,
)
from app.schemas.api_schemas import AttendanceCheckInRequest, AttendanceCheckOutRequest
from app.services.attendance_service import process_check_in, process_check_out
from app.services.crud_service import get_student_by_code
from app.services.export_service import export_attendance_events_excel
from app.services.faculty_service import get_profile_for_user, profile_type_for_student


router = APIRouter(
    prefix="/api/v1/attendance",
    tags=["Attendance & Anomalies"],
)


def _today_window_utc() -> tuple[datetime, datetime]:
    now = datetime.now(timezone.utc)
    start_dt = datetime.combine(now.date(), time.min, tzinfo=timezone.utc)
    end_dt = datetime.combine(now.date(), time.max, tzinfo=timezone.utc)
    return start_dt, end_dt


def _date_window_utc(date_value: str | None) -> tuple[datetime, datetime] | None:
    """
    Parses YYYY-MM-DD into a UTC day window.
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

    start_dt = datetime.combine(parsed_date, time.min, tzinfo=timezone.utc)
    end_dt = datetime.combine(parsed_date, time.max, tzinfo=timezone.utc)

    return start_dt, end_dt


def _safe_iso(value: Any) -> str | None:
    if value is None:
        return None

    if hasattr(value, "isoformat"):
        return value.isoformat()

    return str(value)


def _backend_root() -> Path:
    """
    Returns backend project root.

    Current file:
    backend/app/api/attendance.py

    parents[0] = api
    parents[1] = app
    parents[2] = backend
    """
    return Path(__file__).resolve().parents[2]


def _resolve_selfie_file_path(selfie_evidence: dict[str, Any]) -> Path | None:
    """
    Safely resolves saved selfie path inside backend/storage/uploads.

    Preferred metadata:
    relative_path = attendance_selfies/2026-05-05/student_1/event_x.jpg
    """
    if not selfie_evidence or selfie_evidence.get("saved") is not True:
        return None

    root = _backend_root()
    uploads_root = (root / "storage" / "uploads").resolve()

    relative_path = selfie_evidence.get("relative_path")

    if relative_path:
        candidate = (uploads_root / str(relative_path)).resolve()

        try:
            candidate.relative_to(uploads_root)
        except ValueError:
            return None

        return candidate

    absolute_path = selfie_evidence.get("absolute_path")

    if absolute_path:
        candidate = Path(str(absolute_path))

        if not candidate.is_absolute():
            candidate = (root / candidate).resolve()
        else:
            candidate = candidate.resolve()

        try:
            candidate.relative_to(uploads_root)
        except ValueError:
            return None

        return candidate

    return None


def _student_payload(student: Student | None, db: Session) -> dict[str, Any] | None:
    if not student:
        return None

    return {
        "id": student.id,
        "student_code": getattr(student, "student_code", None),
        "full_name": getattr(student, "full_name", None),
        "iti_name": getattr(student, "iti_name", None),
        "trade": getattr(student, "trade", None),
        "batch": getattr(student, "batch", None),
        "mobile": getattr(student, "mobile", None),
        "email": getattr(student, "email", None),
        "face_enrolled": getattr(student, "face_enrolled", None),
        "consent_status": getattr(student, "consent_status", None),
        "profile_type": profile_type_for_student(db, student),
    }


def _industry_payload(industry: Industry | None) -> dict[str, Any] | None:
    if not industry:
        return None

    return {
        "id": industry.id,
        "industry_code": getattr(industry, "industry_code", None),
        "name": getattr(industry, "name", None),
        "district": getattr(industry, "district", None),
        "city": getattr(industry, "city", None),
        "latitude": getattr(industry, "latitude", None),
        "longitude": getattr(industry, "longitude", None),
        "geofence_radius_meters": getattr(industry, "geofence_radius_meters", None),
        "hr_name": getattr(industry, "hr_name", None),
        "supervisor_name": getattr(industry, "supervisor_name", None),
    }


def _roster_payload(roster: TrainingRoster | None) -> dict[str, Any] | None:
    if not roster:
        return None

    return {
        "id": roster.id,
        "student_id": getattr(roster, "student_id", None),
        "industry_id": getattr(roster, "industry_id", None),
        "start_date": str(getattr(roster, "start_date", None)),
        "end_date": str(getattr(roster, "end_date", None)),
        "shift_start_time": str(getattr(roster, "shift_start_time", None)),
        "shift_end_time": str(getattr(roster, "shift_end_time", None)),
        "is_active": getattr(roster, "is_active", None),
    }


def serialize_attendance_event(event: AttendanceEvent, db: Session) -> dict[str, Any]:
    raw_metadata = event.raw_metadata or {}

    face_result = raw_metadata.get("face_result") or {}
    geo_result = raw_metadata.get("geo_result") or {}
    schedule_result = raw_metadata.get("schedule_result") or {}
    selfie_evidence = raw_metadata.get("selfie_evidence") or {}

    student = db.get(Student, event.student_id) if event.student_id else None
    industry = db.get(Industry, event.industry_id) if event.industry_id else None
    roster = db.get(TrainingRoster, event.roster_id) if event.roster_id else None

    student_data = _student_payload(student, db)
    industry_data = _industry_payload(industry)
    roster_data = _roster_payload(roster)

    return {
        "id": event.id,
        "student_id": event.student_id,
        "industry_id": event.industry_id,
        "roster_id": event.roster_id,
        "student": student_data,
        "industry": industry_data,
        "roster": roster_data,
        "student_name": student_data.get("full_name") if student_data else None,
        "student_code": student_data.get("student_code") if student_data else None,
        "student_trade": student_data.get("trade") if student_data else None,
        "student_batch": student_data.get("batch") if student_data else None,
        "iti_name": student_data.get("iti_name") if student_data else None,
        "industry_name": industry_data.get("name") if industry_data else None,
        "industry_code": industry_data.get("industry_code") if industry_data else None,
        "industry_city": industry_data.get("city") if industry_data else None,
        "industry_district": industry_data.get("district") if industry_data else None,
        "event_type": event.event_type,
        "status": event.status,
        "event_time": _safe_iso(event.event_time),
        "latitude": event.latitude,
        "longitude": event.longitude,
        "gps_accuracy_meters": event.gps_accuracy_meters,
        "distance_from_industry_meters": event.distance_from_industry_meters,
        "face_match_score": event.face_match_score,
        "liveness_score": event.liveness_score,
        "device_id": event.device_id,
        "browser_info": event.browser_info,
        "ip_address": event.ip_address,
        "decision_reason": event.decision_reason,
        "face_result": face_result,
        "geo_result": geo_result,
        "schedule_result": schedule_result,
        "selfie_evidence": selfie_evidence,
        "created_at": _safe_iso(getattr(event, "created_at", None)),
    }


@router.post("/check-in")
def check_in_attendance(
    payload: AttendanceCheckInRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_attendance_user),
):
    """
    Student attendance check-in.

    Uses:
    - GPS / geofence validation
    - pretrained face verification when enrolled
    - selfie evidence storage
    - anomaly creation
    """
    if current_user.role in {"student", "faculty"}:
        linked_student = get_profile_for_user(db, current_user)
        if not linked_student:
            raise HTTPException(status_code=403, detail="Logged-in account is not linked to an attendance profile.")
        if payload.student_id and payload.student_id != linked_student.id:
            raise HTTPException(status_code=403, detail="Profile-linked accounts can only mark attendance for their own profile.")
        payload.student_id = linked_student.id

    try:
        result = process_check_in(
            db,
            payload=payload,
            ip_address=request.client.host if request.client else None,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    result["requested_by"] = {
        "user_id": current_user.id,
        "username": current_user.username,
        "role": current_user.role,
    }

    return result


@router.post("/check-out")
def check_out_attendance(
    payload: AttendanceCheckOutRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_attendance_user),
):
    """
    Student attendance check-out.

    Uses the same multi-factor verification path as check-in,
    but evaluates early exit instead of late arrival.
    """
    if current_user.role in {"student", "faculty"}:
        linked_student = get_profile_for_user(db, current_user)
        if not linked_student:
            raise HTTPException(status_code=403, detail="Logged-in account is not linked to an attendance profile.")
        if payload.student_id and payload.student_id != linked_student.id:
            raise HTTPException(status_code=403, detail="Profile-linked accounts can only mark attendance for their own profile.")
        payload.student_id = linked_student.id

    try:
        result = process_check_out(
            db,
            payload=payload,
            ip_address=request.client.host if request.client else None,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    result["requested_by"] = {
        "user_id": current_user.id,
        "username": current_user.username,
        "role": current_user.role,
    }

    return result


@router.get("/events")
def list_attendance_events(
    student_id: int | None = Query(default=None),
    status: str | None = Query(default=None),
    date: str | None = Query(default=None, description="Optional date in YYYY-MM-DD format"),
    today_only: bool = Query(default=False),
    limit: int = Query(default=100, ge=1, le=500),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_supervisor_or_above),
):
    """
    Lists attendance event history.

    Filtering priority:
    1. If date=YYYY-MM-DD is provided, filter that date.
    2. Else if today_only=true, filter current UTC date.
    3. Else return recent events.
    """
    stmt = select(AttendanceEvent)

    date_window = _date_window_utc(date)

    if date_window:
        start_dt, end_dt = date_window
        stmt = stmt.where(AttendanceEvent.event_time >= start_dt)
        stmt = stmt.where(AttendanceEvent.event_time <= end_dt)
    elif today_only:
        start_dt, end_dt = _today_window_utc()
        stmt = stmt.where(AttendanceEvent.event_time >= start_dt)
        stmt = stmt.where(AttendanceEvent.event_time <= end_dt)

    if student_id is not None:
        stmt = stmt.where(AttendanceEvent.student_id == student_id)

    if status:
        stmt = stmt.where(AttendanceEvent.status == status)

    stmt = stmt.order_by(AttendanceEvent.event_time.desc(), AttendanceEvent.id.desc())
    stmt = stmt.limit(limit)

    events = db.execute(stmt).scalars().all()

    return [
        serialize_attendance_event(event, db)
        for event in events
    ]


@router.get("/events/{event_id}/selfie")
def get_attendance_event_selfie(
    event_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_supervisor_or_above),
):
    """
    Returns saved selfie evidence for one attendance event.

    This route is authenticated.
    Do not expose storage/uploads publicly. This is biometric evidence, not clip art.
    """
    event = db.get(AttendanceEvent, event_id)

    if not event:
        raise HTTPException(status_code=404, detail="Attendance event not found")

    raw_metadata = event.raw_metadata or {}
    selfie_evidence = raw_metadata.get("selfie_evidence") or {}

    if selfie_evidence.get("saved") is not True:
        raise HTTPException(
            status_code=404,
            detail="No saved selfie evidence found for this attendance event.",
        )

    file_path = _resolve_selfie_file_path(selfie_evidence)

    if not file_path or not file_path.exists() or not file_path.is_file():
        raise HTTPException(
            status_code=404,
            detail="Selfie evidence file not found on server.",
        )

    media_type = selfie_evidence.get("mime_type") or "image/jpeg"

    return FileResponse(
        path=str(file_path),
        media_type=media_type,
        filename=file_path.name,
    )


@router.get("/events/{event_id}")
def get_attendance_event(
    event_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_supervisor_or_above),
):
    """
    Gets one attendance event with student, industry, roster, decision, and evidence metadata.
    """
    event = db.get(AttendanceEvent, event_id)

    if not event:
        raise HTTPException(status_code=404, detail="Attendance event not found")

    return serialize_attendance_event(event, db)


@router.get("/my-events")
def get_my_attendance_events(
    limit: int = Query(default=50, ge=1, le=200),
    date: str | None = Query(default=None, description="Filter by date YYYY-MM-DD"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Returns the authenticated student's or faculty's own attendance history.
    Students and faculty can only see their own records via this endpoint.
    """
    from app.services.faculty_service import get_profile_for_user

    linked_student = get_profile_for_user(db, current_user)
    if not linked_student:
        raise HTTPException(
            status_code=404,
            detail="No attendance profile linked to this account.",
        )

    stmt = select(AttendanceEvent).where(AttendanceEvent.student_id == linked_student.id)

    date_window = _date_window_utc(date)
    if date_window:
        start_dt, end_dt = date_window
        stmt = stmt.where(AttendanceEvent.event_time >= start_dt)
        stmt = stmt.where(AttendanceEvent.event_time <= end_dt)

    stmt = stmt.order_by(AttendanceEvent.event_time.desc(), AttendanceEvent.id.desc()).limit(limit)
    events = db.execute(stmt).scalars().all()

    return {
        "student_id": linked_student.id,
        "student_code": linked_student.student_code,
        "full_name": linked_student.full_name,
        "events": [serialize_attendance_event(e, db) for e in events],
        "total_returned": len(events),
    }


@router.get("/export")
def export_attendance_events(
    start_date: str | None = Query(default=None, description="Start date YYYY-MM-DD"),
    end_date: str | None = Query(default=None, description="End date YYYY-MM-DD"),
    student_id: int | None = Query(default=None),
    status: str | None = Query(default=None),
    limit: int = Query(default=5000, ge=1, le=10000),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_supervisor_or_above),
):
    """
    Exports attendance events to Excel (.xlsx).

    Returns a downloadable file with student, industry, face/GPS scores, and decision reason.
    """
    def _parse(val: str | None) -> date | None:
        if not val:
            return None
        try:
            return date.fromisoformat(val)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=f"Invalid date '{val}'. Use YYYY-MM-DD.") from exc

    xlsx_bytes = export_attendance_events_excel(
        db,
        start_date=_parse(start_date),
        end_date=_parse(end_date),
        student_id=student_id,
        status=status,
        limit=limit,
    )

    filename = f"attendance_events_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}.xlsx"

    return Response(
        content=xlsx_bytes,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


@router.get("/health")
def attendance_api_health(
    current_user: User = Depends(require_attendance_user),
):
    return {
        "status": "passed",
        "message": "Attendance API is active.",
        "requested_by": {
            "user_id": current_user.id,
            "username": current_user.username,
            "role": current_user.role,
        },
    }
