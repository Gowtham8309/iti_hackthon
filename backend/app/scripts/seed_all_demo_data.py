"""
Full demo data seed for the GeoFace Verify hackathon demo.

Creates:
  - 6 user accounts  (admin, supervisor, hr, iti_coordinator, district_officer, + faculty/student)
  - 1 demo faculty profile  (Ravi Kumar)
  - 5 demo student profiles (Suresh, Priya, Arjun, Lakshmi, Venkat)
  - 3 industries across AP with real GPS coordinates
  - 6 training rosters  (all students → industries)
  - 84 attendance events across last 14 days (various statuses)
  - 18 anomaly flags   (mix of severities and review statuses)
  - 8 classroom observations (excellent → critical tiers)
"""

from __future__ import annotations

import random
from datetime import date, datetime, timedelta, timezone
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.db.database import SessionLocal
from app.models.database_models import (
    AnomalyFlag,
    AttendanceEvent,
    ClassroomObservation,
    Industry,
    Student,
    TrainingRoster,
    User,
    UserRole,
)
from app.services.auth_service import hash_password

random.seed(42)  # deterministic demo data

# ─── Credentials ──────────────────────────────────────────────────────────────

USERS = [
    dict(username="admin",            full_name="System Administrator",      role=UserRole.ADMIN.value,            password="admin123",     email="admin@govtiti.ap.gov.in",        mobile="9000000000"),
    dict(username="supervisor",        full_name="Mr. Venkat Supervisor",     role=UserRole.SUPERVISOR.value,       password="super123",     email="supervisor@govtiti.ap.gov.in",   mobile="9000000010"),
    dict(username="hr_user",           full_name="Ms. Radha HR",             role=UserRole.HR.value,               password="hr123",        email="hr@govtiti.ap.gov.in",           mobile="9000000011"),
    dict(username="iti_coord",         full_name="Mr. Prasad Coordinator",   role=UserRole.ITI_COORDINATOR.value,  password="coord123",     email="coord@govtiti.ap.gov.in",        mobile="9000000012"),
    dict(username="district_officer",  full_name="Ms. Sunita District",      role=UserRole.DISTRICT_OFFICER.value, password="district123",  email="district@govtiti.ap.gov.in",     mobile="9000000013"),
]

# ─── Student / Faculty profiles ───────────────────────────────────────────────

FACULTY = dict(
    student_code="FAC-GNT-DEMO-001",
    full_name="Ravi Kumar",
    iti_name="Govt ITI Guntur",
    trade="Electrical Instructor",
    batch="Faculty Batch 2026",
    mobile="9000000001",
    email="ravi.faculty@govtiti.ap.gov.in",
    login_username="FAC-GNT-DEMO-001",
    login_password="faculty123",
    login_role=UserRole.FACULTY.value,
)

STUDENTS = [
    dict(student_code="STU-GNT-DEMO-001", full_name="Suresh Kumar",  iti_name="Govt ITI Guntur",      trade="Electrician",   batch="2026", mobile="9000000002", email="suresh@govtiti.ap.gov.in",  login_username="STU-GNT-DEMO-001", login_password="student123", login_role=UserRole.STUDENT.value),
    dict(student_code="STU-GNT-DEMO-002", full_name="Priya Sharma",  iti_name="Govt ITI Guntur",      trade="Fitter",        batch="2026", mobile="9000000003", email="priya@govtiti.ap.gov.in",   login_username="STU-GNT-DEMO-002", login_password="student123", login_role=UserRole.STUDENT.value),
    dict(student_code="STU-VJA-DEMO-003", full_name="Arjun Reddy",   iti_name="Govt ITI Vijayawada",  trade="Welder",        batch="2026", mobile="9000000004", email="arjun@govtiti.ap.gov.in",   login_username="STU-VJA-DEMO-003", login_password="student123", login_role=UserRole.STUDENT.value),
    dict(student_code="STU-VJA-DEMO-004", full_name="Lakshmi Devi",  iti_name="Govt ITI Vijayawada",  trade="COPA",          batch="2026", mobile="9000000005", email="lakshmi@govtiti.ap.gov.in", login_username="STU-VJA-DEMO-004", login_password="student123", login_role=UserRole.STUDENT.value),
    dict(student_code="STU-CTR-DEMO-005", full_name="Venkat Rao",    iti_name="Govt ITI Chittoor",    trade="Turner",        batch="2026", mobile="9000000006", email="venkat@govtiti.ap.gov.in",  login_username="STU-CTR-DEMO-005", login_password="student123", login_role=UserRole.STUDENT.value),
]

# ─── Industries ───────────────────────────────────────────────────────────────

INDUSTRIES = [
    dict(
        industry_code="ITI-GNT-LAB-001",
        name="Govt ITI Guntur — Electrical Lab",
        address="Govt ITI Campus, Brodipet, Guntur",
        district="Guntur", city="Guntur",
        latitude=16.3067, longitude=80.4365,
        geofence_radius_meters=100,
        hr_name="Principal Guntur", hr_mobile="9000000020", hr_email="principal.gnt@govtiti.ap.gov.in",
        supervisor_name="DTO Guntur",  supervisor_mobile="9000000021", supervisor_email="dto.gnt@ap.gov.in",
    ),
    dict(
        industry_code="APIIC-VJA-WRK-002",
        name="APIIC Industrial Park — Precision Workshop",
        address="APIIC Industrial Area, Auto Nagar, Vijayawada",
        district="Krishna", city="Vijayawada",
        latitude=16.5062, longitude=80.6480,
        geofence_radius_meters=150,
        hr_name="HR Manager APIIC", hr_mobile="9000000022", hr_email="hr.apiic@vijayawada.ap.gov.in",
        supervisor_name="Supervisor VJA", supervisor_mobile="9000000023", supervisor_email="supervisor.vja@ap.gov.in",
    ),
    dict(
        industry_code="SRICITY-MFG-003",
        name="Sricity Manufacturing Zone — CNC Unit",
        address="Sricity, Tada, SPSR Nellore District",
        district="SPSR Nellore", city="Tada",
        latitude=13.6288, longitude=79.5472,
        geofence_radius_meters=200,
        hr_name="HR Sricity", hr_mobile="9000000024", hr_email="hr@sricity.in",
        supervisor_name="Supervisor Sricity", supervisor_mobile="9000000025", supervisor_email="supervisor@sricity.in",
    ),
]

# ─── Helpers ──────────────────────────────────────────────────────────────────

def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def days_ago(n: int, hour: int = 9, minute: int = 0) -> datetime:
    d = date.today() - timedelta(days=n)
    return datetime(d.year, d.month, d.day, hour, minute, tzinfo=timezone.utc)


def _upsert_user(db: Session, *, username: str, full_name: str, role: str,
                 password: str, email: str | None, mobile: str | None) -> User:
    user = db.execute(select(User).where(User.username == username)).scalar_one_or_none()
    if user is None:
        # clear email/mobile conflicts
        if email:
            db.execute(select(User).where(User.email == email))
            conflict = db.execute(select(User).where(User.email == email)).scalar_one_or_none()
            if conflict:
                conflict.email = None
        if mobile:
            conflict = db.execute(select(User).where(User.mobile == mobile)).scalar_one_or_none()
            if conflict:
                conflict.mobile = None
        user = User(username=username, full_name=full_name, role=role,
                    hashed_password=hash_password(password), email=email, mobile=mobile, is_active=True)
        db.add(user)
    else:
        user.full_name = full_name
        user.role = role
        user.hashed_password = hash_password(password)
        user.is_active = True
    db.flush()
    return user


def _upsert_student(db: Session, **kwargs) -> Student:
    code = kwargs.pop("student_code")
    login_username = kwargs.pop("login_username", None)
    login_password = kwargs.pop("login_password", None)
    login_role = kwargs.pop("login_role", UserRole.STUDENT.value)

    s = db.execute(select(Student).where(Student.student_code == code)).scalar_one_or_none()
    if s is None:
        s = Student(student_code=code, consent_status=True, face_enrolled=False,
                    face_embedding=None, is_active=True, **kwargs)
        db.add(s)
    else:
        for k, v in kwargs.items():
            setattr(s, k, v)
        s.consent_status = True
        s.is_active = True
    db.flush()

    if login_username:
        _upsert_user(db, username=login_username, full_name=kwargs["full_name"],
                     role=login_role, password=login_password,
                     email=kwargs.get("email"), mobile=kwargs.get("mobile"))
    return s


def _upsert_industry(db: Session, **kwargs) -> Industry:
    code = kwargs.pop("industry_code")
    ind = db.execute(select(Industry).where(Industry.industry_code == code)).scalar_one_or_none()
    if ind is None:
        ind = Industry(industry_code=code, is_active=True, **kwargs)
        db.add(ind)
    else:
        for k, v in kwargs.items():
            setattr(ind, k, v)
    db.flush()
    return ind


def _upsert_roster(db: Session, student_id: int, industry_id: int,
                   start_time: str = "09:00", end_time: str = "17:00") -> TrainingRoster:
    existing = db.execute(
        select(TrainingRoster)
        .where(TrainingRoster.student_id == student_id)
        .where(TrainingRoster.industry_id == industry_id)
    ).scalar_one_or_none()
    if existing:
        existing.is_active = True
        existing.shift_start_time = start_time
        existing.shift_end_time = end_time
        db.flush()
        return existing
    r = TrainingRoster(
        student_id=student_id,
        industry_id=industry_id,
        start_date=date(2026, 1, 1),
        end_date=date(2026, 12, 31),
        shift_start_time=start_time,
        shift_end_time=end_time,
        is_active=True,
    )
    db.add(r)
    db.flush()
    return r


# ─── Attendance event factory ─────────────────────────────────────────────────

ATTENDANCE_PATTERNS = [
    # (status, face_match_score, inside_fence, minutes_late)
    ("present",           0.92, True,  0),
    ("present",           0.88, True,  0),
    ("present",           0.95, True,  0),
    ("present",           0.90, True,  0),
    ("present",           0.86, True,  0),
    ("late",              0.89, True,  22),
    ("late",              0.84, True,  45),
    ("needs_review",      0.71, True,  0),
    ("outside_geofence",  0.91, False, 0),
    ("face_mismatch",     0.48, True,  0),
]


def _make_event(db: Session, student_id: int, industry_id: int, roster_id: int | None,
                ind_lat: float, ind_lon: float, days_back: int, pattern_idx: int) -> AttendanceEvent:
    status, face_score, inside, late_mins = ATTENDANCE_PATTERNS[pattern_idx % len(ATTENDANCE_PATTERNS)]

    hour = 9 + (late_mins // 60)
    minute = late_mins % 60

    if inside:
        lat = ind_lat + random.uniform(-0.0003, 0.0003)
        lon = ind_lon + random.uniform(-0.0003, 0.0003)
        dist = random.uniform(5, 80)
    else:
        lat = ind_lat + random.uniform(0.02, 0.05)
        lon = ind_lon + random.uniform(0.02, 0.05)
        dist = random.uniform(350, 900)

    ev = AttendanceEvent(
        student_id=student_id,
        industry_id=industry_id,
        roster_id=roster_id,
        event_type="check_in",
        status=status,
        event_time=days_ago(days_back, hour=hour, minute=minute),
        latitude=lat,
        longitude=lon,
        gps_accuracy_meters=random.uniform(5, 30),
        distance_from_industry_meters=dist,
        face_match_score=face_score,
        liveness_score=random.uniform(0.75, 0.98),
        device_id=f"device-demo-{student_id}",
        browser_info="Chrome/124 Demo",
        ip_address="127.0.0.1",
        decision_reason=f"Demo: {status} — face={face_score:.2f} dist={dist:.0f}m",
    )
    db.add(ev)
    db.flush()
    return ev


# ─── Anomaly factory ─────────────────────────────────────────────────────────

ANOMALY_TEMPLATES = [
    ("outside_geofence",     "high",     0.85, "Student checked in from 420m outside the assigned industry geofence. GPS coordinates do not match registered location."),
    ("face_mismatch",        "critical", 0.95, "Face similarity score 0.48 is below the 0.60 review threshold. Possible identity fraud or enrollment issue."),
    ("repeated_late_arrival","medium",   0.60, "Student has arrived late 3 times in the past 7 days. Pattern suggests scheduling or transport issue."),
    ("outside_geofence",     "high",     0.80, "Check-in location is 520m from the registered industry. Repeated geofence violation detected."),
    ("consecutive_absence",  "critical", 0.90, "Student has been absent for 3 consecutive working days without prior notice or leave approval."),
    ("face_mismatch",        "high",     0.75, "Face match score 0.52 — below acceptance threshold. Manual review of identity required."),
    ("suspicious_pattern",   "medium",   0.55, "Check-in time pattern shows systematic late arrivals exactly 15 minutes after shift start. Possible clock-in gaming."),
    ("outside_geofence",     "medium",   0.50, "GPS reading shows student 280m from industry boundary. May be WiFi-based location inaccuracy."),
    ("repeated_late_arrival","low",      0.35, "First late arrival recorded this week. Monitor for pattern development."),
    ("face_mismatch",        "medium",   0.65, "Face score 0.62 is between review (0.60) and accept (0.75) thresholds. Borderline case for supervisor review."),
]


def _make_anomaly(db: Session, student_id: int, event_id: int | None, idx: int,
                  review_status: str = "pending") -> AnomalyFlag:
    atype, severity, risk, explanation = ANOMALY_TEMPLATES[idx % len(ANOMALY_TEMPLATES)]
    af = AnomalyFlag(
        attendance_event_id=event_id,
        student_id=student_id,
        anomaly_type=atype,
        severity=severity,
        risk_score=risk,
        explanation=explanation,
        review_status=review_status,
        created_at=utc_now() - timedelta(days=random.randint(0, 10)),
    )
    db.add(af)
    db.flush()
    return af


# ─── Classroom observation factory ───────────────────────────────────────────

OBSERVATION_TEMPLATES = [
    # (session_status, discipline, teaching, engagement, notes)
    ("on_track",       88, 90, 85, "Excellent lesson today. Students actively participated. Practical demos were clear and well-structured."),
    ("on_track",       82, 78, 80, "Good session overall. Teaching pace was appropriate. A few students needed additional explanations."),
    ("late_start",     70, 75, 68, "Faculty arrived 12 minutes late. Lesson content was adequate but shortened due to late start."),
    ("on_track",       85, 88, 90, "Outstanding engagement. Students showed strong understanding of electrical safety standards."),
    ("low_engagement", 75, 70, 45, "Students appeared disengaged in second half. Teaching was mostly chalk-and-talk with no practical component."),
    ("needs_review",   55, 58, 42, "Concerning session. Faculty struggled with content. Several students were on phones. Discipline issues noted."),
    ("absent_faculty", 0,  0,  0,  "Faculty was absent for the session. Students were unsupervised for 40 minutes until substitute arrived."),
    ("late_start",     60, 65, 55, "Faculty started 25 minutes late. Lesson was rushed. Engagement was below average throughout."),
]


def _make_observation(db: Session, faculty_id: int, industry_id: int,
                      observer_user_id: int, days_back: int, idx: int) -> ClassroomObservation:
    s_status, disc, teach, eng, notes = OBSERVATION_TEMPLATES[idx % len(OBSERVATION_TEMPLATES)]
    composite = teach * 0.40 + disc * 0.35 + eng * 0.25
    tier = ("excellent" if composite >= 80 else "satisfactory" if composite >= 65
            else "needs_improvement" if composite >= 50 else "critical")
    signals_items = []
    if disc < 60:   signals_items.append("Discipline score below threshold (60)")
    if teach < 60:  signals_items.append("Teaching quality below threshold (60)")
    if eng < 60:    signals_items.append("Engagement score below threshold (60)")
    if s_status == "absent_faculty": signals_items.append("Faculty absent — session compromised")

    ob = ClassroomObservation(
        faculty_id=faculty_id,
        industry_id=industry_id,
        observer_user_id=observer_user_id,
        observed_at=days_ago(days_back, hour=10 + (idx % 4), minute=random.randint(0, 59)),
        session_status=s_status,
        discipline_score=float(disc),
        teaching_quality_score=float(teach),
        student_engagement_score=float(eng),
        notes=notes,
        anomaly_signals={
            "composite_score": round(composite, 2),
            "performance_tier": tier,
            "needs_attention": len(signals_items) > 0,
            "items": signals_items,
        },
    )
    db.add(ob)
    db.flush()
    return ob


# ─── Main seed function ───────────────────────────────────────────────────────

def seed_all_demo_data() -> dict:
    db = SessionLocal()
    try:
        # 1 ─ Clear transactional data (keep users + master data structure)
        db.execute(delete(ClassroomObservation))
        db.execute(delete(AnomalyFlag))
        db.execute(delete(AttendanceEvent))
        db.execute(delete(TrainingRoster))
        db.flush()

        # 2 ─ Upsert users
        created_users = []
        for u in USERS:
            user = _upsert_user(db, **u)
            created_users.append(user.username)

        admin_user = db.execute(select(User).where(User.username == "admin")).scalar_one()

        # 3 ─ Upsert faculty + student profiles + their login users
        fac_data = {k: v for k, v in FACULTY.items()}
        faculty = _upsert_student(db, **fac_data)

        student_objs = []
        for sd in STUDENTS:
            stu = _upsert_student(db, **sd)
            student_objs.append(stu)

        # 4 ─ Upsert industries
        industry_objs = []
        for ind_data in INDUSTRIES:
            ind = _upsert_industry(db, **ind_data)
            industry_objs.append(ind)

        ind0, ind1, ind2 = industry_objs  # Guntur, Vijayawada, Sricity

        # 5 ─ Create rosters
        #   Faculty → Industry 0
        fac_roster = _upsert_roster(db, faculty.id, ind0.id, "09:00", "17:00")
        #   Students 0,1 → Industry 0 (Guntur)
        r0 = _upsert_roster(db, student_objs[0].id, ind0.id, "09:00", "17:00")
        r1 = _upsert_roster(db, student_objs[1].id, ind0.id, "09:00", "17:00")
        #   Students 2,3 → Industry 1 (Vijayawada)
        r2 = _upsert_roster(db, student_objs[2].id, ind1.id, "08:30", "16:30")
        r3 = _upsert_roster(db, student_objs[3].id, ind1.id, "08:30", "16:30")
        #   Student 4 → Industry 2 (Sricity)
        r4 = _upsert_roster(db, student_objs[4].id, ind2.id, "07:00", "15:00")

        roster_map = {
            student_objs[0].id: (r0, ind0),
            student_objs[1].id: (r1, ind0),
            student_objs[2].id: (r2, ind1),
            student_objs[3].id: (r3, ind1),
            student_objs[4].id: (r4, ind2),
        }

        # 6 ─ Attendance events — 14 days, all 5 students
        #   Pattern index cycles across different statuses per student per day
        created_events: list[AttendanceEvent] = []
        anomaly_events: list[AttendanceEvent] = []

        for day_back in range(1, 15):          # 1..14 days ago
            for s_idx, stu in enumerate(student_objs):
                roster, ind = roster_map[stu.id]
                # pattern index: mix by student and day to get realistic distribution
                pattern_idx = (s_idx * 3 + day_back) % len(ATTENDANCE_PATTERNS)
                ev = _make_event(
                    db, stu.id, ind.id, roster.id,
                    ind.latitude, ind.longitude,
                    day_back, pattern_idx,
                )
                created_events.append(ev)
                if ev.status in ("outside_geofence", "face_mismatch", "needs_review"):
                    anomaly_events.append(ev)

        # 7 ─ Anomaly flags (link to problematic events + a few standalone)
        created_anomalies = []
        for a_idx, ev in enumerate(anomaly_events[:10]):
            review = "pending" if a_idx < 6 else ("approved" if a_idx == 6 else "escalated")
            af = _make_anomaly(db, ev.student_id, ev.id, a_idx, review)
            created_anomalies.append(af)

        # Extra standalone anomalies (no event link)
        for extra_idx in range(8):
            stu = student_objs[extra_idx % len(student_objs)]
            af = _make_anomaly(db, stu.id, None, extra_idx + 4,
                               "pending" if extra_idx < 5 else "rejected")
            created_anomalies.append(af)

        # 8 ─ Classroom observations (8 records, last 8 days)
        created_observations = []
        for obs_idx in range(8):
            ob = _make_observation(
                db,
                faculty_id=faculty.id,
                industry_id=ind0.id,
                observer_user_id=admin_user.id,
                days_back=obs_idx,
                idx=obs_idx,
            )
            created_observations.append(ob)

        db.commit()

        return {
            "seed_status": "success",
            "created": {
                "users": len(USERS),
                "faculty": 1,
                "students": len(STUDENTS),
                "industries": len(INDUSTRIES),
                "rosters": 6,
                "attendance_events": len(created_events),
                "anomaly_flags": len(created_anomalies),
                "classroom_observations": len(created_observations),
            },
            "login_credentials": {
                "admin":            {"username": "admin",           "password": "admin123"},
                "supervisor":       {"username": "supervisor",      "password": "super123"},
                "hr":               {"username": "hr_user",         "password": "hr123"},
                "iti_coordinator":  {"username": "iti_coord",       "password": "coord123"},
                "district_officer": {"username": "district_officer","password": "district123"},
                "faculty":          {"username": "FAC-GNT-DEMO-001","password": "faculty123"},
                "student":          {"username": "STU-GNT-DEMO-001","password": "student123"},
            },
            "demo_industry_id": ind0.id,
            "demo_faculty_id": faculty.id,
            "demo_student_ids": [s.id for s in student_objs],
            "demo_gps": {
                "inside_geofence":  {"lat": 16.3067, "lon": 80.4365, "location": "Govt ITI Guntur"},
                "outside_geofence": {"lat": 17.3850, "lon": 78.4867, "location": "Hyderabad (triggers anomaly)"},
            },
        }

    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
