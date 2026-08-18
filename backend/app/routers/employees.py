from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.auth import get_current_admin
from app.database import get_db
from app.models import Department, Employee, EmployeeRole, EmployeeRoleAssignment
from app.schemas import AssignHodRequest, FacultyAdminOut, HodOut, PendingEmployeeOut

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


def _to_pending_out(employee: Employee, department_name: str | None) -> PendingEmployeeOut:
    return PendingEmployeeOut(
        emp_id=employee.emp_id,
        name=employee.name,
        email=employee.email,
        department_id=employee.department_id,
        department_name=department_name,
        requested_role=employee.role_names[0] if employee.role_names else "",
    )


@router.get("/pending", response_model=list[PendingEmployeeOut])
def list_pending_registrations(
    admin: Employee = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    pending = _in_admin_scope(
        db.query(Employee).filter(Employee.is_approved == False),  # noqa: E712
        admin,
    ).order_by(Employee.name).all()
    dept_ids = {e.department_id for e in pending if e.department_id}
    names = {}
    if dept_ids:
        names = {d.dept_id: d.dept_name for d in db.query(Department).filter(Department.dept_id.in_(dept_ids)).all()}
    return [_to_pending_out(e, names.get(e.department_id)) for e in pending]


@router.patch("/{emp_id}/approve", response_model=PendingEmployeeOut)
def approve_registration(
    emp_id: int,
    admin: Employee = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    employee = _in_admin_scope(
        db.query(Employee).filter(Employee.emp_id == emp_id, Employee.is_approved == False),  # noqa: E712
        admin,
    ).first()
    if employee is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Pending registration not found")

    # One HOD per department: reject the *approval* rather than blocking every
    # future assign_hod call for the department -- approving is the point
    # where a second HOD would actually come into existence, so that's where
    # to stop it. Existing multi-HOD departments (approved before this check
    # existed) are left alone; this only guards new approvals going forward.
    if employee.department_id is not None and EmployeeRole.hod in {a.role for a in employee.roles}:
        existing_hod = (
            db.query(Employee)
            .filter(
                Employee.department_id == employee.department_id,
                Employee.is_approved == True,  # noqa: E712
                Employee.roles.any(EmployeeRoleAssignment.role == EmployeeRole.hod),
            )
            .first()
        )
        if existing_hod is not None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"{existing_hod.name} is already the approved HOD for this department",
            )

    employee.is_approved = True
    db.commit()
    db.refresh(employee)
    department_name = employee.department.dept_name if employee.department else None
    return _to_pending_out(employee, department_name)


@router.delete("/{emp_id}/reject", status_code=status.HTTP_204_NO_CONTENT)
def reject_registration(
    emp_id: int,
    admin: Employee = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    employee = _in_admin_scope(
        db.query(Employee).filter(Employee.emp_id == emp_id, Employee.is_approved == False),  # noqa: E712
        admin,
    ).first()
    if employee is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Pending registration not found")

    db.delete(employee)
    db.commit()
