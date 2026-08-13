import enum
from datetime import datetime

from sqlalchemy import DateTime, Enum, Float, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class EmployeeRole(str, enum.Enum):
    principal = "principal"
    faculty = "faculty"
    hod = "hod"
    admin = "admin"


class StudentType(str, enum.Enum):
    inhouse = "inhouse"
    outhouse = "outhouse"



class CertificateStatus(str, enum.Enum):
    pending = "pending"
    verified = "verified"
    approved = "approved"
    rejected = "rejected"


class OwnerType(str, enum.Enum):
    student = "student"
    employee = "employee"


class ParticipationRole(str, enum.Enum):
    participant = "participant"
    organizer = "organizer"


class AchievementMixin:
    """Shared columns for the submit -> pending -> verify pipeline.

    owner_type/employee_id exist so faculty-authored achievements have
    somewhere to live once an Admin/Principal verification flow is built;
    this phase's endpoints only ever write owner_type=student.
    """

    owner_type: Mapped[OwnerType] = mapped_column(Enum(OwnerType), nullable=False, default=OwnerType.student)
    student_id: Mapped[int | None] = mapped_column(ForeignKey("students.student_id"))
    employee_id: Mapped[int | None] = mapped_column(ForeignKey("employees.emp_id"))
    file_url: Mapped[str] = mapped_column(String(500), nullable=False)
    status: Mapped[CertificateStatus] = mapped_column(
        Enum(CertificateStatus), nullable=False, default=CertificateStatus.pending
    )
    submitted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    verified_by: Mapped[int | None] = mapped_column(ForeignKey("employees.emp_id"))
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    is_featured: Mapped[bool] = mapped_column(default=False, server_default="false", nullable=False)
    thumbnail_url: Mapped[str | None] = mapped_column(String(500))




class Department(Base):
    __tablename__ = "departments"

    dept_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    dept_name: Mapped[str] = mapped_column(String(120), nullable=False)
    location: Mapped[str | None] = mapped_column(String(120))

    employees: Mapped[list["Employee"]] = relationship(back_populates="department")
    students: Mapped[list["Student"]] = relationship(back_populates="department")


class Employee(Base):
    __tablename__ = "employees"

    emp_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    email: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    phone_number: Mapped[str | None] = mapped_column(String(20))
    salary: Mapped[float | None] = mapped_column(Float)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    department_id: Mapped[int | None] = mapped_column(ForeignKey("departments.dept_id"))
    hod_id: Mapped[int | None] = mapped_column(ForeignKey("employees.emp_id"))

    department: Mapped[Department | None] = relationship(back_populates="employees")
    dependents: Mapped[list["Dependent"]] = relationship(back_populates="employee")
    coordinated_students: Mapped[list["Student"]] = relationship(back_populates="coordinator")
    achievements: Mapped[list["Achievement"]] = relationship("Achievement", foreign_keys="[Achievement.employee_id]", back_populates="employee")
    verified_achievements: Mapped[list["Achievement"]] = relationship("Achievement", foreign_keys="[Achievement.verified_by]", back_populates="verifier")
    roles: Mapped[list["EmployeeRoleAssignment"]] = relationship(back_populates="employee", cascade="all, delete-orphan")
    hod: Mapped["Employee | None"] = relationship(remote_side=[emp_id], foreign_keys=[hod_id], back_populates="supervised_faculty")
    supervised_faculty: Mapped[list["Employee"]] = relationship(foreign_keys=[hod_id], back_populates="hod")

    @property
    def role_names(self) -> list[str]:
        return [assignment.role.value for assignment in self.roles]


class EmployeeRoleAssignment(Base):
    __tablename__ = "employee_roles"

    employee_id: Mapped[int] = mapped_column(ForeignKey("employees.emp_id"), primary_key=True)
    role: Mapped[EmployeeRole] = mapped_column(Enum(EmployeeRole), primary_key=True)

    employee: Mapped[Employee] = relationship(back_populates="roles")


class Dependent(Base):
    __tablename__ = "dependents"

    dep_name: Mapped[str] = mapped_column(String(120), primary_key=True)
    employee_id: Mapped[int] = mapped_column(ForeignKey("employees.emp_id"), primary_key=True)
    relationship_: Mapped[str | None] = mapped_column("relationship", String(50))
    age: Mapped[int | None] = mapped_column(Integer)

    employee: Mapped[Employee] = relationship(back_populates="dependents")


class Project(Base):
    __tablename__ = "projects"

    proj_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    proj_name: Mapped[str] = mapped_column(String(120), nullable=False)
    duration: Mapped[str | None] = mapped_column(String(50))


class Student(Base):
    __tablename__ = "students"

    student_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    email: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    student_type: Mapped[StudentType] = mapped_column(Enum(StudentType), nullable=False)
    department_id: Mapped[int | None] = mapped_column(ForeignKey("departments.dept_id"))
    coordinator_id: Mapped[int | None] = mapped_column(ForeignKey("employees.emp_id"))

    department: Mapped[Department | None] = relationship(back_populates="students")
    coordinator: Mapped[Employee | None] = relationship(back_populates="coordinated_students")
    achievements: Mapped[list["Achievement"]] = relationship(back_populates="student")



class Achievement(AchievementMixin, Base):
    __tablename__ = "achievements"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    category: Mapped[str] = mapped_column(String(100), nullable=False)
    sub_category: Mapped[str | None] = mapped_column(String(100))
    
    # Store any flexible extra fields (like patent numbers, grant amounts, etc.)
    from sqlalchemy import JSON
    metadata_fields: Mapped[dict | None] = mapped_column(JSON)

    student: Mapped[Student | None] = relationship(back_populates="achievements")
    employee: Mapped[Employee | None] = relationship("Employee", foreign_keys="[Achievement.employee_id]", back_populates="achievements")
    verifier: Mapped[Employee | None] = relationship("Employee", foreign_keys="[Achievement.verified_by]", back_populates="verified_achievements")

