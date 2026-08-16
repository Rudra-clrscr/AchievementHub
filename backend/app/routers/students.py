from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.auth import get_current_admin
from app.database import get_db
from app.models import Employee, EmployeeRole, EmployeeRoleAssignment, Section, Student
from app.schemas import (
    AssignCoordinatorRequest,
    AssignSectionCoordinatorRequest,
    CoordinatorOut,
    SectionOut,
    StudentAdminOut,
)

router = APIRouter(prefix="/students", tags=["students"])


def _in_admin_scope(query, admin: Employee):
    return query.filter((Student.department_id == admin.department_id) | (Student.department_id.is_(None)))


def _to_admin_out(student: Student, coordinator_name: str | None) -> StudentAdminOut:
    return StudentAdminOut(
        student_id=student.student_id,
        name=student.name,
        email=student.email,
        department_id=student.department_id,
        year=student.year,
        section_id=student.section_id,
        section_name=student.section.section_name if student.section else None,
        coordinator_id=student.coordinator_id,
        coordinator_name=coordinator_name,
    )


@router.get("", response_model=list[StudentAdminOut])
def list_students(
    admin: Employee = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    students = _in_admin_scope(db.query(Student), admin).order_by(Student.name).all()
    coordinator_ids = {s.coordinator_id for s in students if s.coordinator_id}
    names = {}
    if coordinator_ids:
        names = {e.emp_id: e.name for e in db.query(Employee).filter(Employee.emp_id.in_(coordinator_ids)).all()}
    return [_to_admin_out(s, names.get(s.coordinator_id)) for s in students]


@router.get("/coordinators", response_model=list[CoordinatorOut])
def list_coordinators(
    admin: Employee = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    return (
        db.query(Employee)
        .filter(
            Employee.roles.any(EmployeeRoleAssignment.role == EmployeeRole.faculty),
            Employee.department_id == admin.department_id,
        )
        .order_by(Employee.name)
        .all()
    )


@router.patch("/{student_id}/coordinator", response_model=StudentAdminOut)
def assign_coordinator(
    student_id: int,
    payload: AssignCoordinatorRequest,
    admin: Employee = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    student = _in_admin_scope(db.query(Student).filter(Student.student_id == student_id), admin).first()
    if student is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Student not found")

    coordinator = (
        db.query(Employee)
        .filter(
            Employee.emp_id == payload.coordinator_id,
            Employee.roles.any(EmployeeRoleAssignment.role == EmployeeRole.faculty),
            Employee.department_id == admin.department_id,
        )
        .first()
    )
    if coordinator is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Coordinator not found in your department")

    student.coordinator_id = coordinator.emp_id
    student.department_id = admin.department_id
    db.commit()
    db.refresh(student)
    return _to_admin_out(student, coordinator.name)


@router.patch("/sections/{section_id}/coordinator", response_model=SectionOut)
def assign_section_coordinator(
    section_id: int,
    payload: AssignSectionCoordinatorRequest,
    admin: Employee = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    section = db.query(Section).filter(Section.section_id == section_id, Section.department_id == admin.department_id).first()
    if section is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Section not found in your department")

    coordinator = (
        db.query(Employee)
        .filter(
            Employee.emp_id == payload.coordinator_id,
            Employee.roles.any(EmployeeRoleAssignment.role == EmployeeRole.faculty),
            Employee.department_id == admin.department_id,
        )
        .first()
    )
    if coordinator is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Faculty coordinator not found in your department")

    section.coordinator_id = coordinator.emp_id
    
    db.query(Student).filter(Student.section_id == section.section_id).update(
        {"coordinator_id": coordinator.emp_id, "department_id": admin.department_id},
        synchronize_session=False,
    )
    
    db.commit()
    db.refresh(section)
    return section
