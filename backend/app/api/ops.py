from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Body, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.dependencies import require_admin, require_supervisor_or_above
from app.db.database import get_db
from app.models.database_models import (
    AnomalyFlag,
    AttendanceEvent,
    ClassroomObservation,
    Industry,
    ReviewStatus,
    Student,
    TrainingRoster,
    User,
)
from app.schemas.api_schemas import PilotImportRequest
from app.services.attendance_state_service import compute_daily_attendance_states
from app.services.crud_service import geocode_industries_with_missing_coords, get_industry_by_id, get_student_by_id
from app.services.evaluation_service import build_evaluation_report
from app.services.integration_service import (
    build_anomaly_sync_payload,
    build_attendance_portal_payload,
    create_integration_audit_log,
    push_anomaly_to_district_dashboard,
    push_to_iti_portal,
)
from app.services.notification_service import queue_notification
from app.services.pilot_import_service import (
    auto_assign_rosters_from_ojt,
    build_roster_import_template,
    import_industries_from_ojt,
    import_students_from_admissions,
    load_pilot_data,
    preview_pilot_data,
)
from app.services.faculty_service import is_faculty_profile
from app.scripts.demo_reset import reset_demo_data
from app.scripts.seed_all_demo_data import seed_all_demo_data
from app.services.notification_service import send_email_notification
from app.services.sms_service import send_sms


router = APIRouter(
    prefix="/api/v1/ops",
    tags=["Operations"],
)


@router.post("/demo/reset")
def run_demo_reset(
    keep_faculty_face_enrollment: bool = Query(default=True),
    keep_student_face_enrollment: bool = Query(default=False),
    strict_master_data: bool = Query(default=True),
    current_user: User = Depends(require_admin),
):
    result = reset_demo_data(
        keep_faculty_face_enrollment=keep_faculty_face_enrollment,
        keep_student_face_enrollment=keep_student_face_enrollment,
        strict_master_data=strict_master_data,
    )
    result["requested_by"] = {
        "user_id": current_user.id,
        "username": current_user.username,
        "role": current_user.role,
    }
    return result


class _NotificationTestRequest(BaseModel):
    channel: str = Field(..., description="'email', 'sms', or 'both'")
    email: str | None = Field(default=None, description="Target email address")
    mobile: str | None = Field(default=None, description="Target mobile number (10 digits)")
    subject: str = "ITI Attendance — Test Notification"
    message: str = "This is a test notification from the ITI Attendance AI system."


@router.post("/notify/test")
def test_notification(
    payload: _NotificationTestRequest = Body(...),
    current_user: User = Depends(require_admin),
):
    """
    Send a test email and/or SMS to verify notification credentials.
    Requires EMAIL_NOTIFICATIONS_ENABLED / SMS_NOTIFICATIONS_ENABLED in .env.
    """
    results: dict = {}

    if payload.channel in ("email", "both"):
        recipients = [payload.email] if payload.email else settings.default_notification_emails_list
        if not recipients:
            results["email"] = {"sent": False, "error": "No email address provided and DEFAULT_NOTIFICATION_EMAILS not set."}
        elif not settings.EMAIL_NOTIFICATIONS_ENABLED:
            results["email"] = {"sent": False, "error": "EMAIL_NOTIFICATIONS_ENABLED is False in .env"}
        elif not settings.SMTP_HOST:
            results["email"] = {"sent": False, "error": "SMTP_HOST not configured in .env"}
        else:
            results["email"] = send_email_notification(
                subject=payload.subject,
                message=payload.message,
                recipients=recipients,
            )

    if payload.channel in ("sms", "both"):
        mobile = payload.mobile or (settings.default_notification_mobiles_list[0] if settings.default_notification_mobiles_list else None)
        if not mobile:
            results["sms"] = {"sent": False, "error": "No mobile number provided and DEFAULT_NOTIFICATION_MOBILES not set."}
        elif not settings.SMS_NOTIFICATIONS_ENABLED:
            results["sms"] = {"sent": False, "error": "SMS_NOTIFICATIONS_ENABLED is False in .env"}
        elif not settings.FAST2SMS_API_KEY:
            results["sms"] = {"sent": False, "error": "FAST2SMS_API_KEY not configured in .env"}
        else:
            results["sms"] = send_sms(mobile, payload.message)

    results["config"] = {
        "email_enabled": settings.EMAIL_NOTIFICATIONS_ENABLED,
        "sms_enabled": settings.SMS_NOTIFICATIONS_ENABLED,
        "smtp_host": settings.SMTP_HOST,
        "sms_provider": settings.SMS_PROVIDER,
        "fast2sms_key_set": bool(settings.FAST2SMS_API_KEY),
    }
    results["requested_by"] = {"user_id": current_user.id, "username": current_user.username}
    return results


@router.post("/seed-demo")
def run_full_seed(current_user: User = Depends(require_admin)):
    """
    Seeds the database with a full set of demo data for testing.
    Clears all transactional data and recreates 5 students, 3 industries,
    6 rosters, 70 attendance events, 18 anomaly flags, and 8 classroom observations.
    Admin only.
    """
    result = seed_all_demo_data()
    result["requested_by"] = {
        "user_id": current_user.id,
        "username": current_user.username,
        "role": current_user.role,
    }
    return result


@router.get("/readiness")
def get_operational_readiness(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_supervisor_or_above),
):
    today = datetime.now(timezone.utc).date()

    total_students = int(db.execute(select(func.count()).select_from(Student)).scalar() or 0)
    all_profiles = db.execute(select(Student)).scalars().all()
    total_faculty = sum(1 for item in all_profiles if is_faculty_profile(db, item))
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
    active_rosters = int(
        db.execute(
            select(func.count())
            .select_from(TrainingRoster)
            .where(TrainingRoster.is_active.is_(True))
            .where(TrainingRoster.start_date <= today)
            .where(TrainingRoster.end_date >= today)
        ).scalar()
        or 0
    )
    total_industries = int(db.execute(select(func.count()).select_from(Industry)).scalar() or 0)
    attendance_events = int(db.execute(select(func.count()).select_from(AttendanceEvent)).scalar() or 0)
    anomaly_flags = int(db.execute(select(func.count()).select_from(AnomalyFlag)).scalar() or 0)
    classroom_observations = int(db.execute(select(func.count()).select_from(ClassroomObservation)).scalar() or 0)
    pending_reviews = int(
        db.execute(
            select(func.count())
            .select_from(AnomalyFlag)
            .where(AnomalyFlag.review_status == ReviewStatus.PENDING.value)
        ).scalar()
        or 0
    )

    face_enrollment_coverage = round((enrolled_students / total_students) * 100, 2) if total_students else 0.0
    consent_coverage = round((consented_students / total_students) * 100, 2) if total_students else 0.0

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "readiness": {
            "total_students": total_students,
            "total_faculty": total_faculty,
            "total_monitored_profiles": total_students,
            "consented_students": consented_students,
            "enrolled_students": enrolled_students,
            "active_rosters_today": active_rosters,
            "total_industries": total_industries,
            "attendance_events": attendance_events,
            "anomaly_flags": anomaly_flags,
            "classroom_observations": classroom_observations,
            "pending_reviews": pending_reviews,
            "face_enrollment_coverage_pct": face_enrollment_coverage,
            "consent_coverage_pct": consent_coverage,
        },
        "requested_by": {
            "user_id": current_user.id,
            "username": current_user.username,
            "role": current_user.role,
        },
    }


@router.post("/pilot-data/preview")
def preview_pilot_import(
    payload: PilotImportRequest = Body(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_supervisor_or_above),
):
    bundle = load_pilot_data(
        admissions_path=payload.admissions_path,
        ojt_path=payload.ojt_path,
        placements_path=payload.placements_path,
    )

    preview = preview_pilot_data(bundle)
    preview["roster_template_sample"] = build_roster_import_template(db, bundle.ojt)[:10]
    preview["requested_by"] = {
        "user_id": current_user.id,
        "username": current_user.username,
        "role": current_user.role,
    }
    return preview


@router.post("/pilot-data/import")
def run_pilot_import(
    payload: PilotImportRequest = Body(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_supervisor_or_above),
):
    bundle = load_pilot_data(
        admissions_path=payload.admissions_path,
        ojt_path=payload.ojt_path,
        placements_path=payload.placements_path,
    )

    students_result = import_students_from_admissions(db, bundle.admissions)
    industries_result = import_industries_from_ojt(db, bundle.ojt)
    rosters_result = auto_assign_rosters_from_ojt(db, bundle.ojt)
    roster_templates = build_roster_import_template(db, bundle.ojt)

    return {
        "students": students_result,
        "industries": industries_result,
        "rosters": rosters_result,
        "roster_templates_generated": len(roster_templates),
        "roster_template_preview": roster_templates[:10],
        "requested_by": {
            "user_id": current_user.id,
            "username": current_user.username,
            "role": current_user.role,
        },
    }


@router.post("/pilot-data/assign-rosters")
def assign_rosters_from_ojt(
    payload: PilotImportRequest = Body(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """
    Runs only the roster auto-assignment step from OJT data.

    Use this to re-run assignment after fixing industry / student records
    without re-importing the full dataset.
    """
    bundle = load_pilot_data(
        admissions_path=payload.admissions_path,
        ojt_path=payload.ojt_path,
        placements_path=payload.placements_path,
    )

    result = auto_assign_rosters_from_ojt(db, bundle.ojt)
    result["requested_by"] = {
        "user_id": current_user.id,
        "username": current_user.username,
        "role": current_user.role,
    }
    return result


@router.post("/industries/geocode-missing")
def geocode_missing_industry_coords(
    dry_run: bool = Query(default=True, description="Preview without saving when true"),
    limit: int = Query(default=50, ge=1, le=50),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """
    Resolves GPS coordinates for industries that have placeholder (0, 0) coordinates.

    Uses Nominatim geocoder with name + city + district queries.
    Run with dry_run=true first to preview results, then dry_run=false to apply.
    Rate-limited to 50 industries per call to respect Nominatim usage policy.
    """
    result = geocode_industries_with_missing_coords(db, dry_run=dry_run, limit=limit)
    result["requested_by"] = {
        "user_id": current_user.id,
        "username": current_user.username,
        "role": current_user.role,
    }
    return result


@router.get("/day-states")
def get_day_states(
    date: str | None = Query(default=None, description="Optional date in YYYY-MM-DD format"),
    send_absence_alerts: bool = Query(default=False),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_supervisor_or_above),
):
    target_dt = None
    if date:
        try:
            target_dt = datetime.strptime(date, "%Y-%m-%d").replace(tzinfo=timezone.utc)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail="date must be in YYYY-MM-DD format.") from exc

    states = compute_daily_attendance_states(db, target_date=target_dt)
    alerts: list[dict] = []

    if send_absence_alerts:
        for item in states:
            if item.state != "absent":
                continue

            student = get_student_by_id(db, item.student_id)
            alerts.append(
                queue_notification(
                    db,
                    action="absence_detected",
                    entity_type="student_day_state",
                    entity_id=f"{item.student_id}:{date or datetime.now(timezone.utc).date().isoformat()}",
                    subject="Absence detected for today's OJT attendance",
                    message="Student did not complete the required attendance events for the day.",
                    student=student,
                    user_id=current_user.id,
                )
            )
        db.commit()

    summary: dict[str, int] = {}
    for item in states:
        summary[item.state] = summary.get(item.state, 0) + 1

    return {
        "date": (target_dt.date().isoformat() if target_dt else datetime.now(timezone.utc).date().isoformat()),
        "summary": summary,
        "items": [item.to_dict() for item in states],
        "alerts_generated": alerts,
        "requested_by": {
            "user_id": current_user.id,
            "username": current_user.username,
            "role": current_user.role,
        },
    }


@router.get("/evaluation/report")
def get_evaluation_report(
    date: str | None = Query(default=None, description="Optional date in YYYY-MM-DD format"),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_supervisor_or_above),
):
    target_dt = None
    if date:
        try:
            target_dt = datetime.strptime(date, "%Y-%m-%d").replace(tzinfo=timezone.utc)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail="date must be in YYYY-MM-DD format.") from exc

    report = build_evaluation_report(db, target_date=target_dt)
    report["requested_by"] = {
        "user_id": current_user.id,
        "username": current_user.username,
        "role": current_user.role,
    }
    return report


@router.get("/integrations/attendance/{event_id}/preview")
def preview_attendance_sync(
    event_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_supervisor_or_above),
):
    event = db.get(AttendanceEvent, event_id)
    if not event:
        raise HTTPException(status_code=404, detail="Attendance event not found")

    student = get_student_by_id(db, event.student_id)
    industry = get_industry_by_id(db, event.industry_id)
    roster = db.get(TrainingRoster, event.roster_id) if event.roster_id else None

    payload = build_attendance_portal_payload(
        event=event,
        student=student,
        industry=industry,
        roster=roster,
    )
    sync_result = push_to_iti_portal(payload)
    log = create_integration_audit_log(
        db,
        system_name="iti_portal",
        entity_type="attendance_event",
        entity_id=str(event.id),
        payload={**payload, "sync_result": sync_result},
        user_id=current_user.id,
    )
    db.commit()

    return {
        "preview": payload,
        "sync_result": sync_result,
        "audit_log_id": log.id,
    }


@router.get("/integrations/anomalies/{anomaly_id}/preview")
def preview_anomaly_sync(
    anomaly_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_supervisor_or_above),
):
    anomaly = db.get(AnomalyFlag, anomaly_id)
    if not anomaly:
        raise HTTPException(status_code=404, detail="Anomaly not found")

    student = get_student_by_id(db, anomaly.student_id)
    attendance_event = db.get(AttendanceEvent, anomaly.attendance_event_id) if anomaly.attendance_event_id else None

    payload = build_anomaly_sync_payload(
        anomaly=anomaly,
        student=student,
        attendance_event=attendance_event,
    )
    sync_result = push_anomaly_to_district_dashboard(payload)
    log = create_integration_audit_log(
        db,
        system_name="district_dashboard",
        entity_type="anomaly_flag",
        entity_id=str(anomaly.id),
        payload={**payload, "sync_result": sync_result},
        user_id=current_user.id,
    )
    db.commit()

    return {
        "preview": payload,
        "sync_result": sync_result,
        "audit_log_id": log.id,
    }


@router.get("/payroll/summary")
def get_payroll_summary(
    start_date: str | None = Query(default=None, description="Start date YYYY-MM-DD"),
    end_date:   str | None = Query(default=None, description="End date YYYY-MM-DD"),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_supervisor_or_above),
):
    """
    Attendance-based payroll summary.

    Aggregates daily attendance states per student/faculty over a date range
    and produces payroll-ready working day counts for HR/payroll sync.
    """
    from datetime import date as date_type
    from sqlalchemy import and_, cast, Date
    from collections import defaultdict

    today = datetime.now(timezone.utc).date()

    try:
        sd = datetime.strptime(start_date, "%Y-%m-%d").date() if start_date else date_type(today.year, today.month, 1)
        ed = datetime.strptime(end_date, "%Y-%m-%d").date() if end_date else today
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Dates must be in YYYY-MM-DD format.") from exc

    events = db.execute(
        select(
            AttendanceEvent.student_id,
            func.cast(AttendanceEvent.event_time, Date).label("event_date"),
            AttendanceEvent.status,
        ).where(
            and_(
                func.cast(AttendanceEvent.event_time, Date) >= sd,
                func.cast(AttendanceEvent.event_time, Date) <= ed,
            )
        )
    ).all()

    STATUS_RANK = {"present": 1, "late": 2, "outside_geofence": 3, "face_mismatch": 4, "needs_review": 5}
    student_day: dict = defaultdict(dict)

    for ev in events:
        sid, edate, status = ev.student_id, ev.event_date, ev.status
        current = student_day[sid].get(str(edate))
        rank = STATUS_RANK.get(status, 99)
        if current is None or rank < STATUS_RANK.get(current, 99):
            student_day[sid][str(edate)] = status

    students_map = {s.id: s for s in db.execute(select(Student)).scalars().all()}
    records = []

    for sid, day_map in student_day.items():
        present_days = sum(1 for s in day_map.values() if s == "present")
        late_days    = sum(1 for s in day_map.values() if s == "late")
        review_days  = sum(1 for s in day_map.values() if s in ("outside_geofence", "face_mismatch", "needs_review"))
        total_days   = len(day_map)
        stu = students_map.get(sid)
        records.append({
            "student_id":        sid,
            "student_code":      stu.student_code if stu else None,
            "full_name":         stu.full_name    if stu else None,
            "iti_name":          stu.iti_name     if stu else None,
            "trade":             stu.trade        if stu else None,
            "present_days":      present_days,
            "late_days":         late_days,
            "review_days":       review_days,
            "total_logged_days": total_days,
            "attendance_pct":    round((present_days + late_days) / total_days * 100, 1) if total_days else 0,
        })

    records.sort(key=lambda r: r.get("student_code") or "")

    return {
        "period_start":   str(sd),
        "period_end":     str(ed),
        "total_students": len(records),
        "summary": {
            "avg_attendance_pct":   round(sum(r["attendance_pct"] for r in records) / len(records), 1) if records else 0,
            "fully_present_count":  sum(1 for r in records if r["late_days"] == 0 and r["review_days"] == 0 and r["present_days"] > 0),
            "needs_review_count":   sum(1 for r in records if r["review_days"] > 0),
        },
        "records": records,
        "requested_by": {
            "user_id":  current_user.id,
            "username": current_user.username,
            "role":     current_user.role,
        },
    }
