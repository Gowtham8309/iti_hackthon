from datetime import datetime, time, timezone
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.database import SessionLocal
from app.models.database_models import (
    AnomalyFlag,
    AttendanceEvent,
    AttendanceEventType,
    AttendanceStatus,
    AnomalySeverity,
    Industry,
)
from app.schemas.api_schemas import AttendanceCheckInRequest, AttendanceCheckOutRequest
from app.services.crud_service import (
    get_active_roster_for_student,
    get_student_by_id,
)
from app.services.face_service import (
    FaceServiceError,
    extract_face_embedding_from_base64,
    verify_face_embeddings,
)
from app.services.geo_service import validate_geofence
from app.services.ml_anomaly_service import maybe_retrain, run_ml_checks
from app.services.selfie_storage_service import (
    SelfieStorageError,
    save_attendance_selfie,
)
from app.services.notification_service import queue_notification


FACE_LIVENESS_REVIEW_THRESHOLD = 0.60
LATE_GRACE_MINUTES = 30


def _parse_hhmm(value: str) -> time:
    """
    Parses shift time like '09:00' into Python time object.
    """
    hour, minute = value.strip().split(":")
    return time(hour=int(hour), minute=int(minute))


def _minutes_between(start: datetime, end: datetime) -> float:
    return (end - start).total_seconds() / 60.0


def _combine_reasons(reasons: list[str]) -> str:
    clean = [r.strip() for r in reasons if r and r.strip()]
    return " ".join(clean) if clean else "Attendance processed."


def _day_bounds(event_time: datetime) -> tuple[datetime, datetime]:
    day_start = datetime.combine(event_time.date(), time.min, tzinfo=event_time.tzinfo)
    day_end = datetime.combine(event_time.date(), time.max, tzinfo=event_time.tzinfo)
    return day_start, day_end


def get_same_day_event(
    db: Session,
    *,
    student_id: int,
    event_type: str,
    event_time: datetime,
) -> AttendanceEvent | None:
    day_start, day_end = _day_bounds(event_time)

    stmt = (
        select(AttendanceEvent)
        .where(AttendanceEvent.student_id == student_id)
        .where(AttendanceEvent.event_type == event_type)
        .where(AttendanceEvent.event_time >= day_start)
        .where(AttendanceEvent.event_time <= day_end)
        .order_by(AttendanceEvent.event_time.desc(), AttendanceEvent.id.desc())
    )

    return db.execute(stmt).scalar_one_or_none()


def evaluate_schedule_status(
    *,
    roster_shift_start: str,
    roster_shift_end: str,
    event_time: datetime,
) -> dict[str, Any]:
    """
    Checks whether check-in time is on time or late.
    """
    shift_start = _parse_hhmm(roster_shift_start)
    shift_end = _parse_hhmm(roster_shift_end)

    event_date = event_time.date()

    shift_start_dt = datetime.combine(event_date, shift_start, tzinfo=event_time.tzinfo)
    shift_end_dt = datetime.combine(event_date, shift_end, tzinfo=event_time.tzinfo)

    minutes_after_shift_start = _minutes_between(shift_start_dt, event_time)

    if event_time > shift_end_dt:
        return {
            "is_valid_schedule": False,
            "is_late": True,
            "minutes_late": round(minutes_after_shift_start, 2),
            "status": "outside_shift_time",
            "reason": "Check-in happened after shift end time.",
        }

    if minutes_after_shift_start > LATE_GRACE_MINUTES:
        return {
            "is_valid_schedule": True,
            "is_late": True,
            "minutes_late": round(minutes_after_shift_start, 2),
            "status": "late",
            "reason": f"Student checked in {round(minutes_after_shift_start, 2)} minutes after shift start.",
        }

    return {
        "is_valid_schedule": True,
        "is_late": False,
        "minutes_late": max(0, round(minutes_after_shift_start, 2)),
        "status": "on_time",
        "reason": "Student check-in is within allowed shift timing.",
    }


def evaluate_checkout_schedule_status(
    *,
    roster_shift_start: str,
    roster_shift_end: str,
    event_time: datetime,
) -> dict[str, Any]:
    shift_start = _parse_hhmm(roster_shift_start)
    shift_end = _parse_hhmm(roster_shift_end)

    event_date = event_time.date()
    shift_start_dt = datetime.combine(event_date, shift_start, tzinfo=event_time.tzinfo)
    shift_end_dt = datetime.combine(event_date, shift_end, tzinfo=event_time.tzinfo)

    if event_time < shift_start_dt:
        return {
            "is_valid_schedule": False,
            "left_early": True,
            "minutes_from_shift_end": round(_minutes_between(event_time, shift_end_dt), 2),
            "status": "before_shift_start",
            "reason": "Check-out happened before shift start time.",
        }

    if event_time < shift_end_dt:
        return {
            "is_valid_schedule": True,
            "left_early": True,
            "minutes_from_shift_end": round(_minutes_between(event_time, shift_end_dt), 2),
            "status": "early_check_out",
            "reason": "Student checked out before scheduled shift end time.",
        }

    return {
        "is_valid_schedule": True,
        "left_early": False,
        "minutes_from_shift_end": 0.0,
        "status": "completed_shift",
        "reason": "Student checked out after scheduled shift timing.",
    }


def evaluate_face_status(
    *,
    face_match_score: float | None,
    liveness_score: float | None,
) -> dict[str, Any]:
    """
    Manual POC face score evaluator.

    Used only as fallback when real face enrollment/selfie is not available.
    """
    if face_match_score is None:
        return {
            "is_face_valid": False,
            "needs_review": True,
            "status": "face_score_missing",
            "reason": "Face match score is missing.",
        }

    if face_match_score >= settings.FACE_MATCH_ACCEPT_THRESHOLD:
        face_status = {
            "is_face_valid": True,
            "needs_review": False,
            "status": "face_accepted",
            "reason": f"Face match score {face_match_score} is accepted.",
        }
    else:
        face_status = {
            "is_face_valid": True,
            "needs_review": True,
            "status": "face_needs_review",
            "reason": f"Face match score {face_match_score} needs supervisor review.",
        }

    if liveness_score is not None and liveness_score < FACE_LIVENESS_REVIEW_THRESHOLD:
        face_status["is_face_valid"] = False
        face_status["needs_review"] = True
        face_status["status"] = "liveness_low"
        face_status["reason"] += f" Liveness score {liveness_score} is low."

    return face_status


def evaluate_real_or_manual_face_status(
    *,
    student,
    payload: AttendanceCheckInRequest,
) -> dict[str, Any]:
    """
    Uses real pretrained face recognition when possible.

    Real mode requires:
    - student.face_enrolled = True
    - student.face_embedding exists
    - check-in selfie_image_base64 exists

    If enrollment is missing, attendance goes to supervisor review.
    """
    selfie_image_base64 = getattr(payload, "selfie_image_base64", None)

    if student.face_enrolled and student.face_embedding and selfie_image_base64:
        enrolled_embedding = student.face_embedding.get("embedding")

        if not enrolled_embedding:
            raise ValueError("Student face is enrolled, but embedding is missing.")

        try:
            checkin_embedding_result = extract_face_embedding_from_base64(
                selfie_image_base64
            )

            verification = verify_face_embeddings(
                enrolled_embedding=enrolled_embedding,
                checkin_embedding=checkin_embedding_result["embedding"],
            )

        except FaceServiceError as exc:
            raise ValueError(f"Face verification failed: {str(exc)}") from exc

        server_liveness = checkin_embedding_result.get("liveness_score", 1.0)
        liveness_passed = checkin_embedding_result.get("liveness_passed", True)

        face_result = {
            "is_face_valid": verification["is_match"],
            "needs_review": verification["needs_review"],
            "status": verification["status"],
            "reason": verification["reason"],
            "face_match_score": verification["score"],
            "source": "insightface_buffalo_l",
            "accept_threshold": verification["accept_threshold"],
            "review_threshold": verification["review_threshold"],
            "checkin_det_score": checkin_embedding_result["det_score"],
            "checkin_face_count": checkin_embedding_result["face_count"],
            "checkin_bbox": checkin_embedding_result["bbox"],
            "server_liveness_score": server_liveness,
            "liveness_detail": checkin_embedding_result.get("liveness_detail"),
        }

        if checkin_embedding_result["face_count"] != 1:
            face_result["is_face_valid"] = False
            face_result["needs_review"] = True
            face_result["status"] = "multiple_faces_detected"
            face_result["reason"] = (
                "Multiple faces detected during check-in: "
                f"{checkin_embedding_result['face_count']} faces. "
                "Attendance requires exactly one clear student face."
            )
        elif not liveness_passed:
            face_result["is_face_valid"] = False
            face_result["needs_review"] = True
            face_result["status"] = "liveness_low"
            liveness_reason = (checkin_embedding_result.get("liveness_detail") or {}).get("reason", "")
            face_result["reason"] += f" Server liveness check failed. {liveness_reason}"

        return face_result

    if not student.face_enrolled or not student.face_embedding:
        return {
            "is_face_valid": False,
            "needs_review": True,
            "status": "face_enrollment_missing",
            "reason": "Face enrollment is missing for this profile. Attendance requires supervisor review.",
            "face_match_score": None,
            "source": "enrollment_missing_review",
        }

    return {
        "is_face_valid": False,
        "needs_review": True,
        "status": "selfie_missing_review",
        "reason": "Captured selfie evidence is missing for face verification. Attendance requires supervisor review.",
        "face_match_score": None,
        "source": "selfie_missing_review",
    }


def decide_attendance_status(
    *,
    face_result: dict[str, Any],
    geo_result: dict[str, Any],
    schedule_result: dict[str, Any],
) -> str:
    """
    Priority order:
    1. Face mismatch
    2. Outside geofence
    3. Poor GPS / invalid location + poor GPS
    4. Face/liveness/multiple-face needs review
    5. Outside shift time
    6. Late
    7. Present
    """
    if face_result["status"] == "face_mismatch":
        return AttendanceStatus.FACE_MISMATCH.value

    if geo_result["status"] == "outside_geofence":
        return AttendanceStatus.OUTSIDE_GEOFENCE.value

    if geo_result["status"] in {"poor_gps_accuracy", "invalid_location_and_poor_gps"}:
        return AttendanceStatus.NEEDS_REVIEW.value

    if face_result.get("needs_review"):
        return AttendanceStatus.NEEDS_REVIEW.value

    if schedule_result["status"] == "outside_shift_time":
        return AttendanceStatus.NEEDS_REVIEW.value

    if schedule_result.get("is_late"):
        return AttendanceStatus.LATE.value

    return AttendanceStatus.PRESENT.value


def build_anomaly_candidates(
    *,
    attendance_status: str,
    face_result: dict[str, Any],
    geo_result: dict[str, Any],
    schedule_result: dict[str, Any],
) -> list[dict[str, Any]]:
    """
    Creates explainable anomaly records.
    """
    anomalies: list[dict[str, Any]] = []

    if attendance_status == AttendanceStatus.FACE_MISMATCH.value:
        anomalies.append(
            {
                "anomaly_type": "face_mismatch",
                "severity": AnomalySeverity.HIGH.value,
                "risk_score": 85.0,
                "explanation": face_result["reason"],
            }
        )

    if face_result["status"] == "multiple_faces_detected":
        anomalies.append(
            {
                "anomaly_type": "multiple_faces_detected",
                "severity": AnomalySeverity.HIGH.value,
                "risk_score": 80.0,
                "explanation": face_result["reason"],
            }
        )

    if geo_result["status"] == "outside_geofence":
        anomalies.append(
            {
                "anomaly_type": "outside_geofence",
                "severity": AnomalySeverity.HIGH.value,
                "risk_score": 75.0,
                "explanation": geo_result["reason"],
            }
        )

    if geo_result["status"] == "poor_gps_accuracy":
        anomalies.append(
            {
                "anomaly_type": "poor_gps_accuracy",
                "severity": AnomalySeverity.MEDIUM.value,
                "risk_score": 55.0,
                "explanation": geo_result["reason"],
            }
        )

    if geo_result["status"] == "invalid_location_and_poor_gps":
        anomalies.append(
            {
                "anomaly_type": "invalid_location_and_poor_gps",
                "severity": AnomalySeverity.CRITICAL.value,
                "risk_score": 90.0,
                "explanation": geo_result["reason"],
            }
        )

    if face_result["status"] in {
        "face_needs_review",
        "face_enrollment_missing",
        "selfie_missing_review",
        "liveness_low",
        "face_score_missing",
    }:
        anomalies.append(
            {
                "anomaly_type": face_result["status"],
                "severity": AnomalySeverity.MEDIUM.value,
                "risk_score": 60.0,
                "explanation": face_result["reason"],
            }
        )

    if schedule_result["status"] == "late":
        anomalies.append(
            {
                "anomaly_type": "late_check_in",
                "severity": AnomalySeverity.LOW.value,
                "risk_score": 35.0,
                "explanation": schedule_result["reason"],
            }
        )

    if schedule_result["status"] == "outside_shift_time":
        anomalies.append(
            {
                "anomaly_type": "outside_shift_time",
                "severity": AnomalySeverity.MEDIUM.value,
                "risk_score": 65.0,
                "explanation": schedule_result["reason"],
            }
        )

    return anomalies


def build_checkout_anomaly_candidates(
    *,
    attendance_status: str,
    face_result: dict[str, Any],
    geo_result: dict[str, Any],
    schedule_result: dict[str, Any],
) -> list[dict[str, Any]]:
    anomalies = build_anomaly_candidates(
        attendance_status=attendance_status,
        face_result=face_result,
        geo_result=geo_result,
        schedule_result={
            "status": "on_time",
            "reason": schedule_result["reason"],
        } if schedule_result["status"] == "completed_shift" else schedule_result,
    )

    if schedule_result["status"] == "early_check_out":
        anomalies.append(
            {
                "anomaly_type": "early_check_out",
                "severity": AnomalySeverity.LOW.value,
                "risk_score": 40.0,
                "explanation": schedule_result["reason"],
            }
        )
    elif schedule_result["status"] == "before_shift_start":
        anomalies.append(
            {
                "anomaly_type": "before_shift_start",
                "severity": AnomalySeverity.HIGH.value,
                "risk_score": 82.0,
                "explanation": schedule_result["reason"],
            }
        )

    return anomalies


def _finalize_attendance_event(
    db: Session,
    *,
    student,
    industry: Industry | None,
    roster,
    payload,
    event_type: str,
    attendance_status: str,
    event_time: datetime,
    face_result: dict[str, Any],
    geo_result: dict[str, Any],
    schedule_result: dict[str, Any],
    decision_reason: str,
    anomaly_candidates: list[dict[str, Any]],
    ip_address: str | None = None,
) -> dict[str, Any]:
    event = AttendanceEvent(
        student_id=payload.student_id,
        industry_id=roster.industry_id,
        roster_id=roster.id,
        event_type=event_type,
        status=attendance_status,
        event_time=event_time,
        latitude=payload.latitude,
        longitude=payload.longitude,
        gps_accuracy_meters=payload.gps_accuracy_meters,
        distance_from_industry_meters=geo_result["distance_from_industry_meters"],
        face_match_score=face_result.get("face_match_score"),
        liveness_score=payload.liveness_score,
        device_id=payload.device_id,
        browser_info=payload.browser_info,
        ip_address=ip_address,
        decision_reason=decision_reason,
        raw_metadata={
            "face_result": face_result,
            "geo_result": geo_result,
            "schedule_result": schedule_result,
            "selfie_captured": getattr(payload, "selfie_captured", False),
            "notes": getattr(payload, "check_out_notes", None),
        },
    )

    try:
        db.add(event)
        db.flush()

        selfie_evidence = save_attendance_selfie(
            student_id=payload.student_id,
            attendance_event_id=event.id,
            selfie_image_base64=getattr(payload, "selfie_image_base64", None),
        )

        event_metadata = dict(event.raw_metadata or {})
        event_metadata["selfie_evidence"] = selfie_evidence
        event.raw_metadata = event_metadata

        db.commit()
        db.refresh(event)

    except SelfieStorageError as exc:
        db.rollback()
        raise ValueError(f"Selfie storage failed: {str(exc)}") from exc

    created_anomalies: list[AnomalyFlag] = []

    for item in anomaly_candidates:
        anomaly = AnomalyFlag(
            attendance_event_id=event.id,
            student_id=payload.student_id,
            anomaly_type=item["anomaly_type"],
            severity=item["severity"],
            risk_score=item["risk_score"],
            explanation=item["explanation"],
        )
        db.add(anomaly)
        created_anomalies.append(anomaly)

    notifications_generated: list[dict[str, Any]] = []

    if created_anomalies:
        db.commit()
        for anomaly in created_anomalies:
            db.refresh(anomaly)
            notifications_generated.append(
                queue_notification(
                    db,
                    action="anomaly_created",
                    entity_type="anomaly_flag",
                    entity_id=str(anomaly.id),
                    subject=f"Attendance anomaly detected for student {student.student_code}",
                    message=anomaly.explanation,
                    student=student,
                    industry=industry,
                )
            )

    notifications_generated.append(
        queue_notification(
            db,
            action="attendance_event_recorded",
            entity_type="attendance_event",
            entity_id=str(event.id),
            subject=f"Attendance {event_type.replace('_', ' ')} recorded",
            message=decision_reason,
            student=student,
            industry=industry,
        )
    )

    db.commit()

    return {
        "attendance_event": {
            "id": event.id,
            "student_id": event.student_id,
            "industry_id": event.industry_id,
            "roster_id": event.roster_id,
            "event_type": event.event_type,
            "status": event.status,
            "event_time": event.event_time.isoformat(),
            "latitude": event.latitude,
            "longitude": event.longitude,
            "gps_accuracy_meters": event.gps_accuracy_meters,
            "distance_from_industry_meters": event.distance_from_industry_meters,
            "face_match_score": event.face_match_score,
            "liveness_score": event.liveness_score,
            "decision_reason": event.decision_reason,
            "selfie_evidence": (event.raw_metadata or {}).get("selfie_evidence"),
        },
        "decision": {
            "status": attendance_status,
            "reason": decision_reason,
        },
        "checks": {
            "face": face_result,
            "geo": geo_result,
            "schedule": schedule_result,
        },
        "anomalies_created": [
            {
                "id": anomaly.id,
                "anomaly_type": anomaly.anomaly_type,
                "severity": anomaly.severity,
                "risk_score": anomaly.risk_score,
                "explanation": anomaly.explanation,
            }
            for anomaly in created_anomalies
        ],
        "notifications_generated": notifications_generated,
    }


def process_check_in(
    db: Session,
    *,
    payload: AttendanceCheckInRequest,
    event_time: datetime | None = None,
    ip_address: str | None = None,
) -> dict[str, Any]:
    """
    Main attendance check-in engine.
    """
    student = get_student_by_id(db, payload.student_id)
    if not student:
        raise ValueError(f"Student not found with id: {payload.student_id}")

    roster = get_active_roster_for_student(db, payload.student_id)
    if not roster:
        raise ValueError(f"No active training roster found for student id: {payload.student_id}")

    event_time = event_time or datetime.now(timezone.utc)

    existing_check_in = get_same_day_event(
        db,
        student_id=payload.student_id,
        event_type=AttendanceEventType.CHECK_IN.value,
        event_time=event_time,
    )
    if existing_check_in:
        raise ValueError("Only one check-in is allowed per day for this profile.")

    if getattr(payload, "selfie_captured", False) and not getattr(payload, "selfie_image_base64", None):
        raise ValueError("Selfie was marked as captured, but no selfie image was received.")

    geo_validation = validate_geofence(
        db,
        industry_id=roster.industry_id,
        student_latitude=payload.latitude,
        student_longitude=payload.longitude,
        gps_accuracy_meters=payload.gps_accuracy_meters,
    )
    geo_result = geo_validation.to_dict()

    face_result = evaluate_real_or_manual_face_status(
        student=student,
        payload=payload,
    )

    resolved_face_match_score = face_result.get("face_match_score")

    schedule_result = evaluate_schedule_status(
        roster_shift_start=roster.shift_start_time,
        roster_shift_end=roster.shift_end_time,
        event_time=event_time,
    )

    attendance_status = decide_attendance_status(
        face_result=face_result,
        geo_result=geo_result,
        schedule_result=schedule_result,
    )

    decision_reason = _combine_reasons(
        [
            face_result["reason"],
            geo_result["reason"],
            schedule_result["reason"],
        ]
    )

    anomaly_candidates = build_anomaly_candidates(
        attendance_status=attendance_status,
        face_result=face_result,
        geo_result=geo_result,
        schedule_result=schedule_result,
    )

    ml_candidates = run_ml_checks(
        db,
        student_id=payload.student_id,
        industry_id=roster.industry_id,
        device_id=payload.device_id,
        ip_address=ip_address,
        event_time=event_time,
    )
    anomaly_candidates.extend(ml_candidates)

    industry = db.get(Industry, roster.industry_id)

    result = _finalize_attendance_event(
        db,
        student=student,
        industry=industry,
        roster=roster,
        payload=payload,
        event_type=AttendanceEventType.CHECK_IN.value,
        attendance_status=attendance_status,
        event_time=event_time,
        face_result={**face_result, "face_match_score": resolved_face_match_score},
        geo_result=geo_result,
        schedule_result=schedule_result,
        decision_reason=decision_reason,
        anomaly_candidates=anomaly_candidates,
        ip_address=ip_address,
    )

    maybe_retrain(db)
    return result


def process_check_out(
    db: Session,
    *,
    payload: AttendanceCheckOutRequest,
    event_time: datetime | None = None,
    ip_address: str | None = None,
) -> dict[str, Any]:
    student = get_student_by_id(db, payload.student_id)
    if not student:
        raise ValueError(f"Student not found with id: {payload.student_id}")

    roster = get_active_roster_for_student(db, payload.student_id)
    if not roster:
        raise ValueError(f"No active training roster found for student id: {payload.student_id}")

    event_time = event_time or datetime.now(timezone.utc)

    existing_check_out = get_same_day_event(
        db,
        student_id=payload.student_id,
        event_type=AttendanceEventType.CHECK_OUT.value,
        event_time=event_time,
    )
    if existing_check_out:
        raise ValueError("Only one check-out is allowed per day for this profile.")

    if getattr(payload, "selfie_captured", False) and not getattr(payload, "selfie_image_base64", None):
        raise ValueError("Selfie was marked as captured, but no selfie image was received.")

    geo_result = validate_geofence(
        db,
        industry_id=roster.industry_id,
        student_latitude=payload.latitude,
        student_longitude=payload.longitude,
        gps_accuracy_meters=payload.gps_accuracy_meters,
    ).to_dict()

    face_result = evaluate_real_or_manual_face_status(student=student, payload=payload)
    schedule_result = evaluate_checkout_schedule_status(
        roster_shift_start=roster.shift_start_time,
        roster_shift_end=roster.shift_end_time,
        event_time=event_time,
    )

    if face_result["status"] == "face_mismatch":
        attendance_status = AttendanceStatus.FACE_MISMATCH.value
    elif geo_result["status"] == "outside_geofence":
        attendance_status = AttendanceStatus.OUTSIDE_GEOFENCE.value
    elif geo_result["status"] in {"poor_gps_accuracy", "invalid_location_and_poor_gps"}:
        attendance_status = AttendanceStatus.NEEDS_REVIEW.value
    elif face_result.get("needs_review"):
        attendance_status = AttendanceStatus.NEEDS_REVIEW.value
    elif schedule_result["status"] in {"before_shift_start", "early_check_out"}:
        attendance_status = AttendanceStatus.NEEDS_REVIEW.value
    else:
        attendance_status = AttendanceStatus.PRESENT.value

    decision_reason = _combine_reasons(
        [
            face_result["reason"],
            geo_result["reason"],
            schedule_result["reason"],
            getattr(payload, "check_out_notes", "") or "",
        ]
    )

    anomaly_candidates = build_checkout_anomaly_candidates(
        attendance_status=attendance_status,
        face_result=face_result,
        geo_result=geo_result,
        schedule_result=schedule_result,
    )

    ml_candidates = run_ml_checks(
        db,
        student_id=payload.student_id,
        industry_id=roster.industry_id,
        device_id=payload.device_id,
        ip_address=ip_address,
        event_time=event_time,
    )
    anomaly_candidates.extend(ml_candidates)

    industry = db.get(Industry, roster.industry_id)

    result = _finalize_attendance_event(
        db,
        student=student,
        industry=industry,
        roster=roster,
        payload=payload,
        event_type=AttendanceEventType.CHECK_OUT.value,
        attendance_status=attendance_status,
        event_time=event_time,
        face_result=face_result,
        geo_result=geo_result,
        schedule_result=schedule_result,
        decision_reason=decision_reason,
        anomaly_candidates=anomaly_candidates,
        ip_address=ip_address,
    )

    maybe_retrain(db)
    return result


def run_attendance_self_test() -> dict[str, Any]:
    """
    Real Neon DB attendance self-test.

    No selfie image is included here, so it may use manual POC score.
    """
    db = SessionLocal()

    try:
        valid_payload = AttendanceCheckInRequest(
            student_id=1,
            latitude=17.6868,
            longitude=83.2185,
            gps_accuracy_meters=20,
            device_id="demo-browser-device-valid",
            browser_info="self-test-browser",
            face_match_score=0.86,
            liveness_score=0.91,
            selfie_captured=False,
            selfie_image_base64=None,
        )

        outside_payload = AttendanceCheckInRequest(
            student_id=1,
            latitude=17.6968,
            longitude=83.2285,
            gps_accuracy_meters=20,
            device_id="demo-browser-device-outside",
            browser_info="self-test-browser",
            face_match_score=0.88,
            liveness_score=0.92,
            selfie_captured=False,
            selfie_image_base64=None,
        )

        fixed_event_time = datetime(2026, 5, 5, 9, 10, tzinfo=timezone.utc)

        valid_result = process_check_in(
            db,
            payload=valid_payload,
            event_time=fixed_event_time,
            ip_address="127.0.0.1",
        )

        outside_result = process_check_in(
            db,
            payload=outside_payload,
            event_time=fixed_event_time,
            ip_address="127.0.0.1",
        )

        attendance_count = db.execute(
            select(func.count()).select_from(AttendanceEvent)
        ).scalar()

        anomaly_count = db.execute(
            select(func.count()).select_from(AnomalyFlag)
        ).scalar()

        return {
            "attendance_self_test": "passed",
            "valid_check_in_status": valid_result["decision"]["status"],
            "valid_face_source": valid_result["checks"]["face"].get("source"),
            "valid_face_score": valid_result["attendance_event"].get("face_match_score"),
            "valid_selfie_evidence": valid_result["attendance_event"].get("selfie_evidence"),
            "outside_check_in_status": outside_result["decision"]["status"],
            "outside_face_source": outside_result["checks"]["face"].get("source"),
            "outside_face_score": outside_result["attendance_event"].get("face_match_score"),
            "outside_selfie_evidence": outside_result["attendance_event"].get("selfie_evidence"),
            "outside_anomalies": outside_result["anomalies_created"],
            "database_counts": {
                "attendance_events": int(attendance_count or 0),
                "anomaly_flags": int(anomaly_count or 0),
            },
        }

    finally:
        db.close()


if __name__ == "__main__":
    result = run_attendance_self_test()
    print(result)
