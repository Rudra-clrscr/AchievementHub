from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.auth import get_current_identity, get_current_verifier, verifier_scope_filter
from app.database import get_db
from app.models import Achievement, CertificateStatus, Employee, OwnerType, Student
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
    # Only verify student achievements for now
    return (
        db.query(Achievement)
        .join(Student, Achievement.student_id == Student.student_id)
        .filter(
            verifier_scope_filter(verifier),
            Achievement.status == CertificateStatus.pending,
            Achievement.owner_type == OwnerType.student,
        )
        .order_by(Achievement.submitted_at.asc())
        .all()
    )


@router.patch("/{record_id}/verify", response_model=AchievementOut)
def verify_achievement(
    record_id: int,
    payload: AchievementVerify,
    verifier: Employee = Depends(get_current_verifier),
    db: Session = Depends(get_db),
):
    record = (
        db.query(Achievement)
        .outerjoin(Student, Achievement.student_id == Student.student_id)
        .filter(
            Achievement.id == record_id,
            # If it's a student achievement, apply the verifier scope filter.
            # If it's a faculty achievement, we might need a different rule, but for now we'll just check student.
            Achievement.owner_type == OwnerType.student, 
            verifier_scope_filter(verifier)
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

    record.status = CertificateStatus.approved if payload.approve else CertificateStatus.rejected
    record.verified_by = verifier.emp_id
    record.verified_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(record)
    return record
