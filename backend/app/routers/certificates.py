from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.auth import get_current_student, get_current_verifier, verifier_scope_filter
from app.database import get_db
from app.models import Certificate, CertificateStatus, Employee, Student
from app.schemas import CertificateCreate, CertificateOut, CertificateVerify

router = APIRouter(prefix="/certificates", tags=["certificates"])


@router.post("", response_model=CertificateOut, status_code=status.HTTP_201_CREATED)
def submit_certificate(
    payload: CertificateCreate,
    student: Student = Depends(get_current_student),
    db: Session = Depends(get_db),
):
    if not payload.file_url.strip():
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="file_url is required")

    certificate = Certificate(
        student_id=student.student_id,
        title=payload.title,
        issuer=payload.issuer,
        category=payload.category,
        file_url=payload.file_url,
        status=CertificateStatus.pending,
    )
    db.add(certificate)
    db.commit()
    db.refresh(certificate)
    return certificate


@router.get("/mine", response_model=list[CertificateOut])
def list_my_certificates(
    student: Student = Depends(get_current_student),
    db: Session = Depends(get_db),
):
    return (
        db.query(Certificate)
        .filter(Certificate.student_id == student.student_id)
        .order_by(Certificate.submitted_at.desc())
        .all()
    )


@router.get("/pending", response_model=list[CertificateOut])
def list_pending_certificates(
    verifier: Employee = Depends(get_current_verifier),
    db: Session = Depends(get_db),
):
    return (
        db.query(Certificate)
        .join(Student, Certificate.student_id == Student.student_id)
        .filter(
            verifier_scope_filter(verifier),
            Certificate.status == CertificateStatus.pending,
        )
        .order_by(Certificate.submitted_at.asc())
        .all()
    )


@router.patch("/{cert_id}/verify", response_model=CertificateOut)
def verify_certificate(
    cert_id: int,
    payload: CertificateVerify,
    verifier: Employee = Depends(get_current_verifier),
    db: Session = Depends(get_db),
):
    certificate = (
        db.query(Certificate)
        .join(Student, Certificate.student_id == Student.student_id)
        .filter(Certificate.cert_id == cert_id, verifier_scope_filter(verifier))
        .first()
    )
    if certificate is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Certificate not found")

    if payload.approve and not certificate.file_url.strip():
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Cannot approve a certificate without a verified file_url",
        )

    certificate.status = CertificateStatus.approved if payload.approve else CertificateStatus.rejected
    certificate.verified_by = verifier.emp_id
    certificate.verified_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(certificate)
    return certificate
