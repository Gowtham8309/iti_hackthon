from __future__ import annotations

from datetime import date
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.db.database import SessionLocal
from app.models.database_models import (
    AnomalyFlag,
    AttendanceEvent,
    Industry,
    Student,
    TrainingRoster,
    User,
    UserRole,
)
from app.services.auth_service import hash_password


# ---------------------------------------------------------------------
# Dual-role demo setup
# ---------------------------------------------------------------------

DEMO_FACULTY_CODE = "FAC-GNT-DEMO-001"
DEMO_STUDENT_CODE = "STU-GNT-DEMO-001"
DEMO_ITI_LAB_CODE = "ITI-GNT-LAB-001"

# Old demo codes from earlier trainee/in-plant version.
# We use these to preserve face enrollment if it already exists.
OLD_TRAINEE_CODE = "ITI-VSP-DEMO-001"
OLD_INDUSTRY_CODE = "IND-VSP-DEMO-001"

DEMO_FACULTY_PASSWORD = "faculty123"
DEMO_STUDENT_PASSWORD = "student123"


def _count_rows(db: Session, model: Any) -> int:
    return len(db.execute(select(model)).scalars().all())


def _get_all_students(db: Session) -> list[Student]:
    return db.execute(
        select(Student).order_by(Student.id.asc())
    ).scalars().all()


def _get_all_industries(db: Session) -> list[Industry]:
    return db.execute(
        select(Industry).order_by(Industry.id.asc())
    ).scalars().all()


def _get_all_users(db: Session) -> list[User]:
    return db.execute(
        select(User).order_by(User.id.asc())
    ).scalars().all()


def _find_user_by_username(users: list[User], username: str) -> User | None:
    for user in users:
        if getattr(user, "username", None) == username:
            return user
    return None


def _clear_user_conflicts(
    users: list[User],
    *,
    keep_user: User | None,
    email: str | None,
    mobile: str | None,
) -> None:
    keep_id = getattr(keep_user, "id", None)

    for user in users:
        if getattr(user, "id", None) == keep_id:
            continue
        if email and getattr(user, "email", None) == email:
            user.email = None
        if mobile and getattr(user, "mobile", None) == mobile:
            user.mobile = None


def _upsert_demo_user(
    db: Session,
    users: list[User],
    *,
    username: str,
    full_name: str,
    role: str,
    password: str,
    email: str | None,
    mobile: str | None,
) -> User:
    user = _find_user_by_username(users, username)

    _clear_user_conflicts(
        users,
        keep_user=user,
        email=email,
        mobile=mobile,
    )

    if user is None:
        user = User(
            username=username,
            full_name=full_name,
            role=role,
            hashed_password=hash_password(password),
            email=email,
            mobile=mobile,
            is_active=True,
        )
        db.add(user)
        db.flush()
        users.append(user)
        return user

    user.full_name = full_name
    user.role = role
    user.hashed_password = hash_password(password)
    user.email = email
    user.mobile = mobile
    user.is_active = True
    db.flush()
    return user


def _find_existing_faculty_candidate(students: list[Student]) -> Student | None:
    """
    Pick one existing row to become the demo faculty.

    Priority:
    1. FAC-GNT-DEMO-001 if it exists
    2. Old Ravi demo record with face enrollment
    3. Any Ravi Kumar row
    4. First face-enrolled row
    """
    exact = [
        s for s in students
        if getattr(s, "student_code", None) == DEMO_FACULTY_CODE
    ]
    if exact:
        return exact[0]

    old_ravi = [
        s for s in students
        if getattr(s, "student_code", None) == OLD_TRAINEE_CODE
    ]
    if old_ravi:
        old_ravi.sort(
            key=lambda item: (
                0 if getattr(item, "face_enrolled", False) else 1,
                getattr(item, "id", 999999),
            )
        )
        return old_ravi[0]

    ravi_rows = [
        s for s in students
        if "ravi" in (getattr(s, "full_name", "") or "").lower()
    ]
    if ravi_rows:
        ravi_rows.sort(
            key=lambda item: (
                0 if getattr(item, "face_enrolled", False) else 1,
                getattr(item, "id", 999999),
            )
        )
        return ravi_rows[0]

    face_rows = [
        s for s in students
        if getattr(s, "face_enrolled", False)
    ]
    if face_rows:
        face_rows.sort(key=lambda item: getattr(item, "id", 999999))
        return face_rows[0]

    return None


def _find_existing_student_candidate(
    students: list[Student],
    faculty: Student | None,
) -> Student | None:
    """
    Pick one existing row to become the demo student.

    Avoid using the faculty row.
    """
    faculty_id = getattr(faculty, "id", None)

    exact = [
        s for s in students
        if getattr(s, "student_code", None) == DEMO_STUDENT_CODE
        and getattr(s, "id", None) != faculty_id
    ]
    if exact:
        return exact[0]

    suresh_rows = [
        s for s in students
        if "suresh" in (getattr(s, "full_name", "") or "").lower()
        and getattr(s, "id", None) != faculty_id
    ]
    if suresh_rows:
        suresh_rows.sort(key=lambda item: getattr(item, "id", 999999))
        return suresh_rows[0]

    remaining = [
        s for s in students
        if getattr(s, "id", None) != faculty_id
    ]
    if remaining:
        remaining.sort(key=lambda item: getattr(item, "id", 999999))
        return remaining[0]

    return None


def _find_existing_iti_lab_candidate(industries: list[Industry]) -> Industry | None:
    """
    Pick one existing row to become the demo ITI lab / classroom location.
    """
    exact = [
        i for i in industries
        if getattr(i, "industry_code", None) == DEMO_ITI_LAB_CODE
    ]
    if exact:
        return exact[0]

    old = [
        i for i in industries
        if getattr(i, "industry_code", None) == OLD_INDUSTRY_CODE
    ]
    if old:
        return old[0]

    likely = []
    for industry in industries:
        name = (getattr(industry, "name", "") or "").lower()
        if "iti" in name or "lab" in name or "workshop" in name:
            likely.append(industry)

    if likely:
        likely.sort(key=lambda item: getattr(item, "id", 999999))
        return likely[0]

    if industries:
        industries.sort(key=lambda item: getattr(item, "id", 999999))
        return industries[0]

    return None


def _apply_faculty_values(
    faculty: Student,
    *,
    keep_face_enrollment: bool,
) -> Student:
    """
    Rebrands one Student row as demo faculty.
    """
    faculty.student_code = DEMO_FACULTY_CODE
    faculty.full_name = "Ravi Kumar"
    faculty.iti_name = "Govt ITI Guntur"
    faculty.trade = "Electrical Instructor"
    faculty.batch = "Faculty Batch 2026"
    faculty.mobile = "9000000001"
    faculty.email = "ravi.faculty@govtiti.ap.gov.in"
    faculty.consent_status = True
    faculty.is_active = True

    if not keep_face_enrollment:
        faculty.face_enrolled = False
        faculty.face_embedding = None

    return faculty


def _apply_student_values(
    student: Student,
    *,
    keep_student_face_enrollment: bool,
) -> Student:
    """
    Rebrands one Student row as demo trainee/student.
    """
    student.student_code = DEMO_STUDENT_CODE
    student.full_name = "Suresh Kumar"
    student.iti_name = "Govt ITI Guntur"
    student.trade = "Electrician Trainee"
    student.batch = "Student Batch 2026"
    student.mobile = "9000000004"
    student.email = "suresh.student@govtiti.ap.gov.in"
    student.consent_status = True
    student.is_active = True

    if not keep_student_face_enrollment:
        student.face_enrolled = False
        student.face_embedding = None

    return student


def _create_demo_faculty(
    db: Session,
    *,
    keep_face_enrollment: bool,
) -> Student:
    faculty = Student(
        student_code=DEMO_FACULTY_CODE,
        full_name="Ravi Kumar",
        iti_name="Govt ITI Guntur",
        trade="Electrical Instructor",
        batch="Faculty Batch 2026",
        mobile="9000000001",
        email="ravi.faculty@govtiti.ap.gov.in",
        consent_status=True,
        face_enrolled=False,
        face_embedding=None,
        is_active=True,
    )

    if not keep_face_enrollment:
        faculty.face_enrolled = False
        faculty.face_embedding = None

    db.add(faculty)
    db.flush()
    return faculty


def _create_demo_student(
    db: Session,
    *,
    keep_student_face_enrollment: bool,
) -> Student:
    student = Student(
        student_code=DEMO_STUDENT_CODE,
        full_name="Suresh Kumar",
        iti_name="Govt ITI Guntur",
        trade="Electrician Trainee",
        batch="Student Batch 2026",
        mobile="9000000004",
        email="suresh.student@govtiti.ap.gov.in",
        consent_status=True,
        face_enrolled=False,
        face_embedding=None,
        is_active=True,
    )

    if not keep_student_face_enrollment:
        student.face_enrolled = False
        student.face_embedding = None

    db.add(student)
    db.flush()
    return student


def _apply_iti_lab_values(industry: Industry) -> Industry:
    """
    Rebrands one Industry row as demo ITI/classroom/lab location.
    """
    industry.industry_code = DEMO_ITI_LAB_CODE
    industry.name = "Govt ITI Guntur - Electrical Lab"
    industry.address = "Govt ITI Campus, Guntur District, Andhra Pradesh"
    industry.district = "Guntur"
    industry.city = "Guntur"

    # Shared valid demo location for both faculty and student flows.
    industry.latitude = 16.3067
    industry.longitude = 80.4365
    industry.geofence_radius_meters = 100

    industry.hr_name = "Principal Demo"
    industry.hr_mobile = "9000000002"
    industry.hr_email = "principal@govtiti.ap.gov.in"

    industry.supervisor_name = "District Training Officer Demo"
    industry.supervisor_mobile = "9000000003"
    industry.supervisor_email = "dto.guntur@ap.gov.in"

    industry.is_active = True

    return industry


def _create_demo_iti_lab(db: Session) -> Industry:
    industry = Industry(
        industry_code=DEMO_ITI_LAB_CODE,
        name="Govt ITI Guntur - Electrical Lab",
        address="Govt ITI Campus, Guntur District, Andhra Pradesh",
        district="Guntur",
        city="Guntur",
        latitude=16.3067,
        longitude=80.4365,
        geofence_radius_meters=100,
        hr_name="Principal Demo",
        hr_mobile="9000000002",
        hr_email="principal@govtiti.ap.gov.in",
        supervisor_name="District Training Officer Demo",
        supervisor_mobile="9000000003",
        supervisor_email="dto.guntur@ap.gov.in",
        is_active=True,
    )

    db.add(industry)
    db.flush()
    return industry


def _create_schedule(
    db: Session,
    *,
    person: Student,
    location: Industry,
    start_time: str,
    end_time: str,
) -> TrainingRoster:
    roster = TrainingRoster(
        student_id=person.id,
        industry_id=location.id,
        start_date=date(2026, 1, 1),
        end_date=date(2026, 12, 31),
        shift_start_time=start_time,
        shift_end_time=end_time,
        is_active=True,
    )

    db.add(roster)
    db.flush()
    return roster


def reset_demo_data(
    *,
    keep_faculty_face_enrollment: bool = True,
    keep_student_face_enrollment: bool = False,
    strict_master_data: bool = True,
) -> dict:
    """
    Dual-role reset for combined hackathon solution.

    Creates:
    - one faculty record
    - one student/trainee record
    - one ITI lab/classroom location
    - one faculty teaching schedule
    - one student training roster

    Clears:
    - attendance events
    - anomaly flags
    - all old schedules/rosters

    If strict_master_data=True:
    - removes extra test-created students/faculty
    - removes extra test-created industries/locations

    Users/admin accounts are preserved.
    """
    db = SessionLocal()

    try:
        attendance_before = _count_rows(db, AttendanceEvent)
        anomaly_before = _count_rows(db, AnomalyFlag)
        roster_before = _count_rows(db, TrainingRoster)
        student_before = _count_rows(db, Student)
        industry_before = _count_rows(db, Industry)

        # Delete event-level records first.
        db.execute(delete(AnomalyFlag))
        db.execute(delete(AttendanceEvent))

        # Delete schedules before removing/rewriting master data.
        db.execute(delete(TrainingRoster))
        db.flush()

        all_students = _get_all_students(db)
        all_industries = _get_all_industries(db)
        all_users = _get_all_users(db)

        faculty_candidate = _find_existing_faculty_candidate(all_students)
        student_candidate = _find_existing_student_candidate(
            all_students,
            faculty_candidate,
        )
        iti_lab_candidate = _find_existing_iti_lab_candidate(all_industries)

        if strict_master_data:
            keep_student_ids = set()

            if faculty_candidate is not None:
                keep_student_ids.add(faculty_candidate.id)

            if student_candidate is not None:
                keep_student_ids.add(student_candidate.id)

            for student in all_students:
                if student.id not in keep_student_ids:
                    db.delete(student)

            keep_industry_ids = set()

            if iti_lab_candidate is not None:
                keep_industry_ids.add(iti_lab_candidate.id)

            for industry in all_industries:
                if industry.id not in keep_industry_ids:
                    db.delete(industry)

            db.flush()

        if faculty_candidate is None:
            faculty = _create_demo_faculty(
                db,
                keep_face_enrollment=keep_faculty_face_enrollment,
            )
        else:
            faculty = _apply_faculty_values(
                faculty_candidate,
                keep_face_enrollment=keep_faculty_face_enrollment,
            )

        db.flush()

        # Re-read students because strict delete + faculty rewrite can affect uniqueness.
        all_students_after_faculty = _get_all_students(db)

        # Ensure student candidate is not the same row as faculty after rewrite.
        if student_candidate is not None and student_candidate.id == faculty.id:
            student_candidate = None

        if student_candidate is None:
            remaining_student_candidate = _find_existing_student_candidate(
                all_students_after_faculty,
                faculty,
            )
            student_candidate = remaining_student_candidate

        if student_candidate is None:
            student = _create_demo_student(
                db,
                keep_student_face_enrollment=keep_student_face_enrollment,
            )
        else:
            student = _apply_student_values(
                student_candidate,
                keep_student_face_enrollment=keep_student_face_enrollment,
            )

        db.flush()

        if iti_lab_candidate is None:
            iti_lab = _create_demo_iti_lab(db)
        else:
            iti_lab = _apply_iti_lab_values(iti_lab_candidate)

        db.flush()

        faculty_schedule = _create_schedule(
            db,
            person=faculty,
            location=iti_lab,
            start_time="09:00",
            end_time="17:00",
        )

        student_roster = _create_schedule(
            db,
            person=student,
            location=iti_lab,
            start_time="09:00",
            end_time="17:00",
        )

        db.flush()

        student_after = _count_rows(db, Student)
        industry_after = _count_rows(db, Industry)
        roster_after = _count_rows(db, TrainingRoster)

        faculty_user = _upsert_demo_user(
            db,
            all_users,
            username=faculty.student_code,
            full_name=faculty.full_name,
            role=UserRole.FACULTY.value,
            password=DEMO_FACULTY_PASSWORD,
            email=faculty.email,
            mobile=faculty.mobile,
        )

        student_user = _upsert_demo_user(
            db,
            all_users,
            username=student.student_code,
            full_name=student.full_name,
            role=UserRole.STUDENT.value,
            password=DEMO_STUDENT_PASSWORD,
            email=student.email,
            mobile=student.mobile,
        )

        db.commit()

        return {
            "demo_reset": "passed",
            "mode": "dual_faculty_and_student_monitoring",
            "strict_master_data": strict_master_data,
            "deleted": {
                "attendance_events": attendance_before,
                "anomaly_flags": anomaly_before,
                "old_rosters_or_schedules": roster_before,
                "extra_people_removed": max(student_before - student_after, 0),
                "extra_locations_removed": max(industry_before - industry_after, 0),
            },
            "kept": {
                "users": True,
                "faculty_face_enrollment": keep_faculty_face_enrollment,
                "student_face_enrollment": keep_student_face_enrollment,
            },
            "final_counts": {
                "people_records": student_after,
                "locations": industry_after,
                "schedules_or_rosters": roster_after,
            },
            "demo_faculty": {
                "id": faculty.id,
                "faculty_code": faculty.student_code,
                "full_name": faculty.full_name,
                "iti_name": faculty.iti_name,
                "designation": faculty.trade,
                "face_enrolled": getattr(faculty, "face_enrolled", None),
                "login_username": faculty_user.username,
                "login_password": DEMO_FACULTY_PASSWORD,
            },
            "demo_student": {
                "id": student.id,
                "student_code": student.student_code,
                "full_name": student.full_name,
                "iti_name": student.iti_name,
                "trade": student.trade,
                "face_enrolled": getattr(student, "face_enrolled", None),
                "login_username": student_user.username,
                "login_password": DEMO_STUDENT_PASSWORD,
            },
            "demo_location": {
                "id": iti_lab.id,
                "location_code": iti_lab.industry_code,
                "name": iti_lab.name,
                "district": iti_lab.district,
                "city": iti_lab.city,
                "latitude": iti_lab.latitude,
                "longitude": iti_lab.longitude,
                "geofence_radius_meters": iti_lab.geofence_radius_meters,
            },
            "faculty_teaching_schedule": {
                "id": faculty_schedule.id,
                "faculty_id": faculty_schedule.student_id,
                "location_id": faculty_schedule.industry_id,
                "class_start_time": faculty_schedule.shift_start_time,
                "class_end_time": faculty_schedule.shift_end_time,
                "is_active": faculty_schedule.is_active,
            },
            "student_training_roster": {
                "id": student_roster.id,
                "student_id": student_roster.student_id,
                "location_id": student_roster.industry_id,
                "training_start_time": student_roster.shift_start_time,
                "training_end_time": student_roster.shift_end_time,
                "is_active": student_roster.is_active,
            },
        }

    except Exception:
        db.rollback()
        raise

    finally:
        db.close()


if __name__ == "__main__":
    result = reset_demo_data(
        keep_faculty_face_enrollment=True,
        keep_student_face_enrollment=False,
        strict_master_data=True,
    )
    print(result)
