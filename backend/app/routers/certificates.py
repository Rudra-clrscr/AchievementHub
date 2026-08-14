from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.auth import get_current_identity, get_current_verifier, verifier_scope_filter
from app.database import get_db
from app.models import Certificate, CertificateStatus, Employee, EmployeeRole, OwnerType, Student
from app.schemas import CertificateCreate, CertificateOut, CertificateVerify

router = APIRouter(prefix="/certificates", tags=["certificates"])


@router.post("", response_model=CertificateOut, status_code=status.HTTP_201_CREATED)
def submit_certificate(
    payload: CertificateCreate,
    user: Student | Employee = Depends(get_current_identity),
    db: Session = Depends(get_db),
):
    if not payload.file_url.strip():
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="file_url is required")

    if isinstance(user, Student):
        owner_type = OwnerType.student
        student_id = user.student_id
        employee_id = None
        initial_status = CertificateStatus.pending
    else:
        owner_type = OwnerType.employee
        student_id = None
        employee_id = user.emp_id
        if user.role == EmployeeRole.faculty_coordinator:
            initial_status = CertificateStatus.pending_hod
        elif user.role == EmployeeRole.admin_hod:
            initial_status = CertificateStatus.pending_admin
        else:
            initial_status = CertificateStatus.pending

    certificate = Certificate(
        owner_type=owner_type,
        student_id=student_id,
        employee_id=employee_id,
        title=payload.title,
        issuer=payload.issuer,
        category=payload.category,
        file_url=payload.file_url,
        status=initial_status,
    )
    db.add(certificate)
    db.commit()
    db.refresh(certificate)
    return certificate


@router.get("/mine", response_model=list[CertificateOut])
def list_my_certificates(
    user: Student | Employee = Depends(get_current_identity),
    db: Session = Depends(get_db),
):
    if isinstance(user, Student):
        query = db.query(Certificate).filter(Certificate.student_id == user.student_id)
    else:
        query = db.query(Certificate).filter(Certificate.employee_id == user.emp_id)

    return query.order_by(Certificate.submitted_at.desc()).all()


@router.get("/pending", response_model=list[CertificateOut])
def list_pending_certificates(
    verifier: Employee = Depends(get_current_verifier),
    db: Session = Depends(get_db),
):
    query = (
        db.query(Certificate)
        .outerjoin(Student, Certificate.student_id == Student.student_id)
        .outerjoin(Employee, Certificate.employee_id == Employee.emp_id)
        .filter(verifier_scope_filter(verifier, Certificate))
    )

    return query.order_by(Certificate.submitted_at.asc()).all()


@router.patch("/{cert_id}/verify", response_model=CertificateOut)
def verify_certificate(
    cert_id: int,
    payload: CertificateVerify,
    verifier: Employee = Depends(get_current_verifier),
    db: Session = Depends(get_db),
):
    certificate = (
        db.query(Certificate)
        .outerjoin(Student, Certificate.student_id == Student.student_id)
        .outerjoin(Employee, Certificate.employee_id == Employee.emp_id)
        .filter(Certificate.cert_id == cert_id, verifier_scope_filter(verifier, Certificate))
        .first()
    )
    if certificate is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Certificate not found")

    if payload.approve and not certificate.file_url.strip():
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Cannot approve a certificate without a verified file_url",
        )

    if not payload.approve:
        if not payload.remarks or len(payload.remarks.strip()) < 10:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Remarks of at least 10 characters are required when rejecting or requiring revision.",
            )

    if verifier.role == EmployeeRole.faculty_coordinator:
        if payload.approve:
            certificate.status = CertificateStatus.pending_hod
        else:
            certificate.status = CertificateStatus.revision_required
    elif verifier.role == EmployeeRole.admin_hod:
        if payload.approve:
            certificate.status = CertificateStatus.pending_admin
        else:
            certificate.status = CertificateStatus.pending
    else:
        certificate.status = CertificateStatus.approved if payload.approve else CertificateStatus.rejected

    certificate.verified_by = verifier.emp_id
    certificate.verified_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(certificate)
    return certificate
