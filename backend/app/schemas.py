from datetime import datetime
from typing import Literal

from pydantic import BaseModel, EmailStr

from app.models import CertificateStatus, ParticipationRole, StudentType


class LoginRequest(BaseModel):
    email: EmailStr
    password: str
    # Role intent picked in the pre-login chooser (Faculty/HOD/Admin). When set
    # and the account actually holds it, login goes straight to a token for
    # that role -- no post-password role picker needed.
    role: str | None = None


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
    year: int | None = None
    section_id: int | None = None


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


class SectionOut(BaseModel):
    section_id: int
    section_name: str
    year: int
    department_id: int
    coordinator_id: int | None = None

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
    approved_by: int | None = None
    approved_at: datetime | None = None
    thumbnail_url: str | None
    metadata_fields: dict | None

    model_config = {"from_attributes": True}


class ReviewedAchievementOut(AchievementOut):
    """A record in a verifier's own review history. Carries the owner's name so
    the list is readable without a second round trip -- a coordinator scanning
    what they signed off needs to see whose achievement it was."""

    owner_name: str | None = None


class OwnerAchievementsOut(BaseModel):
    """One person in a verifier's scope, with their achievements grouped.

    `pending` is what *this* verifier can still act on, not simply what has
    status `pending`: faculty/HOD act at tier 1 (pending -> verified), admin
    at tier 2 (verified -> approved), so the same record is "waiting on me"
    for exactly one of them at a time. Grouping this way lets the roster
    double as a per-person verification queue -- the same decisions the
    Verification Queue offers, but with the owner's approved history sitting
    next to them for context.
    """

    owner_id: int
    owner_type: str
    name: str
    email: str
    approved: list[AchievementOut] = []
    pending: list[AchievementOut] = []


class StudentOut(BaseModel):
    student_id: int
    name: str
    email: str
    student_type: StudentType
    department_id: int | None = None
    year: int | None = None
    section_id: int | None = None

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
    year: int | None = None
    section_id: int | None = None
    section_name: str | None = None
    coordinator_id: int | None
    coordinator_name: str | None


class AssignCoordinatorRequest(BaseModel):
    coordinator_id: int


class AssignSectionCoordinatorRequest(BaseModel):
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
