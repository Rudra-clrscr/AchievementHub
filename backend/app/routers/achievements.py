from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from sqlalchemy import or_

from app.auth import get_current_identity, get_current_verifier, verifier_scope_filter, faculty_verifier_scope_filter
from app.database import get_db
from app.models import Achievement, CertificateStatus, Employee, OwnerType, Student, EmployeeRole
from app.schemas import AchievementCreate, AchievementOut, AchievementVerify

router = APIRouter(prefix="/achievements", tags=["achievements"])

@router.post("", response_model=AchievementOut, status_code=status.HTTP_201_CREATED)
def submit_achievement(
    payload: AchievementCreate,
    identity=Depends(get_current_identity),
    db: Session = Depends(get_db),
):
    if not payload.file_url.strip():
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="file_url is required")

    is_student = isinstance(identity, Student)
    
    record = Achievement(
        **payload.model_dump(),
        owner_type=OwnerType.student if is_student else OwnerType.employee,
        student_id=identity.student_id if is_student else None,
        employee_id=identity.emp_id if not is_student else None,
        status=CertificateStatus.pending,
    )
    db.add(record)
    db.commit()
    db.refresh(record)
    return record


@router.get("/mine", response_model=list[AchievementOut])
def list_mine(
    identity=Depends(get_current_identity),
    db: Session = Depends(get_db),
):
    is_student = isinstance(identity, Student)
    query = db.query(Achievement)
    
    if is_student:
        query = query.filter(Achievement.student_id == identity.student_id)
    else:
        query = query.filter(Achievement.employee_id == identity.emp_id)
        
    return query.order_by(Achievement.submitted_at.desc()).all()


@router.get("/pending", response_model=list[AchievementOut])
def list_pending(
    verifier: Employee = Depends(get_current_verifier),
    db: Session = Depends(get_db),
):
    # Retrieve pending achievements for students (based on verifier scope)
    # and employees (based on faculty verifier scope)

    if verifier.active_role == EmployeeRole.admin.value:
        student_records = (
            db.query(Achievement)
            .join(Student, Achievement.student_id == Student.student_id)
            .filter(
                verifier_scope_filter(verifier),
                Achievement.status == CertificateStatus.verified,
                Achievement.owner_type == OwnerType.student,
            )
        )

        employee_records = (
            db.query(Achievement)
            .join(Employee, Achievement.employee_id == Employee.emp_id)
            .filter(
                faculty_verifier_scope_filter(verifier),
                Achievement.status == CertificateStatus.verified,
                Achievement.owner_type == OwnerType.employee,
            )
        )
    else:
        student_records = (
            db.query(Achievement)
            .join(Student, Achievement.student_id == Student.student_id)
            .filter(
                verifier_scope_filter(verifier),
                Achievement.status == CertificateStatus.pending,
                Achievement.owner_type == OwnerType.student,
            )
        )

        employee_records = (
            db.query(Achievement)
            .join(Employee, Achievement.employee_id == Employee.emp_id)
            .filter(
                faculty_verifier_scope_filter(verifier),
                Achievement.status == CertificateStatus.pending,
                Achievement.owner_type == OwnerType.employee,
            )
        )

    # union_all, not union: owner_type makes the two queries mutually
    # exclusive already (a row can never appear in both), and plain union's
    # deduplication needs an equality operator for every selected column --
    # Achievement.metadata_fields is `json`, which Postgres has none for,
    # so union() throws "could not identify an equality operator for type json".
    return student_records.union_all(employee_records).order_by(Achievement.submitted_at.asc()).all()


@router.patch("/{record_id}/verify", response_model=AchievementOut)
def verify_achievement(
    record_id: int,
    payload: AchievementVerify,
    verifier: Employee = Depends(get_current_verifier),
    db: Session = Depends(get_db),
):
    # Find the record, ensuring the verifier has scope whether it's a student or employee achievement
    record = (
        db.query(Achievement)
        .outerjoin(Student, Achievement.student_id == Student.student_id)
        .outerjoin(Employee, Achievement.employee_id == Employee.emp_id)
        .filter(
            Achievement.id == record_id,
            or_(
                (Achievement.owner_type == OwnerType.student) & verifier_scope_filter(verifier),
                (Achievement.owner_type == OwnerType.employee) & faculty_verifier_scope_filter(verifier)
            )
        )
        .first()
    )
    
    if record is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Record not found or access denied")

    if payload.approve and not record.file_url.strip():
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Cannot approve a record without a verified file_url",
        )

    if verifier.active_role == EmployeeRole.admin.value:
        if record.status != CertificateStatus.verified:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Admin can only act on records that are already verified.",
            )
        record.status = CertificateStatus.approved if payload.approve else CertificateStatus.rejected
    else:
        if record.status != CertificateStatus.pending:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="This record has already been reviewed.",
            )
        record.status = CertificateStatus.verified if payload.approve else CertificateStatus.rejected
    record.verified_by = verifier.emp_id
    record.verified_at = datetime.now(timezone.utc)
    
    if payload.remarks:
        current_meta = record.metadata_fields or {}
        current_meta["remarks"] = payload.remarks
        record.metadata_fields = current_meta
        
    db.commit()
    db.refresh(record)
    return record
