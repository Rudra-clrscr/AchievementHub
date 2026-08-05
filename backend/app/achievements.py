from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.auth import get_current_student, get_current_verifier, verifier_scope_filter
from app.database import get_db
from app.models import CertificateStatus, Employee, OwnerType, Student
from app.schemas import CertificateVerify


def build_achievement_router(
    *,
    model,
    id_attr: str,
    prefix: str,
    tag: str,
    create_schema: type[BaseModel],
    out_schema: type[BaseModel],
) -> APIRouter:
    """Generates the submit -> pending -> verify endpoints shared by every
    achievement type (Certificates included the pattern first, in
    app/routers/certificates.py). owner_type is always forced to
    OwnerType.student here -- there is no faculty-submitting-their-own-
    achievement verifier defined yet. Verification itself (pending/verify)
    is open to both faculty coordinators and Admin HOD/Clerk, scoped
    differently per verifier_scope_filter."""

    router = APIRouter(prefix=prefix, tags=[tag])
    id_column = getattr(model, id_attr)

    @router.post("", response_model=out_schema, status_code=status.HTTP_201_CREATED)
    def submit(
        payload: create_schema,
        student: Student = Depends(get_current_student),
        db: Session = Depends(get_db),
    ):
        if not payload.file_url.strip():
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="file_url is required")

        record = model(
            **payload.model_dump(),
            owner_type=OwnerType.student,
            student_id=student.student_id,
            status=CertificateStatus.pending,
        )
        db.add(record)
        db.commit()
        db.refresh(record)
        return record

    @router.get("/mine", response_model=list[out_schema])
    def list_mine(
        student: Student = Depends(get_current_student),
        db: Session = Depends(get_db),
    ):
        return (
            db.query(model)
            .filter(model.student_id == student.student_id)
            .order_by(model.submitted_at.desc())
            .all()
        )

    @router.get("/pending", response_model=list[out_schema])
    def list_pending(
        verifier: Employee = Depends(get_current_verifier),
        db: Session = Depends(get_db),
    ):
        return (
            db.query(model)
            .join(Student, model.student_id == Student.student_id)
            .filter(
                verifier_scope_filter(verifier),
                model.status == CertificateStatus.pending,
            )
            .order_by(model.submitted_at.asc())
            .all()
        )

    @router.patch("/{record_id}/verify", response_model=out_schema)
    def verify(
        record_id: int,
        payload: CertificateVerify,
        verifier: Employee = Depends(get_current_verifier),
        db: Session = Depends(get_db),
    ):
        record = (
            db.query(model)
            .join(Student, model.student_id == Student.student_id)
            .filter(id_column == record_id, verifier_scope_filter(verifier))
            .first()
        )
        if record is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Record not found")

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

    return router
