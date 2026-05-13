from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone

from app.db.database import SessionLocal
from app.services.evaluation_service import build_evaluation_report


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate an operational evaluation report for the ITI attendance pilot.")
    parser.add_argument("--date", help="Optional date in YYYY-MM-DD format", default=None)
    parser.add_argument("--pretty", action="store_true", help="Print a human-readable summary before JSON output.")
    args = parser.parse_args()

    target_dt = None
    if args.date:
        target_dt = datetime.strptime(args.date, "%Y-%m-%d").replace(tzinfo=timezone.utc)

    db = SessionLocal()
    try:
        report = build_evaluation_report(db, target_date=target_dt)
    finally:
        db.close()

    if args.pretty:
        summary = report["summary"]
        coverage = report["coverage"]
        quality = report["attendance_quality"]
        print("Evaluation Summary")
        print(f"Date: {report['evaluation_date']}")
        print(f"Students: {summary['total_students']}")
        print(f"Attendance events: {summary['attendance_events']}")
        print(f"Anomaly flags: {summary['anomaly_flags']}")
        print(f"Face enrollment coverage: {coverage['face_enrollment_pct']}%")
        print(f"Consent coverage: {coverage['biometric_consent_pct']}%")
        print(f"Daily states: {quality['daily_state_summary']}")
        print("")

    print(json.dumps(report, indent=2, default=str))


if __name__ == "__main__":
    main()
