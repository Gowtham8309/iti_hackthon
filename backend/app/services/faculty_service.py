from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.database_models import Student, User, UserRole
from app.services.auth_service import get_user_by_username
from app.services.crud_service import get_student_by_code


FACULTY_TRADE_HINTS = (
    "faculty",
    "instructor",
    "trainer",
    "lecturer",
    "teacher",
)


def get_profile_for_user(db: Session, user: User) -> Student | None:
    if user.role not in {UserRole.STUDENT.value, UserRole.FACULTY.value}:
        return None
    return get_student_by_code(db, user.username)


def is_faculty_profile(db: Session, student: Student) -> bool:
    linked_user = get_user_by_username(db, student.student_code)
    if linked_user and linked_user.role == UserRole.FACULTY.value:
        return True

    trade_value = (student.trade or "").strip().lower()
    batch_value = (student.batch or "").strip().lower()
    code_value = (student.student_code or "").strip().lower()

    if code_value.startswith("fac-"):
        return True

    if "faculty" in batch_value:
        return True

    return any(hint in trade_value for hint in FACULTY_TRADE_HINTS)


def profile_type_for_student(db: Session, student: Student) -> str:
    return "faculty" if is_faculty_profile(db, student) else "student"


def list_faculty_profiles(db: Session) -> list[Student]:
    items = db.execute(select(Student).order_by(Student.id.desc())).scalars().all()
    return [item for item in items if is_faculty_profile(db, item)]
