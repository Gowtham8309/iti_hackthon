from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, time, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.database_models import AttendanceEvent, AttendanceEventType, AttendanceStatus, TrainingRoster


@dataclass
class DailyAttendanceState:
    student_id: int
    roster_id: int
    student_code: str | None
    student_name: str | None
    iti_name: str | None
    trade: str | None
    industry_id: int | None
    industry_code: str | None
    industry_name: str | None
    shift_start_time: str | None
    shift_end_time: str | None
    state: str
    review_required: bool
    reasons: list[str]
    check_in_event_id: int | None
    check_out_event_id: int | None

    def to_dict(self) -> dict[str, Any]:
        return {
            "student_id": self.student_id,
            "roster_id": self.roster_id,
            "student_code": self.student_code,
            "student_name": self.student_name,
            "iti_name": self.iti_name,
            "trade": self.trade,
            "industry_id": self.industry_id,
            "industry_code": self.industry_code,
            "industry_name": self.industry_name,
            "shift_start_time": self.shift_start_time,
            "shift_end_time": self.shift_end_time,
            "state": self.state,
            "review_required": self.review_required,
            "reasons": self.reasons,
            "check_in_event_id": self.check_in_event_id,
            "check_out_event_id": self.check_out_event_id,
        }


def _day_window(target_date: datetime | None = None) -> tuple[datetime, datetime]:
    current = target_date or datetime.now(timezone.utc)
    start_dt = datetime.combine(current.date(), time.min, tzinfo=timezone.utc)
    end_dt = datetime.combine(current.date(), time.max, tzinfo=timezone.utc)
    return start_dt, end_dt


def compute_daily_attendance_states(
    db: Session,
    *,
    target_date: datetime | None = None,
) -> list[DailyAttendanceState]:
    start_dt, end_dt = _day_window(target_date)
    day = start_dt.date()

    rosters = db.execute(
        select(TrainingRoster)
        .where(TrainingRoster.is_active.is_(True))
        .where(TrainingRoster.start_date <= day)
        .where(TrainingRoster.end_date >= day)
    ).scalars().all()

    events = db.execute(
        select(AttendanceEvent)
        .where(AttendanceEvent.event_time >= start_dt)
        .where(AttendanceEvent.event_time <= end_dt)
        .order_by(AttendanceEvent.event_time.asc(), AttendanceEvent.id.asc())
    ).scalars().all()

    events_by_student: dict[int, list[AttendanceEvent]] = {}
    for event in events:
        events_by_student.setdefault(int(event.student_id), []).append(event)

    results: list[DailyAttendanceState] = []

    for roster in rosters:
        student_events = events_by_student.get(int(roster.student_id), [])
        check_ins = [item for item in student_events if item.event_type == AttendanceEventType.CHECK_IN.value]
        check_outs = [item for item in student_events if item.event_type == AttendanceEventType.CHECK_OUT.value]

        reasons: list[str] = []
        review_required = False
        state = "present"

        if not check_ins:
            state = "absent"
            reasons.append("No check-in recorded for the day.")
        else:
            first_check_in = check_ins[0]
            if first_check_in.status == AttendanceStatus.LATE.value:
                state = "late"
                reasons.append("Check-in was recorded after the allowed 10-minute threshold.")
            if first_check_in.status in {
                AttendanceStatus.NEEDS_REVIEW.value,
                AttendanceStatus.OUTSIDE_GEOFENCE.value,
                AttendanceStatus.FACE_MISMATCH.value,
            }:
                state = "needs_review"
                review_required = True
                reasons.append(first_check_in.decision_reason or "Check-in requires supervisor review.")

            if not check_outs:
                state = "half_day"
                review_required = True
                reasons.append("Missing check-out. Marked as half day and needs review.")
            else:
                last_check_out = check_outs[-1]
                if last_check_out.status == AttendanceStatus.NEEDS_REVIEW.value:
                    state = "half_day"
                    review_required = True
                    reasons.append("Early or irregular check-out requires supervisor review.")
                elif last_check_out.status in {
                    AttendanceStatus.OUTSIDE_GEOFENCE.value,
                    AttendanceStatus.FACE_MISMATCH.value,
                }:
                    state = "needs_review"
                    review_required = True
                    reasons.append(last_check_out.decision_reason or "Check-out requires supervisor review.")

        results.append(
            DailyAttendanceState(
                student_id=int(roster.student_id),
                roster_id=int(roster.id),
                student_code=getattr(roster.student, "student_code", None),
                student_name=getattr(roster.student, "full_name", None),
                iti_name=getattr(roster.student, "iti_name", None),
                trade=getattr(roster.student, "trade", None),
                industry_id=int(roster.industry_id) if roster.industry_id is not None else None,
                industry_code=getattr(roster.industry, "industry_code", None),
                industry_name=getattr(roster.industry, "name", None),
                shift_start_time=roster.shift_start_time,
                shift_end_time=roster.shift_end_time,
                state=state,
                review_required=review_required,
                reasons=reasons,
                check_in_event_id=check_ins[0].id if check_ins else None,
                check_out_event_id=check_outs[-1].id if check_outs else None,
            )
        )

    return results
