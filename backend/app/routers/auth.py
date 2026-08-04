from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.auth import create_access_token, get_current_identity, hash_password, verify_password
from app.database import get_db
from app.models import Employee, Student
from app.schemas import LoginRequest, MeResponse, RegisterRequest, TokenResponse

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login", response_model=TokenResponse)
def login(payload: LoginRequest, db: Session = Depends(get_db)):
    employee = db.query(Employee).filter(Employee.email == payload.email).first()
    if employee and verify_password(payload.password, employee.password_hash):
        token = create_access_token(subject_id=employee.emp_id, entity_type="employee", role=employee.role.value)
        return TokenResponse(access_token=token, role=employee.role.value)

    student = db.query(Student).filter(Student.email == payload.email).first()
    if student and verify_password(payload.password, student.password_hash):
        token = create_access_token(subject_id=student.student_id, entity_type="student", role="student")
        return TokenResponse(access_token=token, role="student")

    raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid email or password")


@router.post("/register", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
def register(payload: RegisterRequest, db: Session = Depends(get_db)):
    """Self-service registration is student-only. Faculty/Admin/Principal accounts are
    provisioned by the institution (seed data today), not created through this form --
    those roles carry verification authority that shouldn't be self-assigned."""
    email_taken = (
        db.query(Employee).filter(Employee.email == payload.email).first()
        or db.query(Student).filter(Student.email == payload.email).first()
    )
    if email_taken:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="An account with this email already exists")

    student = Student(
        name=payload.name,
        email=payload.email,
        password_hash=hash_password(payload.password),
        student_type=payload.student_type,
        department_id=payload.department_id,
    )
    db.add(student)
    db.commit()
    db.refresh(student)

    token = create_access_token(subject_id=student.student_id, entity_type="student", role="student")
    return TokenResponse(access_token=token, role="student")


@router.get("/me", response_model=MeResponse)
def me(identity: Employee | Student = Depends(get_current_identity)):
    if isinstance(identity, Student):
        return MeResponse(id=identity.student_id, name=identity.name, email=identity.email, role="student")
    return MeResponse(id=identity.emp_id, name=identity.name, email=identity.email, role=identity.role.value)
