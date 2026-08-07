from datetime import datetime

from pydantic import BaseModel, EmailStr

from app.models import CertificateCategory, CertificateStatus, ParticipationRole, StudentType


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
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


class DepartmentOut(BaseModel):
    dept_id: int
    dept_name: str

    model_config = {"from_attributes": True}


class CertificateCreate(BaseModel):
    title: str
    issuer: str | None = None
    category: CertificateCategory
    file_url: str


class CertificateVerify(BaseModel):
    approve: bool


class CertificateOut(BaseModel):
    cert_id: int
    student_id: int
    title: str
    issuer: str | None
    category: CertificateCategory
    file_url: str
    status: CertificateStatus
    submitted_at: datetime
    verified_by: int | None
    verified_at: datetime | None

    model_config = {"from_attributes": True}


class PublicationCreate(BaseModel):
    title: str
    venue: str | None = None
    publication_date: datetime | None = None
    file_url: str


class PublicationOut(BaseModel):
    pub_id: int
    student_id: int | None
    title: str
    venue: str | None
    publication_date: datetime | None
    file_url: str
    status: CertificateStatus
    submitted_at: datetime
    verified_by: int | None
    verified_at: datetime | None

    model_config = {"from_attributes": True}


class PatentCreate(BaseModel):
    title: str
    patent_number: str | None = None
    filing_date: datetime | None = None
    file_url: str


class PatentOut(BaseModel):
    patent_id: int
    student_id: int | None
    title: str
    patent_number: str | None
    filing_date: datetime | None
    file_url: str
    status: CertificateStatus
    submitted_at: datetime
    verified_by: int | None
    verified_at: datetime | None

    model_config = {"from_attributes": True}


class InternshipCreate(BaseModel):
    organization: str
    role_title: str | None = None
    start_date: datetime | None = None
    end_date: datetime | None = None
    file_url: str


class InternshipOut(BaseModel):
    internship_id: int
    student_id: int | None
    organization: str
    role_title: str | None
    start_date: datetime | None
    end_date: datetime | None
    file_url: str
    status: CertificateStatus
    submitted_at: datetime
    verified_by: int | None
    verified_at: datetime | None

    model_config = {"from_attributes": True}


class EventParticipationCreate(BaseModel):
    event_name: str
    event_date: datetime | None = None
    participation_role: ParticipationRole = ParticipationRole.participant
    file_url: str


class EventParticipationOut(BaseModel):
    event_id: int
    student_id: int | None
    event_name: str
    event_date: datetime | None
    participation_role: ParticipationRole
    file_url: str
    status: CertificateStatus
    submitted_at: datetime
    verified_by: int | None
    verified_at: datetime | None

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
    coordinator_id: int
