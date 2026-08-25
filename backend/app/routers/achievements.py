from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from sqlalchemy import or_

from app.auth import get_current_identity, get_current_verifier, verifier_scope_filter, faculty_verifier_scope_filter
from app.database import get_db
from app.models import Achievement, CertificateStatus, Employee, OwnerType, Student, EmployeeRole
from app.schemas import AchievementCreate, AchievementOut, AchievementVerify, ReviewedAchievementOut

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

    now = datetime.now(timezone.utc)
    if verifier.active_role == EmployeeRole.admin.value:
        if record.status != CertificateStatus.verified:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Admin can only act on records that are already verified.",
            )
        record.status = CertificateStatus.approved if payload.approve else CertificateStatus.rejected
        # Tier 2 signs approved_by, NOT verified_by. Writing both here (as this
        # used to) erased the coordinator who did tier 1, which is the one
        # thing a "what have I reviewed?" view needs to survive.
        record.approved_by = verifier.emp_id
        record.approved_at = now
    else:
        if record.status != CertificateStatus.pending:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="This record has already been reviewed.",
            )
        record.status = CertificateStatus.verified if payload.approve else CertificateStatus.rejected
        record.verified_by = verifier.emp_id
        record.verified_at = now
    
    if payload.remarks:
        # Build a new dict rather than mutating the existing one in place.
        # metadata_fields is a plain JSON column with no mutation tracking, so
        # mutating the dict and assigning the *same object* back leaves
        # SQLAlchemy's attribute history unchanged -- the column is dropped from
        # the UPDATE and the remarks are silently lost. That only bit records
        # which already had metadata (patents, publications, internships);
        # records with NULL metadata worked by accident, because `or {}`
        # produced a genuinely new object.
        record.metadata_fields = {**(record.metadata_fields or {}), "remarks": payload.remarks}


    db.commit()
    db.refresh(record)
    return record


@router.get("/reviewed", response_model=list[ReviewedAchievementOut])
def list_reviewed(
    record_status: CertificateStatus | None = Query(default=None, alias="status"),
    verifier: Employee = Depends(get_current_verifier),
    db: Session = Depends(get_db),
):
    """Everything this verifier has personally acted on, newest decision first.

    Deliberately keyed off the signature (`verified_by` for tier 1,
    `approved_by` for tier 2) rather than off the scope filters used by the
    pending queue. Scope answers "what may I review now?" and legitimately
    changes -- a student gets reassigned to another coordinator, a faculty
    member moves department -- whereas history should not rewrite itself when
    that happens. If you signed it, you can still see it.

    A record can appear for two different people at once, which is correct:
    the coordinator who verified it and the admin who then approved it each
    reviewed it.
    """
    signature = (
        Achievement.approved_by == verifier.emp_id
        if verifier.active_role == EmployeeRole.admin.value
        else Achievement.verified_by == verifier.emp_id
    )

    query = (
        db.query(Achievement, Student.name, Employee.name)
        .outerjoin(Student, Achievement.student_id == Student.student_id)
        .outerjoin(Employee, Achievement.employee_id == Employee.emp_id)
        .filter(signature)
    )
    if record_status is not None:
        query = query.filter(Achievement.status == record_status)

    # Order by the acting tier's own timestamp: an admin's list should be
    # ordered by when *they* approved, not by when a coordinator verified.
    decided_at = (
        Achievement.approved_at
        if verifier.active_role == EmployeeRole.admin.value
        else Achievement.verified_at
    )
    rows = query.order_by(decided_at.desc()).all()

    return [
        ReviewedAchievementOut(
            **AchievementOut.model_validate(record).model_dump(),
            owner_name=student_name if record.owner_type == OwnerType.student else employee_name,
        )
        for record, student_name, employee_name in rows
    ]

