from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.api.dependencies import require_admin, require_supervisor_or_above
from app.db.database import get_db
from app.models.database_models import User
from app.schemas.api_schemas import (
    IndustryCreate,
    IndustryResponse,
    IndustryUpdate,
    StudentCreate,
    StudentResponse,
    StudentUpdate,
    TrainingRosterCreate,
    TrainingRosterResponse,
    TrainingRosterUpdate,
)
from app.services import crud_service
from app.services.faculty_service import list_faculty_profiles


router = APIRouter(
    prefix="/api/v1",
    tags=["Master Data"],
)


# -----------------------------
# Students
# -----------------------------

@router.post("/students", response_model=StudentResponse)
def create_student(
    payload: StudentCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    try:
        return crud_service.create_student(db, payload)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/students", response_model=list[StudentResponse])
def list_students(
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=100, ge=1, le=500),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_supervisor_or_above),
):
    return crud_service.list_students(db, skip=skip, limit=limit)


@router.get("/faculty", response_model=list[StudentResponse])
def list_faculty(
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=100, ge=1, le=500),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_supervisor_or_above),
):
    items = list_faculty_profiles(db)
    return items[skip: skip + limit]


@router.get("/students/{student_id}", response_model=StudentResponse)
def get_student(
    student_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_supervisor_or_above),
):
    student = crud_service.get_student_by_id(db, student_id)

    if not student:
        raise HTTPException(status_code=404, detail="Student not found")

    return student


@router.patch("/students/{student_id}", response_model=StudentResponse)
def update_student(
    student_id: int,
    payload: StudentUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    try:
        return crud_service.update_student(db, student_id, payload)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


# -----------------------------
# Industries
# -----------------------------

@router.post("/industries", response_model=IndustryResponse)
def create_industry(
    payload: IndustryCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    try:
        return crud_service.create_industry(db, payload)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/industries", response_model=list[IndustryResponse])
def list_industries(
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=100, ge=1, le=500),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_supervisor_or_above),
):
    return crud_service.list_industries(db, skip=skip, limit=limit)


@router.get("/industries/{industry_id}", response_model=IndustryResponse)
def get_industry(
    industry_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_supervisor_or_above),
):
    industry = crud_service.get_industry_by_id(db, industry_id)

    if not industry:
        raise HTTPException(status_code=404, detail="Industry not found")

    return industry


@router.patch("/industries/{industry_id}", response_model=IndustryResponse)
def update_industry(
    industry_id: int,
    payload: IndustryUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    try:
        return crud_service.update_industry(db, industry_id, payload)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


# -----------------------------
# Training Rosters
# -----------------------------

@router.post("/rosters", response_model=TrainingRosterResponse)
def create_roster(
    payload: TrainingRosterCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    try:
        return crud_service.create_roster(db, payload)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/rosters", response_model=list[TrainingRosterResponse])
def list_rosters(
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=100, ge=1, le=500),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_supervisor_or_above),
):
    return crud_service.list_rosters(db, skip=skip, limit=limit)


@router.get("/rosters/{roster_id}", response_model=TrainingRosterResponse)
def get_roster(
    roster_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_supervisor_or_above),
):
    roster = crud_service.get_roster_by_id(db, roster_id)

    if not roster:
        raise HTTPException(status_code=404, detail="Roster not found")

    return roster


@router.patch("/rosters/{roster_id}", response_model=TrainingRosterResponse)
def update_roster(
    roster_id: int,
    payload: TrainingRosterUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    try:
        return crud_service.update_roster(db, roster_id, payload)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


# -----------------------------
# API self-test
# -----------------------------

@router.get("/master-data/self-test")
def master_data_self_test(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    students = crud_service.list_students(db, limit=1000)
    industries = crud_service.list_industries(db, limit=1000)
    rosters = crud_service.list_rosters(db, limit=1000)

    return {
        "status": "passed",
        "message": "Master data API can read from Neon database.",
        "counts": {
            "students": len(students),
            "industries": len(industries),
            "rosters": len(rosters),
        },
    }


if __name__ == "__main__":
    result = crud_service.run_crud_self_test()
    print("Master data API module self-test passed.")
    print(result)
