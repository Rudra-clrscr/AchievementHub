from datetime import datetime, timedelta, timezone

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from passlib.context import CryptContext
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.models import Employee, EmployeeRole, Student

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="auth/login")


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    return pwd_context.verify(password, password_hash)


def create_access_token(*, subject_id: int, entity_type: str, role: str) -> str:
    expire = datetime.now(timezone.utc) + timedelta(minutes=settings.jwt_expire_minutes)
    payload = {"sub": str(subject_id), "entity_type": entity_type, "role": role, "exp": expire}
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def _decode_token(token: str) -> dict:
    try:
        return jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
    except JWTError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired token")


def get_current_student(
    token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)
) -> Student:
    payload = _decode_token(token)
    if payload.get("entity_type") != "student":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Student access only")
    student = db.get(Student, int(payload["sub"]))
    if student is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Student not found")
    return student


VERIFIER_ROLES = {
    EmployeeRole.faculty.value,
    EmployeeRole.hod.value,
    EmployeeRole.admin.value,
}


def get_current_verifier(
    token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)
) -> Employee:
    payload = _decode_token(token)
    if payload.get("entity_type") != "employee" or payload.get("role") not in VERIFIER_ROLES:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Faculty, HOD, or admin access only")
    employee = db.get(Employee, int(payload["sub"]))
    if employee is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Employee not found")
    employee.active_role = payload["role"]
    return employee


ADMIN_ROLES = {
    EmployeeRole.admin.value,
}


def get_current_admin(
    token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)
) -> Employee:
    """Stricter than get_current_verifier: only Admin, not faculty or HOD.
    Assigning which coordinator/HOD someone reports to is an admin-level
    action -- a coordinator or HOD reassigning their own reports would be
    able to hand off the ones they don't want to review, which defeats the
    point of the assignment."""
    payload = _decode_token(token)
    if payload.get("entity_type") != "employee" or payload.get("role") not in ADMIN_ROLES:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin access only")
    employee = db.get(Employee, int(payload["sub"]))
    if employee is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Employee not found")
    employee.active_role = payload["role"]
    return employee


def verifier_scope_filter(employee: Employee):
    """A faculty member only sees/acts on their own assigned students (one
    coordinator per class, per the spec). Admin sees/acts on every student
    in their department -- the tier-2 view, matching the spec's "Admin ...
    Department level" scope. Principal is out of scope here; that role is
    about global monitoring/reporting, not verification. Scoping is keyed
    off the token's active_role (the role picked at login), not the
    employee's full role set, since a multi-role employee acts as one role
    per session.
    """
    if employee.active_role == EmployeeRole.faculty.value:
        return Student.coordinator_id == employee.emp_id
    elif employee.active_role == EmployeeRole.admin.value:
        return Student.department_id == employee.department_id
    return Student.student_id == None

def faculty_verifier_scope_filter(verifier: Employee):
    """Scope filter for verifying faculty-owned achievements.
    HOD verifies only the faculty explicitly assigned to them (hod_id),
    mirroring how a faculty coordinator only sees their assigned students.
    Admin sees every faculty member in their department -- the tier-2
    view. Faculty cannot verify other faculty.
    """
    if verifier.active_role == EmployeeRole.hod.value:
        return Employee.hod_id == verifier.emp_id
    elif verifier.active_role == EmployeeRole.admin.value:
        return Employee.department_id == verifier.department_id
    return Employee.emp_id == None


def get_current_identity(
    token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)
) -> Employee | Student:
    payload = _decode_token(token)
    model = Student if payload.get("entity_type") == "student" else Employee
    entity = db.get(model, int(payload["sub"]))
    if entity is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Account not found")
    if isinstance(entity, Employee):
        entity.active_role = payload.get("role")
    return entity


PENDING_TOKEN_EXPIRE_MINUTES = 5


def create_pending_token(*, subject_id: int) -> str:
    """Short-lived token identifying an employee who has passed the
    password check but hasn't picked which of their roles to act as this
    session. Carries no `role` claim, so it can't be used against any
    role-gated dependency -- only /auth/select-role accepts it."""
    expire = datetime.now(timezone.utc) + timedelta(minutes=PENDING_TOKEN_EXPIRE_MINUTES)
    payload = {"sub": str(subject_id), "entity_type": "employee_pending", "exp": expire}
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def resolve_pending_employee(token: str, db: Session) -> Employee:
    payload = _decode_token(token)
    if payload.get("entity_type") != "employee_pending":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired role-selection token")
    employee = db.get(Employee, int(payload["sub"]))
    if employee is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Employee not found")
    return employee
