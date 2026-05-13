from datetime import datetime, timezone
from enum import Enum

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    create_engine,
    inspect,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.database import Base, engine


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class UserRole(str, Enum):
    FACULTY = "faculty"
    STUDENT = "student"
    SUPERVISOR = "supervisor"
    HR = "hr"
    ITI_COORDINATOR = "iti_coordinator"
    DISTRICT_OFFICER = "district_officer"
    ADMIN = "admin"


class AttendanceEventType(str, Enum):
    CHECK_IN = "check_in"
    CHECK_OUT = "check_out"


class AttendanceStatus(str, Enum):
    PRESENT = "present"
    LATE = "late"
    ABSENT = "absent"
    OUTSIDE_GEOFENCE = "outside_geofence"
    FACE_MISMATCH = "face_mismatch"
    NEEDS_REVIEW = "needs_review"
    REJECTED = "rejected"


class AnomalySeverity(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class ReviewStatus(str, Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    ESCALATED = "escalated"


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)

    full_name: Mapped[str] = mapped_column(String(150), nullable=False)
    email: Mapped[str | None] = mapped_column(String(150), unique=True, index=True, nullable=True)
    mobile: Mapped[str | None] = mapped_column(String(20), unique=True, index=True, nullable=True)

    username: Mapped[str] = mapped_column(String(100), unique=True, index=True, nullable=False)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)

    role: Mapped[str] = mapped_column(String(50), index=True, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        onupdate=utc_now,
        nullable=False,
    )


class Student(Base):
    __tablename__ = "students"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)

    student_code: Mapped[str] = mapped_column(String(100), unique=True, index=True, nullable=False)
    full_name: Mapped[str] = mapped_column(String(150), nullable=False)

    iti_name: Mapped[str] = mapped_column(String(150), index=True, nullable=False)
    trade: Mapped[str] = mapped_column(String(150), index=True, nullable=False)
    batch: Mapped[str] = mapped_column(String(100), index=True, nullable=False)

    mobile: Mapped[str | None] = mapped_column(String(20), index=True, nullable=True)
    email: Mapped[str | None] = mapped_column(String(150), index=True, nullable=True)

    consent_status: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    # Store encrypted/vectorized face template later.
    # For now, JSONB keeps it flexible.
    face_embedding: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    face_enrolled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        onupdate=utc_now,
        nullable=False,
    )

    rosters: Mapped[list["TrainingRoster"]] = relationship(back_populates="student")
    attendance_events: Mapped[list["AttendanceEvent"]] = relationship(back_populates="student")
    anomaly_flags: Mapped[list["AnomalyFlag"]] = relationship(back_populates="student")


class Industry(Base):
    __tablename__ = "industries"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)

    industry_code: Mapped[str] = mapped_column(String(100), unique=True, index=True, nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    address: Mapped[str | None] = mapped_column(Text, nullable=True)

    district: Mapped[str | None] = mapped_column(String(100), index=True, nullable=True)
    city: Mapped[str | None] = mapped_column(String(100), index=True, nullable=True)

    latitude: Mapped[float] = mapped_column(Float, nullable=False)
    longitude: Mapped[float] = mapped_column(Float, nullable=False)

    geofence_radius_meters: Mapped[int] = mapped_column(Integer, default=100, nullable=False)

    hr_name: Mapped[str | None] = mapped_column(String(150), nullable=True)
    hr_mobile: Mapped[str | None] = mapped_column(String(20), nullable=True)
    hr_email: Mapped[str | None] = mapped_column(String(150), nullable=True)

    supervisor_name: Mapped[str | None] = mapped_column(String(150), nullable=True)
    supervisor_mobile: Mapped[str | None] = mapped_column(String(20), nullable=True)
    supervisor_email: Mapped[str | None] = mapped_column(String(150), nullable=True)

    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        onupdate=utc_now,
        nullable=False,
    )

    rosters: Mapped[list["TrainingRoster"]] = relationship(back_populates="industry")
    attendance_events: Mapped[list["AttendanceEvent"]] = relationship(back_populates="industry")


class TrainingRoster(Base):
    __tablename__ = "training_rosters"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)

    student_id: Mapped[int] = mapped_column(ForeignKey("students.id"), nullable=False, index=True)
    industry_id: Mapped[int] = mapped_column(ForeignKey("industries.id"), nullable=False, index=True)

    start_date: Mapped[datetime] = mapped_column(Date, nullable=False)
    end_date: Mapped[datetime] = mapped_column(Date, nullable=False)

    shift_start_time: Mapped[str] = mapped_column(String(20), nullable=False)  # HH:MM
    shift_end_time: Mapped[str] = mapped_column(String(20), nullable=False)    # HH:MM

    supervisor_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True, index=True)
    hr_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True, index=True)

    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        onupdate=utc_now,
        nullable=False,
    )

    student: Mapped["Student"] = relationship(back_populates="rosters")
    industry: Mapped["Industry"] = relationship(back_populates="rosters")


class AttendanceEvent(Base):
    __tablename__ = "attendance_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)

    student_id: Mapped[int] = mapped_column(ForeignKey("students.id"), nullable=False, index=True)
    industry_id: Mapped[int] = mapped_column(ForeignKey("industries.id"), nullable=False, index=True)
    roster_id: Mapped[int | None] = mapped_column(ForeignKey("training_rosters.id"), nullable=True, index=True)

    event_type: Mapped[str] = mapped_column(String(50), index=True, nullable=False)
    status: Mapped[str] = mapped_column(String(50), index=True, nullable=False)

    event_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, index=True, nullable=False)

    latitude: Mapped[float] = mapped_column(Float, nullable=False)
    longitude: Mapped[float] = mapped_column(Float, nullable=False)
    gps_accuracy_meters: Mapped[float | None] = mapped_column(Float, nullable=True)
    distance_from_industry_meters: Mapped[float | None] = mapped_column(Float, nullable=True)

    face_match_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    liveness_score: Mapped[float | None] = mapped_column(Float, nullable=True)

    device_id: Mapped[str | None] = mapped_column(String(255), index=True, nullable=True)
    browser_info: Mapped[str | None] = mapped_column(Text, nullable=True)
    ip_address: Mapped[str | None] = mapped_column(String(100), nullable=True)

    decision_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    raw_metadata: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)

    student: Mapped["Student"] = relationship(back_populates="attendance_events")
    industry: Mapped["Industry"] = relationship(back_populates="attendance_events")
    anomaly_flags: Mapped[list["AnomalyFlag"]] = relationship(back_populates="attendance_event")


class AnomalyFlag(Base):
    __tablename__ = "anomaly_flags"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)

    attendance_event_id: Mapped[int | None] = mapped_column(
        ForeignKey("attendance_events.id"),
        nullable=True,
        index=True,
    )
    student_id: Mapped[int] = mapped_column(ForeignKey("students.id"), nullable=False, index=True)

    anomaly_type: Mapped[str] = mapped_column(String(100), index=True, nullable=False)
    severity: Mapped[str] = mapped_column(String(50), index=True, nullable=False)

    risk_score: Mapped[float] = mapped_column(Float, nullable=False)
    explanation: Mapped[str] = mapped_column(Text, nullable=False)

    review_status: Mapped[str] = mapped_column(String(50), default=ReviewStatus.PENDING.value, index=True, nullable=False)
    reviewed_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    review_notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)

    student: Mapped["Student"] = relationship(back_populates="anomaly_flags")
    attendance_event: Mapped["AttendanceEvent"] = relationship(back_populates="anomaly_flags")


class PasswordResetToken(Base):
    __tablename__ = "password_reset_tokens"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    token: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    used: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)

    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True, index=True)
    action: Mapped[str] = mapped_column(String(150), index=True, nullable=False)

    entity_type: Mapped[str | None] = mapped_column(String(100), index=True, nullable=True)
    entity_id: Mapped[str | None] = mapped_column(String(100), index=True, nullable=True)

    ip_address: Mapped[str | None] = mapped_column(String(100), nullable=True)
    metadata_json: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)


class ClassroomObservation(Base):
    __tablename__ = "classroom_observations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)

    faculty_id: Mapped[int] = mapped_column(ForeignKey("students.id"), nullable=False, index=True)
    industry_id: Mapped[int | None] = mapped_column(ForeignKey("industries.id"), nullable=True, index=True)
    observer_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True, index=True)

    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, index=True, nullable=False)
    session_status: Mapped[str] = mapped_column(String(50), index=True, nullable=False)
    discipline_score: Mapped[float] = mapped_column(Float, nullable=False)
    teaching_quality_score: Mapped[float] = mapped_column(Float, nullable=False)
    student_engagement_score: Mapped[float] = mapped_column(Float, nullable=False)

    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    evidence_metadata: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    anomaly_signals: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)


Index("idx_attendance_student_time", AttendanceEvent.student_id, AttendanceEvent.event_time)
Index("idx_attendance_industry_time", AttendanceEvent.industry_id, AttendanceEvent.event_time)
Index("idx_anomaly_student_severity", AnomalyFlag.student_id, AnomalyFlag.severity)
Index("idx_classroom_observation_faculty_time", ClassroomObservation.faculty_id, ClassroomObservation.observed_at)


def create_all_tables() -> list[str]:
    """
    Creates all tables in the connected Neon database.
    This is okay for early development.
    Later we will shift to Alembic migrations.
    """
    Base.metadata.create_all(bind=engine)

    inspector = inspect(engine)
    return sorted(inspector.get_table_names())


if __name__ == "__main__":
    tables = create_all_tables()
    print("Database tables created successfully.")
    print("Tables:")
    for table in tables:
        print(f"- {table}")
