from __future__ import annotations

from datetime import datetime
from typing import Any

import httpx
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.database_models import AuditLog


def build_attendance_portal_payload(*, event, student=None, industry=None, roster=None) -> dict[str, Any]:
    return {
        "system": "iti_portal",
        "base_url": settings.ITI_PORTAL_BASE_URL,
        "entity_type": "attendance_event",
        "attendance_event_id": event.id,
        "student": {
            "id": getattr(student, "id", None),
            "student_code": getattr(student, "student_code", None),
            "full_name": getattr(student, "full_name", None),
            "iti_name": getattr(student, "iti_name", None),
            "trade": getattr(student, "trade", None),
            "batch": getattr(student, "batch", None),
        },
        "industry": {
            "id": getattr(industry, "id", None),
            "industry_code": getattr(industry, "industry_code", None),
            "name": getattr(industry, "name", None),
            "district": getattr(industry, "district", None),
            "city": getattr(industry, "city", None),
        },
        "roster": {
            "id": getattr(roster, "id", None),
            "shift_start_time": getattr(roster, "shift_start_time", None),
            "shift_end_time": getattr(roster, "shift_end_time", None),
            "start_date": str(getattr(roster, "start_date", None)),
            "end_date": str(getattr(roster, "end_date", None)),
        },
        "attendance": {
            "event_type": event.event_type,
            "status": event.status,
            "event_time": event.event_time.isoformat() if getattr(event, "event_time", None) else None,
            "latitude": event.latitude,
            "longitude": event.longitude,
            "gps_accuracy_meters": event.gps_accuracy_meters,
            "distance_from_industry_meters": event.distance_from_industry_meters,
            "face_match_score": event.face_match_score,
            "decision_reason": event.decision_reason,
        },
    }


def build_anomaly_sync_payload(*, anomaly, student=None, attendance_event=None) -> dict[str, Any]:
    return {
        "system": "district_dashboard",
        "district_dashboard_sync_enabled": settings.DISTRICT_DASHBOARD_SYNC_ENABLED,
        "entity_type": "anomaly_flag",
        "anomaly_id": anomaly.id,
        "student": {
            "id": getattr(student, "id", None),
            "student_code": getattr(student, "student_code", None),
            "full_name": getattr(student, "full_name", None),
            "iti_name": getattr(student, "iti_name", None),
        },
        "attendance_event": {
            "id": getattr(attendance_event, "id", None),
            "event_type": getattr(attendance_event, "event_type", None),
            "status": getattr(attendance_event, "status", None),
            "event_time": (
                attendance_event.event_time.isoformat()
                if getattr(attendance_event, "event_time", None)
                else None
            ),
        },
        "anomaly": {
            "anomaly_type": anomaly.anomaly_type,
            "severity": anomaly.severity,
            "risk_score": anomaly.risk_score,
            "explanation": anomaly.explanation,
            "review_status": anomaly.review_status,
            "review_notes": anomaly.review_notes,
        },
    }


def push_to_iti_portal(payload: dict[str, Any]) -> dict[str, Any]:
    """
    POST attendance payload to the ITI portal API when sync is enabled.
    Requires ITI_PORTAL_SYNC_ENABLED=true and ITI_PORTAL_API_KEY in .env.
    """
    if not settings.ITI_PORTAL_SYNC_ENABLED:
        return {"synced": False, "reason": "ITI_PORTAL_SYNC_ENABLED is False."}

    if not settings.ITI_PORTAL_API_KEY:
        return {"synced": False, "reason": "ITI_PORTAL_API_KEY not configured."}

    url = f"{settings.ITI_PORTAL_BASE_URL.rstrip('/')}/api/attendance/sync"
    try:
        response = httpx.post(
            url,
            json=payload,
            headers={
                "Authorization": f"Bearer {settings.ITI_PORTAL_API_KEY}",
                "Content-Type": "application/json",
                "X-Source": "iti-attendance-ai",
            },
            timeout=15.0,
        )
        return {
            "synced": response.is_success,
            "status_code": response.status_code,
            "url": url,
            "response": response.text[:500],
        }
    except Exception as exc:
        return {"synced": False, "url": url, "error": str(exc)}


def push_anomaly_to_district_dashboard(payload: dict[str, Any]) -> dict[str, Any]:
    """
    POST anomaly payload to the district dashboard webhook when sync is enabled.
    Requires DISTRICT_DASHBOARD_SYNC_ENABLED=true and DISTRICT_DASHBOARD_WEBHOOK_URL.
    """
    if not settings.DISTRICT_DASHBOARD_SYNC_ENABLED:
        return {"synced": False, "reason": "DISTRICT_DASHBOARD_SYNC_ENABLED is False."}

    webhook_url = settings.DISTRICT_DASHBOARD_WEBHOOK_URL
    if not webhook_url:
        return {"synced": False, "reason": "DISTRICT_DASHBOARD_WEBHOOK_URL not configured."}

    try:
        response = httpx.post(
            webhook_url,
            json=payload,
            headers={"Content-Type": "application/json", "X-Source": "iti-attendance-ai"},
            timeout=10.0,
        )
        return {
            "synced": response.is_success,
            "status_code": response.status_code,
            "url": webhook_url,
        }
    except Exception as exc:
        return {"synced": False, "url": webhook_url, "error": str(exc)}


def create_integration_audit_log(
    db: Session,
    *,
    system_name: str,
    entity_type: str,
    entity_id: str,
    payload: dict[str, Any],
    user_id: int | None = None,
) -> AuditLog:
    log = AuditLog(
        user_id=user_id,
        action=f"integration_preview:{system_name}",
        entity_type=entity_type,
        entity_id=entity_id,
        metadata_json={
            "preview_generated_at": datetime.utcnow().isoformat() + "Z",
            "payload": payload,
        },
    )
    db.add(log)
    db.flush()
    return log
