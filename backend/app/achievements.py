from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.auth import get_current_identity, get_current_verifier, verifier_scope_filter
from app.database import get_db
from app.models import CertificateStatus, Employee, EmployeeRole, OwnerType, Student
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
    achievement type. Supports both Student and Employee (Faculty / HOD) submitters."""

    router = APIRouter(prefix=prefix, tags=[tag])
    id_column = getattr(model, id_attr)

    @router.post("", response_model=out_schema, status_code=status.HTTP_201_CREATED)
    def submit(
        payload: create_schema,
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

        record = model(
            **payload.model_dump(),
            owner_type=owner_type,
            student_id=student_id,
            employee_id=employee_id,
            status=initial_status,
        )
        db.add(record)
        db.commit()
        db.refresh(record)
        return record

    @router.get("/mine", response_model=list[out_schema])
    def list_mine(
        user: Student | Employee = Depends(get_current_identity),
        db: Session = Depends(get_db),
    ):
        if isinstance(user, Student):
            query = db.query(model).filter(model.student_id == user.student_id)
        else:
            query = db.query(model).filter(model.employee_id == user.emp_id)

        return query.order_by(model.submitted_at.desc()).all()

    @router.get("/pending", response_model=list[out_schema])
    def list_pending(
        verifier: Employee = Depends(get_current_verifier),
        db: Session = Depends(get_db),
    ):
        query = (
            db.query(model)
            .outerjoin(Student, model.student_id == Student.student_id)
            .outerjoin(Employee, model.employee_id == Employee.emp_id)
            .filter(verifier_scope_filter(verifier, model))
        )

        return query.order_by(model.submitted_at.asc()).all()

    @router.patch("/{record_id}/verify", response_model=out_schema)
    def verify(
        record_id: int,
        payload: CertificateVerify,
        verifier: Employee = Depends(get_current_verifier),
        db: Session = Depends(get_db),
    ):
        record = (
            db.query(model)
            .outerjoin(Student, model.student_id == Student.student_id)
            .outerjoin(Employee, model.employee_id == Employee.emp_id)
            .filter(id_column == record_id, verifier_scope_filter(verifier, model))
            .first()
        )
        if record is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Record not found")

        if payload.approve and not record.file_url.strip():
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Cannot approve a record without a verified file_url",
            )

        if not payload.approve:
            if not payload.remarks or len(payload.remarks.strip()) < 10:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail="Remarks of at least 10 characters are required when rejecting or requiring revision.",
                )

        if verifier.role == EmployeeRole.faculty_coordinator:
            if payload.approve:
                record.status = CertificateStatus.pending_hod
            else:
                record.status = CertificateStatus.revision_required
        elif verifier.role == EmployeeRole.admin_hod:
            if payload.approve:
                record.status = CertificateStatus.pending_admin
            else:
                record.status = CertificateStatus.pending
        else:
            record.status = CertificateStatus.approved if payload.approve else CertificateStatus.rejected

        record.verified_by = verifier.emp_id
        record.verified_at = datetime.now(timezone.utc)
        db.commit()
        db.refresh(record)
        return record

    return router
