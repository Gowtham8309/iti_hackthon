"""
ML-based anomaly detection service.

Two layers:
1. Instant rule checks run during every check-in (same-device proxy, rapid
   duplicate IP, impossible-travel velocity).
2. Isolation Forest trained on historical attendance features; scores each
   new event as an outlier probability.  Model is persisted to disk and
   retrained automatically once enough new events accumulate.
"""
from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import joblib
import numpy as np
from sqlalchemy import select
from sqlalchemy.orm import Session
from sklearn.ensemble import IsolationForest
from sklearn.preprocessing import StandardScaler

from app.core.config import settings
from app.models.database_models import AttendanceEvent, AnomalyFlag, AnomalySeverity


# ---------------------------------------------------------------------------
# Feature extraction
# ---------------------------------------------------------------------------

def _event_features(event: AttendanceEvent) -> list[float]:
    """
    Converts one attendance event into a fixed-length numeric feature vector.

    Features:
    0  face_match_score     (0–1, 0 when missing)
    1  liveness_score       (0–1, 0 when missing)
    2  gps_accuracy_meters  (0–200, clamped)
    3  distance_from_industry_meters (0–5000, clamped)
    4  hour_of_day          (0–23)
    5  day_of_week          (0–6)
    6  event_type_encoded   (0=check_in, 1=check_out)
    """
    t: datetime = event.event_time
    if t.tzinfo is None:
        t = t.replace(tzinfo=timezone.utc)

    return [
        float(event.face_match_score or 0.0),
        float(event.liveness_score or 0.0),
        min(float(event.gps_accuracy_meters or 0.0), 200.0),
        min(float(event.distance_from_industry_meters or 0.0), 5000.0),
        float(t.hour),
        float(t.weekday()),
        0.0 if str(event.event_type) == "check_in" else 1.0,
    ]


# ---------------------------------------------------------------------------
# Model persistence
# ---------------------------------------------------------------------------

def _model_path() -> Path:
    path = Path(settings.ML_ANOMALY_MODEL_PATH)
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def _save_model(model: IsolationForest, scaler: StandardScaler) -> None:
    joblib.dump({"model": model, "scaler": scaler}, _model_path())


def _load_model() -> tuple[IsolationForest, StandardScaler] | None:
    p = _model_path()
    if not p.exists():
        return None
    try:
        bundle = joblib.load(p)
        return bundle["model"], bundle["scaler"]
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Training
# ---------------------------------------------------------------------------

def train_isolation_forest(db: Session) -> dict[str, Any]:
    """
    Trains (or retrains) the Isolation Forest on all historical attendance events.
    Requires at least 20 events.
    """
    events = db.execute(select(AttendanceEvent)).scalars().all()

    if len(events) < 20:
        return {
            "trained": False,
            "reason": f"Not enough events to train ({len(events)} < 20).",
        }

    X = np.array([_event_features(e) for e in events], dtype=np.float32)

    scaler = StandardScaler()
    X_scaled = scaler.fit_transform(X)

    model = IsolationForest(
        n_estimators=200,
        contamination=0.05,
        random_state=42,
        n_jobs=-1,
    )
    model.fit(X_scaled)
    _save_model(model, scaler)

    return {
        "trained": True,
        "events_used": len(events),
        "model_path": str(_model_path()),
    }


def maybe_retrain(db: Session) -> None:
    """
    Retrains the model if enough new events have accumulated since last train.
    Called lazily after every check-in.
    """
    p = _model_path()
    if not p.exists():
        train_isolation_forest(db)
        return

    total_events = db.execute(
        select(AttendanceEvent)
    ).scalars().all()

    model_mtime = datetime.fromtimestamp(p.stat().st_mtime, tz=timezone.utc)
    recent_events = [
        e for e in total_events
        if e.created_at and e.created_at > model_mtime
    ]

    if len(recent_events) >= settings.ML_ANOMALY_RETRAIN_AFTER_EVENTS:
        train_isolation_forest(db)


# ---------------------------------------------------------------------------
# Scoring a single new event
# ---------------------------------------------------------------------------

def score_event_with_isolation_forest(
    db: Session,
    event: AttendanceEvent,
) -> dict[str, Any]:
    """
    Returns an anomaly score for one event using the trained Isolation Forest.

    isolation_forest_score: raw score from the model (-1 or +1 for predict,
        continuous for decision_function; we convert to a 0–1 risk probability).
    is_outlier: True when the model classifies the event as anomalous.
    """
    bundle = _load_model()
    if bundle is None:
        return {
            "isolation_forest_available": False,
            "reason": "Model not trained yet.",
        }

    model, scaler = bundle
    features = np.array([_event_features(event)], dtype=np.float32)
    features_scaled = scaler.transform(features)

    raw_score = float(model.decision_function(features_scaled)[0])
    prediction = int(model.predict(features_scaled)[0])  # -1=outlier, 1=normal

    # Normalise decision_function score to 0–1 risk (higher = more anomalous)
    risk_probability = round(max(0.0, min(1.0, 0.5 - raw_score * 0.5)), 4)

    return {
        "isolation_forest_available": True,
        "is_outlier": prediction == -1,
        "raw_score": round(raw_score, 6),
        "risk_probability": risk_probability,
    }


# ---------------------------------------------------------------------------
# Instant proxy / abuse checks (run during check-in, before DB write)
# ---------------------------------------------------------------------------

def check_same_device_proxy(
    db: Session,
    *,
    student_id: int,
    device_id: str | None,
    event_time: datetime,
) -> dict[str, Any] | None:
    """
    Returns an anomaly candidate dict if the same device_id was used
    by a DIFFERENT student on the same calendar day.

    Returns None when clean.
    """
    if not device_id:
        return None

    day_start = datetime.combine(event_time.date(), datetime.min.time(), tzinfo=timezone.utc)
    day_end = datetime.combine(event_time.date(), datetime.max.time(), tzinfo=timezone.utc)

    stmt = (
        select(AttendanceEvent)
        .where(AttendanceEvent.device_id == device_id)
        .where(AttendanceEvent.student_id != student_id)
        .where(AttendanceEvent.event_time >= day_start)
        .where(AttendanceEvent.event_time <= day_end)
    )
    conflict = db.execute(stmt).scalars().first()

    if conflict:
        return {
            "anomaly_type": "proxy_attendance_device_sharing",
            "severity": AnomalySeverity.CRITICAL.value,
            "risk_score": 95.0,
            "explanation": (
                f"Device ID '{device_id}' was used by another student "
                f"(student_id={conflict.student_id}) on the same day. "
                "Possible proxy attendance via shared device."
            ),
        }
    return None


def check_same_ip_proxy(
    db: Session,
    *,
    student_id: int,
    ip_address: str | None,
    event_time: datetime,
) -> dict[str, Any] | None:
    """
    Returns an anomaly candidate if the same IP produced check-ins for
    3 or more different students within 10 minutes (coordinated proxy check-in).
    """
    if not ip_address:
        return None

    window_start = event_time - timedelta(minutes=10)

    stmt = (
        select(AttendanceEvent)
        .where(AttendanceEvent.ip_address == ip_address)
        .where(AttendanceEvent.student_id != student_id)
        .where(AttendanceEvent.event_time >= window_start)
        .where(AttendanceEvent.event_time <= event_time)
    )
    recent = db.execute(stmt).scalars().all()

    unique_students = {e.student_id for e in recent}
    if len(unique_students) >= 2:
        return {
            "anomaly_type": "proxy_attendance_ip_cluster",
            "severity": AnomalySeverity.HIGH.value,
            "risk_score": 88.0,
            "explanation": (
                f"IP address '{ip_address}' produced check-ins for "
                f"{len(unique_students) + 1} different students within 10 minutes. "
                "Possible coordinated proxy attendance."
            ),
        }
    return None


def check_impossible_travel(
    db: Session,
    *,
    student_id: int,
    industry_id: int,
    event_time: datetime,
) -> dict[str, Any] | None:
    """
    Flags if the student has a check-in at a DIFFERENT industry
    within the last 2 hours (physically impossible travel).
    """
    window_start = event_time - timedelta(hours=2)

    stmt = (
        select(AttendanceEvent)
        .where(AttendanceEvent.student_id == student_id)
        .where(AttendanceEvent.industry_id != industry_id)
        .where(AttendanceEvent.event_time >= window_start)
        .where(AttendanceEvent.event_time <= event_time)
        .order_by(AttendanceEvent.event_time.desc())
    )
    recent = db.execute(stmt).scalars().first()

    if recent:
        minutes_apart = abs((event_time - recent.event_time).total_seconds()) / 60
        return {
            "anomaly_type": "impossible_travel",
            "severity": AnomalySeverity.CRITICAL.value,
            "risk_score": 92.0,
            "explanation": (
                f"Student checked in at industry {industry_id} but had a recent "
                f"event at industry {recent.industry_id} only "
                f"{round(minutes_apart, 1)} minutes earlier. "
                "Physically impossible travel detected."
            ),
        }
    return None


# ---------------------------------------------------------------------------
# High-level entry point used by attendance_service
# ---------------------------------------------------------------------------

def run_ml_checks(
    db: Session,
    *,
    student_id: int,
    industry_id: int,
    device_id: str | None,
    ip_address: str | None,
    event_time: datetime,
) -> list[dict[str, Any]]:
    """
    Runs all instant ML/proxy checks and returns a list of anomaly candidates.
    Empty list means clean.
    """
    candidates: list[dict[str, Any]] = []

    proxy_device = check_same_device_proxy(
        db, student_id=student_id, device_id=device_id, event_time=event_time
    )
    if proxy_device:
        candidates.append(proxy_device)

    proxy_ip = check_same_ip_proxy(
        db, student_id=student_id, ip_address=ip_address, event_time=event_time
    )
    if proxy_ip:
        candidates.append(proxy_ip)

    travel = check_impossible_travel(
        db, student_id=student_id, industry_id=industry_id, event_time=event_time
    )
    if travel:
        candidates.append(travel)

    return candidates
