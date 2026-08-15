from datetime import datetime
from typing import Literal

from pydantic import BaseModel, EmailStr

from app.models import CertificateStatus, ParticipationRole, StudentType


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    role: str


class LoginResult(BaseModel):
    """Either a real session (requires_role_selection=False, access_token
    set) or a prompt to pick a role (requires_role_selection=True, roles +
    pending_token set, no access_token yet)."""

    requires_role_selection: bool = False
    access_token: str | None = None
    token_type: str = "bearer"
    role: str | None = None
    roles: list[str] | None = None
    pending_token: str | None = None


class SelectRoleRequest(BaseModel):
    pending_token: str
    role: str


class MeResponse(BaseModel):
    id: int
    name: str
    email: str
    role: str


class RegisterRequest(BaseModel):
    name: str
    email: EmailStr
    password: str
    student_type: StudentType
    department_id: int | None = None


class EmployeeRegisterRequest(BaseModel):
    name: str
    email: EmailStr
    password: str
    role: Literal["faculty", "hod"]
    department_id: int | None = None


class RegistrationSubmitted(BaseModel):
    message: str = "Registration submitted. An admin will review and approve your account."


class DepartmentOut(BaseModel):
    dept_id: int
    dept_name: str

    model_config = {"from_attributes": True}


class AchievementCreate(BaseModel):
    title: str
    category: str
    sub_category: str | None = None
    file_url: str
    thumbnail_url: str | None = None
    metadata_fields: dict | None = None


class AchievementVerify(BaseModel):
    approve: bool
    remarks: str | None = None


class AchievementOut(BaseModel):
    id: int
    student_id: int | None
    employee_id: int | None
    owner_type: str
    title: str
    category: str
    sub_category: str | None
    file_url: str
    status: CertificateStatus
    submitted_at: datetime
    verified_by: int | None
    verified_at: datetime | None
    thumbnail_url: str | None
    metadata_fields: dict | None

    model_config = {"from_attributes": True}



class StudentOut(BaseModel):
    student_id: int
    name: str
    email: str
    student_type: StudentType

    model_config = {"from_attributes": True}


class FeedItem(BaseModel):
    id: int
    type: str  # "certificate", "publication", "patent", "internship", "event"
    title: str
    owner_type: str
    student_name: str | None = None
    category: str | None = None
    verified_at: datetime | None = None
    file_url: str
    is_featured: bool = False
    thumbnail_url: str | None = None

    model_config = {"from_attributes": True}
class CoordinatorOut(BaseModel):
    emp_id: int
    name: str

    model_config = {"from_attributes": True}


class StudentAdminOut(BaseModel):
    student_id: int
    name: str
    email: str
    department_id: int | None
    coordinator_id: int | None
    coordinator_name: str | None

class AssignCoordinatorRequest(BaseModel):
    coordinator_id: int


class HodOut(BaseModel):
    emp_id: int
    name: str

    model_config = {"from_attributes": True}


class FacultyAdminOut(BaseModel):
    emp_id: int
    name: str
    email: str
    department_id: int | None
    hod_id: int | None
    hod_name: str | None


class AssignHodRequest(BaseModel):
    hod_id: int


class PendingEmployeeOut(BaseModel):
    emp_id: int
    name: str
    email: str
    department_id: int | None
    department_name: str | None
    requested_role: str
