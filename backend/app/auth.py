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
    EmployeeRole.faculty_coordinator.value,
    EmployeeRole.admin_hod.value,
    EmployeeRole.admin_clerk.value,
}


def get_current_verifier(
    token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)
) -> Employee:
    payload = _decode_token(token)
    if payload.get("entity_type") != "employee" or payload.get("role") not in VERIFIER_ROLES:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Faculty coordinator or admin access only")
    employee = db.get(Employee, int(payload["sub"]))
    if employee is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Employee not found")
    return employee


ADMIN_ROLES = {
    EmployeeRole.admin_hod.value,
    EmployeeRole.admin_clerk.value,
}


def get_current_admin(
    token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)
) -> Employee:
    """Stricter than get_current_verifier: only Admin (HOD/Clerk), not
    faculty coordinators. Assigning which coordinator a student belongs to
    is an admin-level action -- a coordinator reassigning their own
    students would be able to hand off the students they don't want to
    review, which defeats the point of the assignment."""
    payload = _decode_token(token)
    if payload.get("entity_type") != "employee" or payload.get("role") not in ADMIN_ROLES:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin access only")
    employee = db.get(Employee, int(payload["sub"]))
    if employee is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Employee not found")
    return employee


def verifier_scope_filter(employee: Employee):
    """A faculty coordinator only sees/acts on their own assigned students
    (one coordinator per class, per the spec). An Admin (HOD/Clerk) sees/
    acts on every student in their department -- one tier up, matching the
    spec's "Admin ... Department level" scope. Principal is out of scope
    here; that role is about global monitoring/reporting, not verification.
    """
    if employee.role == EmployeeRole.faculty_coordinator:
        return Student.coordinator_id == employee.emp_id
    return Student.department_id == employee.department_id

def faculty_verifier_scope_filter(verifier: Employee):
    """Scope filter for verifying faculty achievements.
    Only Admins (HOD/Clerk) can verify faculty achievements, and only for
    faculty in their own department. Faculty coordinators cannot verify
    other faculty.
    """
    if verifier.role not in ADMIN_ROLES:
        # Returning a condition that is always False in SQLAlchemy
        return Employee.emp_id == None
    return Employee.department_id == verifier.department_id


def get_current_identity(
    token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)
) -> Employee | Student:
    payload = _decode_token(token)
    model = Student if payload.get("entity_type") == "student" else Employee
    entity = db.get(model, int(payload["sub"]))
    if entity is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Account not found")
    return entity
