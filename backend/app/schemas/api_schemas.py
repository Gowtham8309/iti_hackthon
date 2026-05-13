from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field


# -----------------------------
# Common
# -----------------------------

class MessageResponse(BaseModel):
    message: str


class HealthResponse(BaseModel):
    status: str
    service: str
    environment: str


# -----------------------------
# Auth / Users
# -----------------------------

class UserCreate(BaseModel):
    full_name: str = Field(..., min_length=2, max_length=150)
    username: str = Field(..., min_length=3, max_length=100)
    password: str = Field(..., min_length=6, max_length=100)

    role: str = Field(
        ...,
        description="faculty, student, supervisor, hr, iti_coordinator, district_officer, admin",
    )

    email: EmailStr | None = None
    mobile: str | None = Field(default=None, max_length=20)


class UserLogin(BaseModel):
    username: str
    password: str


class UserResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    full_name: str
    username: str
    role: str
    email: str | None = None
    mobile: str | None = None
    is_active: bool
    created_at: datetime


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserResponse


class StudentSignupRequest(BaseModel):
    role: str = Field(default="student", description="faculty or student")
    student_code: str = Field(..., min_length=2, max_length=100)
    full_name: str = Field(..., min_length=2, max_length=150)
    iti_name: str = Field(..., min_length=2, max_length=150)
    trade: str = Field(..., min_length=2, max_length=150)
    batch: str = Field(..., min_length=1, max_length=100)
    password: str = Field(..., min_length=6, max_length=100)
    mobile: str | None = Field(default=None, max_length=20)
    email: EmailStr | None = None
    consent_status: bool = True
    selfie_image_base64: str


class AdminCreateAccountRequest(BaseModel):
    full_name: str = Field(..., min_length=2, max_length=150)
    username: str | None = Field(default=None, min_length=3, max_length=100)
    password: str = Field(..., min_length=6, max_length=100)
    role: str = Field(..., description="faculty, student, supervisor, hr, iti_coordinator, district_officer, admin")
    email: EmailStr | None = None
    mobile: str | None = Field(default=None, max_length=20)
    student_code: str | None = Field(default=None, min_length=2, max_length=100)
    iti_name: str | None = Field(default=None, min_length=2, max_length=150)
    trade: str | None = Field(default=None, min_length=2, max_length=150)
    batch: str | None = Field(default=None, min_length=1, max_length=100)
    consent_status: bool = True
    selfie_image_base64: str | None = None


# -----------------------------
# Students
# -----------------------------

class StudentCreate(BaseModel):
    student_code: str = Field(..., min_length=2, max_length=100)
    full_name: str = Field(..., min_length=2, max_length=150)

    iti_name: str = Field(..., min_length=2, max_length=150)
    trade: str = Field(..., min_length=2, max_length=150)
    batch: str = Field(..., min_length=1, max_length=100)

    mobile: str | None = Field(default=None, max_length=20)
    email: EmailStr | None = None

    consent_status: bool = False


class StudentUpdate(BaseModel):
    full_name: str | None = Field(default=None, min_length=2, max_length=150)
    iti_name: str | None = Field(default=None, min_length=2, max_length=150)
    trade: str | None = Field(default=None, min_length=2, max_length=150)
    batch: str | None = Field(default=None, min_length=1, max_length=100)
    mobile: str | None = Field(default=None, max_length=20)
    email: EmailStr | None = None
    consent_status: bool | None = None
    is_active: bool | None = None


class StudentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    student_code: str
    full_name: str

    iti_name: str
    trade: str
    batch: str

    mobile: str | None = None
    email: str | None = None

    consent_status: bool
    face_enrolled: bool
    is_active: bool

    created_at: datetime


class ClassroomObservationCreate(BaseModel):
    faculty_id: int
    industry_id: int | None = None
    observed_at: datetime | None = None
    session_status: str = Field(..., description="on_track, late_start, absent_faculty, low_engagement, needs_review")
    discipline_score: float = Field(..., ge=0, le=100)
    teaching_quality_score: float = Field(..., ge=0, le=100)
    student_engagement_score: float = Field(..., ge=0, le=100)
    notes: str | None = Field(default=None, max_length=2000)


class ClassroomObservationResponse(BaseModel):
    id: int
    faculty_id: int
    industry_id: int | None = None
    observer_user_id: int | None = None
    observed_at: datetime
    session_status: str
    discipline_score: float
    teaching_quality_score: float
    student_engagement_score: float
    notes: str | None = None
    evidence_metadata: dict | None = None
    anomaly_signals: dict | None = None
    created_at: datetime


# -----------------------------
# Industries
# -----------------------------

class IndustryCreate(BaseModel):
    industry_code: str = Field(..., min_length=2, max_length=100)
    name: str = Field(..., min_length=2, max_length=200)

    address: str | None = None
    district: str | None = Field(default=None, max_length=100)
    city: str | None = Field(default=None, max_length=100)

    latitude: float = Field(..., ge=-90, le=90)
    longitude: float = Field(..., ge=-180, le=180)

    geofence_radius_meters: int = Field(default=100, ge=20, le=1000)

    hr_name: str | None = Field(default=None, max_length=150)
    hr_mobile: str | None = Field(default=None, max_length=20)
    hr_email: EmailStr | None = None

    supervisor_name: str | None = Field(default=None, max_length=150)
    supervisor_mobile: str | None = Field(default=None, max_length=20)
    supervisor_email: EmailStr | None = None


class IndustryUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=200)
    address: str | None = None
    district: str | None = Field(default=None, max_length=100)
    city: str | None = Field(default=None, max_length=100)

    latitude: float | None = Field(default=None, ge=-90, le=90)
    longitude: float | None = Field(default=None, ge=-180, le=180)

    geofence_radius_meters: int | None = Field(default=None, ge=20, le=1000)

    hr_name: str | None = Field(default=None, max_length=150)
    hr_mobile: str | None = Field(default=None, max_length=20)
    hr_email: EmailStr | None = None

    supervisor_name: str | None = Field(default=None, max_length=150)
    supervisor_mobile: str | None = Field(default=None, max_length=20)
    supervisor_email: EmailStr | None = None

    is_active: bool | None = None


class IndustryResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    industry_code: str
    name: str

    address: str | None = None
    district: str | None = None
    city: str | None = None

    latitude: float
    longitude: float
    geofence_radius_meters: int

    hr_name: str | None = None
    hr_mobile: str | None = None
    hr_email: str | None = None

    supervisor_name: str | None = None
    supervisor_mobile: str | None = None
    supervisor_email: str | None = None

    is_active: bool
    created_at: datetime


# -----------------------------
# Training Rosters
# -----------------------------

class TrainingRosterCreate(BaseModel):
    student_id: int
    industry_id: int

    start_date: date
    end_date: date

    shift_start_time: str = Field(..., description="HH:MM format")
    shift_end_time: str = Field(..., description="HH:MM format")

    supervisor_user_id: int | None = None
    hr_user_id: int | None = None
    is_active: bool = True


class TrainingRosterUpdate(BaseModel):
    industry_id: int | None = None

    start_date: date | None = None
    end_date: date | None = None

    shift_start_time: str | None = None
    shift_end_time: str | None = None

    supervisor_user_id: int | None = None
    hr_user_id: int | None = None

    is_active: bool | None = None


class TrainingRosterResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    student_id: int
    industry_id: int

    start_date: date
    end_date: date

    shift_start_time: str
    shift_end_time: str

    supervisor_user_id: int | None = None
    hr_user_id: int | None = None

    is_active: bool
    created_at: datetime


# -----------------------------
# Attendance
# -----------------------------

class AttendanceCheckInRequest(BaseModel):
    student_id: int

    latitude: float = Field(..., ge=-90, le=90)
    longitude: float = Field(..., ge=-180, le=180)
    gps_accuracy_meters: float | None = Field(default=None, ge=0)

    device_id: str | None = Field(default=None, max_length=255)
    browser_info: str | None = None

    # Current POC:
    # These are manually supplied by frontend.
    # Later, these will come from the real face verification model.
    face_match_score: float | None = Field(default=None, ge=0, le=1)
    liveness_score: float | None = Field(default=None, ge=0, le=1)

    # Captured selfie from browser canvas as base64 JPEG data URL.
    # Example:
    # data:image/jpeg;base64,/9j/4AAQSkZJRgABAQ...
    selfie_image_base64: str | None = None
    selfie_captured: bool = False


class AttendanceCheckOutRequest(AttendanceCheckInRequest):
    check_out_notes: str | None = None


class AttendanceEventResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    student_id: int
    industry_id: int
    roster_id: int | None = None

    event_type: str
    status: str
    event_time: datetime

    latitude: float
    longitude: float
    gps_accuracy_meters: float | None = None
    distance_from_industry_meters: float | None = None

    face_match_score: float | None = None
    liveness_score: float | None = None

    device_id: str | None = None
    decision_reason: str | None = None

    created_at: datetime


# -----------------------------
# Anomalies
# -----------------------------

class AnomalyFlagResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    attendance_event_id: int | None = None
    student_id: int

    anomaly_type: str
    severity: str
    risk_score: float
    explanation: str

    review_status: str
    reviewed_by_user_id: int | None = None
    reviewed_at: datetime | None = None
    review_notes: str | None = None

    created_at: datetime


class AnomalyReviewRequest(BaseModel):
    review_status: str = Field(..., description="approved, rejected, escalated")
    review_notes: str | None = None
    reviewed_by_user_id: int | None = None


# -----------------------------
# Dashboard
# -----------------------------

class DashboardSummaryResponse(BaseModel):
    total_students: int
    total_industries: int
    present_today: int
    late_today: int
    absent_today: int
    anomalies_today: int
    pending_reviews: int


class AttendanceAnalyticsResponse(BaseModel):
    date: str
    total_students: int
    present_count: int
    late_count: int
    absent_count: int
    anomaly_count: int
    attendance_percentage: float


# -----------------------------
# Generic DB test schema
# -----------------------------

class DatabaseStatusResponse(BaseModel):
    database_connected: bool
    database: str
    user: str
    postgres_version: str
    postgis_enabled: bool


class PilotImportRequest(BaseModel):
    admissions_path: str
    ojt_path: str
    placements_path: str | None = None


if __name__ == "__main__":
    sample_student = StudentCreate(
        student_code="ITI-VSP-001",
        full_name="Ravi Kumar",
        iti_name="Govt ITI Visakhapatnam",
        trade="Electrician",
        batch="2026",
        mobile="9876543210",
        consent_status=True,
    )

    sample_industry = IndustryCreate(
        industry_code="IND-VSP-001",
        name="Vizag Steel Partner Workshop",
        district="Visakhapatnam",
        city="Visakhapatnam",
        latitude=17.6868,
        longitude=83.2185,
        geofence_radius_meters=100,
    )

    sample_attendance = AttendanceCheckInRequest(
        student_id=1,
        latitude=17.6869,
        longitude=83.2186,
        gps_accuracy_meters=20,
        device_id="demo-browser-device",
        face_match_score=0.86,
        liveness_score=0.91,
        selfie_captured=True,
        selfie_image_base64=None,
    )

    print("Schema self-test passed.")
    print(sample_student.model_dump())
    print(sample_industry.model_dump())
    print(sample_attendance.model_dump())
