from dataclasses import dataclass
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.database import SessionLocal
from app.models.database_models import Industry
from app.services.crud_service import get_industry_by_code, get_industry_by_id


@dataclass
class GeoValidationResult:
    is_valid_location: bool
    is_gps_accuracy_valid: bool
    is_inside_geofence: bool
    distance_from_industry_meters: float
    allowed_radius_meters: int
    gps_accuracy_meters: float | None
    max_allowed_gps_accuracy_meters: int
    status: str
    reason: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "is_valid_location": self.is_valid_location,
            "is_gps_accuracy_valid": self.is_gps_accuracy_valid,
            "is_inside_geofence": self.is_inside_geofence,
            "distance_from_industry_meters": round(self.distance_from_industry_meters, 2),
            "allowed_radius_meters": self.allowed_radius_meters,
            "gps_accuracy_meters": self.gps_accuracy_meters,
            "max_allowed_gps_accuracy_meters": self.max_allowed_gps_accuracy_meters,
            "status": self.status,
            "reason": self.reason,
        }


def calculate_distance_with_postgis(
    db: Session,
    *,
    industry_latitude: float,
    industry_longitude: float,
    student_latitude: float,
    student_longitude: float,
) -> float:
    """
    Uses Neon PostGIS to calculate real earth distance in meters.

    ST_MakePoint(longitude, latitude)
    ST_DistanceSphere(point1, point2) returns distance in meters.
    """
    query = text(
        """
        SELECT ST_DistanceSphere(
            ST_MakePoint(:industry_longitude, :industry_latitude),
            ST_MakePoint(:student_longitude, :student_latitude)
        ) AS distance_meters;
        """
    )

    result = db.execute(
        query,
        {
            "industry_latitude": industry_latitude,
            "industry_longitude": industry_longitude,
            "student_latitude": student_latitude,
            "student_longitude": student_longitude,
        },
    ).scalar()

    return float(result or 0.0)


def validate_geofence(
    db: Session,
    *,
    industry_id: int,
    student_latitude: float,
    student_longitude: float,
    gps_accuracy_meters: float | None = None,
) -> GeoValidationResult:
    """
    Validates whether a student is physically present inside the assigned industry location.

    Rules:
    1. Student must be inside industry geofence radius.
    2. GPS accuracy must be acceptable.
    3. Both must pass for valid attendance location.
    """
    industry: Industry | None = get_industry_by_id(db, industry_id)

    if not industry:
        raise ValueError(f"Industry not found with id: {industry_id}")

    allowed_radius = int(industry.geofence_radius_meters or settings.DEFAULT_GEOFENCE_RADIUS_METERS)
    max_gps_accuracy = int(settings.MAX_ALLOWED_GPS_ACCURACY_METERS)

    distance = calculate_distance_with_postgis(
        db,
        industry_latitude=float(industry.latitude),
        industry_longitude=float(industry.longitude),
        student_latitude=float(student_latitude),
        student_longitude=float(student_longitude),
    )

    is_inside_geofence = distance <= allowed_radius

    if gps_accuracy_meters is None:
        is_gps_accuracy_valid = True
    else:
        is_gps_accuracy_valid = float(gps_accuracy_meters) <= max_gps_accuracy

    is_valid_location = is_inside_geofence and is_gps_accuracy_valid

    if is_valid_location:
        status = "valid_location"
        reason = (
            f"Student is within {round(distance, 2)} meters of industry site "
            f"and GPS accuracy is acceptable."
        )
    elif not is_inside_geofence and not is_gps_accuracy_valid:
        status = "invalid_location_and_poor_gps"
        reason = (
            f"Student is outside geofence: {round(distance, 2)} meters away. "
            f"GPS accuracy is also poor: {gps_accuracy_meters} meters."
        )
    elif not is_inside_geofence:
        status = "outside_geofence"
        reason = (
            f"Student is outside allowed geofence. Distance is {round(distance, 2)} meters, "
            f"allowed radius is {allowed_radius} meters."
        )
    else:
        status = "poor_gps_accuracy"
        reason = (
            f"GPS accuracy is poor: {gps_accuracy_meters} meters. "
            f"Maximum allowed GPS accuracy is {max_gps_accuracy} meters."
        )

    return GeoValidationResult(
        is_valid_location=is_valid_location,
        is_gps_accuracy_valid=is_gps_accuracy_valid,
        is_inside_geofence=is_inside_geofence,
        distance_from_industry_meters=distance,
        allowed_radius_meters=allowed_radius,
        gps_accuracy_meters=gps_accuracy_meters,
        max_allowed_gps_accuracy_meters=max_gps_accuracy,
        status=status,
        reason=reason,
    )


def run_geo_self_test() -> dict[str, Any]:
    """
    Real Neon + PostGIS self-test.

    Uses the demo industry created earlier:
    industry_code = IND-VSP-DEMO-001

    Tests:
    1. Same location as industry = should pass.
    2. Far location = should fail.
    """
    db = SessionLocal()

    try:
        industry = get_industry_by_code(db, "IND-VSP-DEMO-001")

        if not industry:
            raise RuntimeError(
                "Demo industry not found. Run: python -m app.services.crud_service first."
            )

        valid_case = validate_geofence(
            db,
            industry_id=industry.id,
            student_latitude=float(industry.latitude),
            student_longitude=float(industry.longitude),
            gps_accuracy_meters=20,
        )

        outside_case = validate_geofence(
            db,
            industry_id=industry.id,
            student_latitude=float(industry.latitude) + 0.01,
            student_longitude=float(industry.longitude) + 0.01,
            gps_accuracy_meters=20,
        )

        poor_gps_case = validate_geofence(
            db,
            industry_id=industry.id,
            student_latitude=float(industry.latitude),
            student_longitude=float(industry.longitude),
            gps_accuracy_meters=120,
        )

        return {
            "geo_self_test": "passed",
            "industry": {
                "id": industry.id,
                "industry_code": industry.industry_code,
                "name": industry.name,
                "latitude": industry.latitude,
                "longitude": industry.longitude,
                "geofence_radius_meters": industry.geofence_radius_meters,
            },
            "valid_case": valid_case.to_dict(),
            "outside_case": outside_case.to_dict(),
            "poor_gps_case": poor_gps_case.to_dict(),
        }

    finally:
        db.close()


if __name__ == "__main__":
    result = run_geo_self_test()
    print(result)