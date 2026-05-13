from datetime import date
from typing import Any, Sequence

from geopy.geocoders import Nominatim
from geopy.exc import GeocoderServiceError
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.database import SessionLocal
from app.models.database_models import Industry, Student, TrainingRoster
from app.schemas.api_schemas import (
    IndustryCreate,
    IndustryUpdate,
    StudentCreate,
    StudentUpdate,
    TrainingRosterCreate,
    TrainingRosterUpdate,
)


# -----------------------------
# Students
# -----------------------------

def get_student_by_id(db: Session, student_id: int) -> Student | None:
    return db.get(Student, student_id)


def get_student_by_code(db: Session, student_code: str) -> Student | None:
    stmt = select(Student).where(Student.student_code == student_code)
    return db.execute(stmt).scalar_one_or_none()


def list_students(db: Session, skip: int = 0, limit: int = 100) -> Sequence[Student]:
    stmt = (
        select(Student)
        .order_by(Student.id.desc())
        .offset(skip)
        .limit(limit)
    )
    return db.execute(stmt).scalars().all()




def create_student(db: Session, payload: StudentCreate) -> Student:
    existing = get_student_by_code(db, payload.student_code)
    if existing:
        raise ValueError(f"Student already exists with code: {payload.student_code}")

    student = Student(**payload.model_dump())
    db.add(student)
    db.commit()
    db.refresh(student)
    return student


def update_student(db: Session, student_id: int, payload: StudentUpdate) -> Student:
    student = get_student_by_id(db, student_id)
    if not student:
        raise ValueError(f"Student not found with id: {student_id}")

    updates = payload.model_dump(exclude_unset=True)

    for key, value in updates.items():
        setattr(student, key, value)

    db.commit()
    db.refresh(student)
    return student


# -----------------------------
# Industries
# -----------------------------

def get_industry_by_id(db: Session, industry_id: int) -> Industry | None:
    return db.get(Industry, industry_id)


def get_industry_by_code(db: Session, industry_code: str) -> Industry | None:
    stmt = select(Industry).where(Industry.industry_code == industry_code)
    return db.execute(stmt).scalar_one_or_none()


def list_industries(db: Session, skip: int = 0, limit: int = 100) -> Sequence[Industry]:
    stmt = (
        select(Industry)
        .order_by(Industry.id.desc())
        .offset(skip)
        .limit(limit)
    )
    return db.execute(stmt).scalars().all()


def create_industry(db: Session, payload: IndustryCreate) -> Industry:
    existing = get_industry_by_code(db, payload.industry_code)
    if existing:
        raise ValueError(f"Industry already exists with code: {payload.industry_code}")

    industry = Industry(**payload.model_dump())
    db.add(industry)
    db.commit()
    db.refresh(industry)
    return industry


def update_industry(db: Session, industry_id: int, payload: IndustryUpdate) -> Industry:
    industry = get_industry_by_id(db, industry_id)
    if not industry:
        raise ValueError(f"Industry not found with id: {industry_id}")

    updates = payload.model_dump(exclude_unset=True)

    for key, value in updates.items():
        setattr(industry, key, value)

    db.commit()
    db.refresh(industry)
    return industry


# -----------------------------
# Training Rosters
# -----------------------------

def get_roster_by_id(db: Session, roster_id: int) -> TrainingRoster | None:
    return db.get(TrainingRoster, roster_id)


def list_rosters(db: Session, skip: int = 0, limit: int = 100) -> Sequence[TrainingRoster]:
    stmt = (
        select(TrainingRoster)
        .order_by(TrainingRoster.id.desc())
        .offset(skip)
        .limit(limit)
    )
    return db.execute(stmt).scalars().all()


def get_active_roster_for_student(db: Session, student_id: int) -> TrainingRoster | None:
    today = date.today()

    stmt = (
        select(TrainingRoster)
        .where(TrainingRoster.student_id == student_id)
        .where(TrainingRoster.is_active == True)  # noqa: E712
        .where(TrainingRoster.start_date <= today)
        .where(TrainingRoster.end_date >= today)
        .order_by(TrainingRoster.id.desc())
    )

    return db.execute(stmt).scalar_one_or_none()


def create_roster(db: Session, payload: TrainingRosterCreate) -> TrainingRoster:
    student = get_student_by_id(db, payload.student_id)
    if not student:
        raise ValueError(f"Student not found with id: {payload.student_id}")

    industry = get_industry_by_id(db, payload.industry_id)
    if not industry:
        raise ValueError(f"Industry not found with id: {payload.industry_id}")

    roster = TrainingRoster(**payload.model_dump())
    db.add(roster)
    db.commit()
    db.refresh(roster)
    return roster


def update_roster(db: Session, roster_id: int, payload: TrainingRosterUpdate) -> TrainingRoster:
    roster = get_roster_by_id(db, roster_id)
    if not roster:
        raise ValueError(f"Roster not found with id: {roster_id}")

    updates = payload.model_dump(exclude_unset=True)

    for key, value in updates.items():
        setattr(roster, key, value)

    db.commit()
    db.refresh(roster)
    return roster


# -----------------------------
# GPS Geocoding
# -----------------------------

_geocoder = Nominatim(user_agent="iti-attendance-ai/1.0")


def geocode_industry(industry: Industry) -> dict[str, Any]:
    """
    Attempts to geocode an industry using its name, city, and district via Nominatim.

    Returns a dict with:
      - resolved: bool
      - latitude, longitude: floats (updated values if resolved)
      - display_name: str | None
      - error: str | None
    """
    query_parts = [p for p in [industry.name, industry.city, industry.district, "India"] if p]
    query = ", ".join(query_parts)

    try:
        location = _geocoder.geocode(query, timeout=10)
    except GeocoderServiceError as exc:
        return {"resolved": False, "latitude": industry.latitude, "longitude": industry.longitude, "error": str(exc)}

    if not location:
        return {"resolved": False, "latitude": industry.latitude, "longitude": industry.longitude, "error": "No result from geocoder"}

    return {
        "resolved": True,
        "latitude": location.latitude,
        "longitude": location.longitude,
        "display_name": location.address,
        "error": None,
    }


def geocode_industries_with_missing_coords(
    db: Session,
    *,
    dry_run: bool = False,
    limit: int = 50,
) -> dict[str, Any]:
    """
    Finds industries where latitude == 0.0 and longitude == 0.0
    (placeholder set during OJT import) and resolves their coordinates.

    Set dry_run=True to preview results without writing to the database.
    Limit is capped at 50 per call to avoid Nominatim rate limits.
    """
    stmt = (
        select(Industry)
        .where(Industry.latitude == 0.0)
        .where(Industry.longitude == 0.0)
        .limit(min(limit, 50))
    )
    industries = db.execute(stmt).scalars().all()

    results: list[dict[str, Any]] = []

    for industry in industries:
        geo = geocode_industry(industry)
        entry: dict[str, Any] = {
            "industry_id": industry.id,
            "industry_code": industry.industry_code,
            "name": industry.name,
            "district": industry.district,
            **geo,
        }

        if geo["resolved"] and not dry_run:
            industry.latitude = geo["latitude"]
            industry.longitude = geo["longitude"]

        results.append(entry)

    if not dry_run:
        db.commit()

    resolved_count = sum(1 for r in results if r["resolved"])

    return {
        "dry_run": dry_run,
        "total_checked": len(results),
        "resolved": resolved_count,
        "failed": len(results) - resolved_count,
        "items": results,
    }


# -----------------------------
# Real DB self-test
# -----------------------------

def run_crud_self_test() -> dict:
    """
    Real Neon DB self-test.
    Creates or reuses:
    - one demo student
    - one demo industry
    - one active roster

    This is intentionally idempotent so repeated runs do not create duplicates.
    """
    db = SessionLocal()

    try:
        student_payload = StudentCreate(
            student_code="ITI-VSP-DEMO-001",
            full_name="Ravi Kumar",
            iti_name="Govt ITI Visakhapatnam",
            trade="Electrician",
            batch="2026",
            mobile="9876543210",
            consent_status=True,
        )

        industry_payload = IndustryCreate(
            industry_code="IND-VSP-DEMO-001",
            name="Vizag Steel Partner Workshop",
            address="Demo Industrial Training Site, Visakhapatnam",
            district="Visakhapatnam",
            city="Visakhapatnam",
            latitude=17.6868,
            longitude=83.2185,
            geofence_radius_meters=100,
            supervisor_name="Demo Supervisor",
            supervisor_mobile="9000000001",
            hr_name="Demo HR",
            hr_mobile="9000000002",
        )

        student = get_student_by_code(db, student_payload.student_code)
        student_created = False
        if not student:
            student = create_student(db, student_payload)
            student_created = True

        industry = get_industry_by_code(db, industry_payload.industry_code)
        industry_created = False
        if not industry:
            industry = create_industry(db, industry_payload)
            industry_created = True

        active_roster = get_active_roster_for_student(db, student.id)
        roster_created = False

        if not active_roster:
            roster_payload = TrainingRosterCreate(
                student_id=student.id,
                industry_id=industry.id,
                start_date=date(2026, 1, 1),
                end_date=date(2026, 12, 31),
                shift_start_time="09:00",
                shift_end_time="17:00",
            )
            active_roster = create_roster(db, roster_payload)
            roster_created = True

        students_count = len(list_students(db, limit=1000))
        industries_count = len(list_industries(db, limit=1000))
        rosters_count = len(list_rosters(db, limit=1000))

        return {
            "crud_self_test": "passed",
            "student": {
                "id": student.id,
                "student_code": student.student_code,
                "created_now": student_created,
            },
            "industry": {
                "id": industry.id,
                "industry_code": industry.industry_code,
                "created_now": industry_created,
            },
            "active_roster": {
                "id": active_roster.id,
                "created_now": roster_created,
            },
            "database_counts": {
                "students": students_count,
                "industries": industries_count,
                "rosters": rosters_count,
            },
        }

    finally:
        db.close()


if __name__ == "__main__":
    result = run_crud_self_test()
    print(result)
