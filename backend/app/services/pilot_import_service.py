from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

import pandas as pd
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.database_models import Industry, Student, TrainingRoster


@dataclass
class PilotDataBundle:
    admissions: pd.DataFrame
    ojt: pd.DataFrame
    placements: pd.DataFrame | None


def _normalize_columns(df: pd.DataFrame) -> pd.DataFrame:
    renamed = {
        column: str(column).strip().upper().replace("\n", " ")
        for column in df.columns
    }
    return df.rename(columns=renamed)


def load_pilot_data(
    *,
    admissions_path: str,
    ojt_path: str,
    placements_path: str | None = None,
) -> PilotDataBundle:
    admissions_df = _normalize_columns(pd.read_excel(admissions_path))
    ojt_df = _normalize_columns(pd.read_excel(ojt_path))
    placements_df = _normalize_columns(pd.read_excel(placements_path)) if placements_path else None

    return PilotDataBundle(
        admissions=admissions_df,
        ojt=ojt_df,
        placements=placements_df,
    )


def preview_pilot_data(bundle: PilotDataBundle) -> dict[str, Any]:
    admissions = bundle.admissions
    ojt = bundle.ojt
    placements = bundle.placements

    return {
        "students_preview": {
            "rows": int(len(admissions)),
            "columns": list(admissions.columns),
            "sample": admissions.head(3).fillna("").to_dict(orient="records"),
        },
        "ojt_preview": {
            "rows": int(len(ojt)),
            "columns": list(ojt.columns),
            "sample": ojt.head(3).fillna("").to_dict(orient="records"),
        },
        "placements_preview": (
            {
                "rows": int(len(placements)),
                "columns": list(placements.columns),
                "sample": placements.head(3).fillna("").to_dict(orient="records"),
            }
            if placements is not None
            else None
        ),
    }


def _student_payload_from_row(row: pd.Series) -> dict[str, Any]:
    admission_number = str(row.get("ADMISSIONNUMBER", "")).strip()
    trade_name = str(row.get("TRADE NAME", "")).strip()
    iti_name = str(row.get("ITI NAME", "")).strip()
    mobile = row.get("MOBILE NUMBER")
    mobile_text = ""
    if pd.notna(mobile):
        mobile_text = str(int(float(mobile))) if str(mobile).replace(".", "", 1).isdigit() else str(mobile).strip()

    email = row.get("EMAIL ID")
    email_text = str(email).strip() if pd.notna(email) and str(email).strip() else None

    batch = admission_number[-2:] if len(admission_number) >= 2 else "unknown"

    return {
        "student_code": admission_number,
        "full_name": str(row.get("NAME", "")).strip(),
        "iti_name": iti_name,
        "trade": trade_name,
        "batch": batch,
        "mobile": mobile_text or None,
        "email": email_text,
        "consent_status": True,
    }


def import_students_from_admissions(db: Session, admissions_df: pd.DataFrame) -> dict[str, int]:
    created = 0
    existing = 0

    for _, row in admissions_df.iterrows():
        payload = _student_payload_from_row(row)
        student_code = payload["student_code"]
        if not student_code:
            continue

        student = db.execute(
            select(Student).where(Student.student_code == student_code)
        ).scalar_one_or_none()

        if student:
            existing += 1
            continue

        db.add(Student(**payload))
        created += 1

    db.commit()
    return {"created": created, "existing": existing}


def import_industries_from_ojt(db: Session, ojt_df: pd.DataFrame) -> dict[str, int]:
    created = 0
    existing = 0

    for _, row in ojt_df.iterrows():
        industry_name = str(row.get("INDUSTRY NAME", "")).strip()
        district_name = str(row.get("DISTRICT NAME", "")).strip()
        hr_no = row.get("HR NO")
        hr_mobile = None
        if pd.notna(hr_no):
            hr_mobile = str(int(float(hr_no))) if str(hr_no).replace(".", "", 1).isdigit() else str(hr_no).strip()

        if not industry_name:
            continue

        industry_code = f"OJT-{abs(hash((industry_name, district_name))) % 10_000_000:07d}"

        industry = db.execute(
            select(Industry).where(Industry.industry_code == industry_code)
        ).scalar_one_or_none()

        if industry:
            existing += 1
            continue

        db.add(
            Industry(
                industry_code=industry_code,
                name=industry_name,
                district=district_name or None,
                city=district_name or None,
                latitude=0.0,
                longitude=0.0,
                geofence_radius_meters=100,
                hr_mobile=hr_mobile,
                hr_name="HR Contact",
                supervisor_name=str(row.get("FACULTY NAME", "")).strip() or None,
            )
        )
        created += 1

    db.commit()
    return {"created": created, "existing": existing}


def _parse_date_cell(value: Any) -> date | None:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    if hasattr(value, "date"):
        return value.date()
    if isinstance(value, date):
        return value
    text = str(value).strip()
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y", "%d-%b-%Y"):
        try:
            from datetime import datetime as _dt
            return _dt.strptime(text, fmt).date()
        except ValueError:
            pass
    return None


def auto_assign_rosters_from_ojt(
    db: Session,
    ojt_df: pd.DataFrame,
    *,
    default_shift_start: str = "09:00",
    default_shift_end: str = "17:00",
) -> dict[str, Any]:
    """
    Auto-creates TrainingRoster records by matching OJT rows to existing
    Student and Industry records.

    Matching logic:
    - Student: matched by ADMISSIONNUMBER == student_code
    - Industry: matched by industry_code derived from (INDUSTRY NAME, DISTRICT NAME)
      (same hash used by import_industries_from_ojt)

    Skips rows where student or industry is not found, or an active roster
    already exists for that student.
    """
    created = 0
    skipped_no_student = 0
    skipped_no_industry = 0
    skipped_existing = 0
    skipped_bad_dates = 0

    for _, row in ojt_df.iterrows():
        admission_number = str(row.get("ADMISSIONNUMBER", "")).strip()
        industry_name = str(row.get("INDUSTRY NAME", "")).strip()
        district_name = str(row.get("DISTRICT NAME", "")).strip()

        if not admission_number or not industry_name:
            skipped_no_student += 1
            continue

        student = db.execute(
            select(Student).where(Student.student_code == admission_number)
        ).scalar_one_or_none()

        if not student:
            skipped_no_student += 1
            continue

        industry_code = f"OJT-{abs(hash((industry_name, district_name))) % 10_000_000:07d}"
        industry = db.execute(
            select(Industry).where(Industry.industry_code == industry_code)
        ).scalar_one_or_none()

        if not industry:
            skipped_no_industry += 1
            continue

        existing_roster = db.execute(
            select(TrainingRoster)
            .where(TrainingRoster.student_id == student.id)
            .where(TrainingRoster.is_active.is_(True))
        ).scalar_one_or_none()

        if existing_roster:
            skipped_existing += 1
            continue

        start_date = _parse_date_cell(row.get("FROM DATE"))
        end_date = _parse_date_cell(row.get("TO DATE"))

        if not start_date or not end_date or end_date < start_date:
            skipped_bad_dates += 1
            continue

        shift_start = str(row.get("SHIFT START TIME", default_shift_start) or default_shift_start).strip() or default_shift_start
        shift_end = str(row.get("SHIFT END TIME", default_shift_end) or default_shift_end).strip() or default_shift_end

        db.add(
            TrainingRoster(
                student_id=student.id,
                industry_id=industry.id,
                start_date=start_date,
                end_date=end_date,
                shift_start_time=shift_start,
                shift_end_time=shift_end,
                is_active=True,
            )
        )
        created += 1

    db.commit()

    return {
        "rosters_created": created,
        "skipped_no_student": skipped_no_student,
        "skipped_no_industry": skipped_no_industry,
        "skipped_existing_roster": skipped_existing,
        "skipped_bad_dates": skipped_bad_dates,
    }


def build_roster_import_template(
    db: Session,
    ojt_df: pd.DataFrame,
) -> list[dict[str, Any]]:
    templates: list[dict[str, Any]] = []

    for _, row in ojt_df.head(500).iterrows():
        industry_name = str(row.get("INDUSTRY NAME", "")).strip()
        if not industry_name:
            continue

        from_date = row.get("FROM DATE")
        to_date = row.get("TO DATE")

        templates.append(
            {
                "student_code": "",
                "industry_name": industry_name,
                "trade_name": str(row.get("TRADE NAME", "")).strip(),
                "iti_name": str(row.get("ITI NAME", "")).strip(),
                "district_name": str(row.get("DISTRICT NAME", "")).strip(),
                "start_date": (
                    from_date.date().isoformat()
                    if hasattr(from_date, "date")
                    else str(from_date or "")
                ),
                "end_date": (
                    to_date.date().isoformat()
                    if hasattr(to_date, "date")
                    else str(to_date or "")
                ),
                "shift_start_time": "09:00",
                "shift_end_time": "17:00",
                "supervisor_name": str(row.get("FACULTY NAME", "")).strip(),
                "hr_mobile": str(row.get("HR NO", "")).strip(),
                "notes": "Fill student_code for exact trainee-to-industry assignment.",
            }
        )

    return templates
