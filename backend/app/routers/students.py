from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.auth import get_current_admin
from app.database import get_db
from app.models import Employee, EmployeeRole, Student
from app.schemas import AssignCoordinatorRequest, CoordinatorOut, StudentAdminOut

router = APIRouter(prefix="/students", tags=["students"])


def _in_admin_scope(query, admin: Employee):
    """Department students, plus students with no department yet (e.g. a
    self-registered student who hasn't been placed anywhere) -- otherwise
    an unassigned student could never be picked up by any admin."""
    return query.filter((Student.department_id == admin.department_id) | (Student.department_id.is_(None)))


def _to_admin_out(student: Student, coordinator_name: str | None) -> StudentAdminOut:
    return StudentAdminOut(
        student_id=student.student_id,
        name=student.name,
        email=student.email,
        department_id=student.department_id,
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
        .filter(Employee.role == EmployeeRole.faculty_coordinator, Employee.department_id == admin.department_id)
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
            Employee.role == EmployeeRole.faculty_coordinator,
            Employee.department_id == admin.department_id,
        )
        .first()
    )
    if coordinator is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Coordinator not found in your department")

    # Keep department_id in sync with the assigned coordinator's department --
    # verifier_scope_filter's admin branch is department-based, so a student
    # left with department_id=None would vanish from every admin's queue the
    # moment they're assigned a coordinator, even though the coordinator
    # branch (coordinator_id-based) would still show them correctly.
    student.coordinator_id = coordinator.emp_id
    student.department_id = admin.department_id
    db.commit()
    db.refresh(student)
    return _to_admin_out(student, coordinator.name)
