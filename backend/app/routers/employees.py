from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.auth import get_current_admin
from app.database import get_db
from app.models import Employee, EmployeeRole, EmployeeRoleAssignment
from app.schemas import AssignHodRequest, FacultyAdminOut, HodOut

router = APIRouter(prefix="/employees", tags=["employees"])


def _in_admin_scope(query, admin: Employee):
    return query.filter((Employee.department_id == admin.department_id) | (Employee.department_id.is_(None)))


def _to_faculty_out(employee: Employee, hod_name: str | None) -> FacultyAdminOut:
    return FacultyAdminOut(
        emp_id=employee.emp_id,
        name=employee.name,
        email=employee.email,
        department_id=employee.department_id,
        hod_id=employee.hod_id,
        hod_name=hod_name,
    )


@router.get("/faculty", response_model=list[FacultyAdminOut])
def list_faculty(
    admin: Employee = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    faculty = _in_admin_scope(
        db.query(Employee).filter(Employee.roles.any(EmployeeRoleAssignment.role == EmployeeRole.faculty)),
        admin,
    ).order_by(Employee.name).all()
    hod_ids = {f.hod_id for f in faculty if f.hod_id}
    names = {}
    if hod_ids:
        names = {e.emp_id: e.name for e in db.query(Employee).filter(Employee.emp_id.in_(hod_ids)).all()}
    return [_to_faculty_out(f, names.get(f.hod_id)) for f in faculty]


@router.get("/hods", response_model=list[HodOut])
def list_hods(
    admin: Employee = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    return (
        db.query(Employee)
        .filter(
            Employee.roles.any(EmployeeRoleAssignment.role == EmployeeRole.hod),
            Employee.department_id == admin.department_id,
        )
        .order_by(Employee.name)
        .all()
    )


@router.patch("/{emp_id}/hod", response_model=FacultyAdminOut)
def assign_hod(
    emp_id: int,
    payload: AssignHodRequest,
    admin: Employee = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    faculty = _in_admin_scope(
        db.query(Employee).filter(
            Employee.emp_id == emp_id,
            Employee.roles.any(EmployeeRoleAssignment.role == EmployeeRole.faculty),
        ),
        admin,
    ).first()
    if faculty is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Faculty member not found")

    hod = (
        db.query(Employee)
        .filter(
            Employee.emp_id == payload.hod_id,
            Employee.roles.any(EmployeeRoleAssignment.role == EmployeeRole.hod),
            Employee.department_id == admin.department_id,
        )
        .first()
    )
    if hod is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="HOD not found in your department")

    # Keep department_id in sync with the assigned HOD's department -- mirrors
    # assign_coordinator's reasoning: faculty_verifier_scope_filter's admin
    # branch is department-based, so an unassigned faculty member would
    # vanish from every admin's queue the moment they're assigned a HOD,
    # even though the hod_id-based branch would still show them correctly.
    faculty.hod_id = hod.emp_id
    faculty.department_id = admin.department_id
    db.commit()
    db.refresh(faculty)
    return _to_faculty_out(faculty, hod.name)
