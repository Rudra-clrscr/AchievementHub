"""Shared test harness.

Two things matter here before anything else:

1. **Nothing in this suite may ever touch the production database.** The app
   reads DATABASE_URL through `app.config.Settings`, which also loads
   `backend/.env` -- the real Supabase URL. Environment variables outrank the
   dotenv file in pydantic-settings, so this module sets DATABASE_URL to a
   throwaway SQLite URL *before* `app.*` is imported, and then asserts that the
   URL the app actually resolved is the test one. If that assertion ever fires,
   the suite refuses to run rather than risk writing to prod.

2. **The default backing store is in-memory SQLite** so `pytest` works with no
   setup on any machine or CI runner. Set TEST_DATABASE_URL to a scratch
   Postgres database to run the same suite against the real dialect -- worth
   doing before trusting a migration, since SQLite will not reproduce
   Postgres-specific behaviour (the `json` equality operator that broke
   `union()` in the pending queue is the standing example).
"""

import os

TEST_DATABASE_URL = os.environ.get("TEST_DATABASE_URL", "sqlite://")

os.environ["DATABASE_URL"] = TEST_DATABASE_URL
os.environ.setdefault("JWT_SECRET", "test-secret-not-used-anywhere-real")
os.environ.setdefault("SUPABASE_URL", "https://test.invalid")
os.environ.setdefault("SUPABASE_SERVICE_KEY", "test-service-key")
os.environ.setdefault("SUPABASE_STORAGE_BUCKET", "test-achievements")

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import create_engine  # noqa: E402
from sqlalchemy.orm import Session, sessionmaker  # noqa: E402
from sqlalchemy.pool import StaticPool  # noqa: E402

from app.auth import (  # noqa: E402
    create_access_token,
    create_pending_token,
    hash_password,
    pwd_context,
)
from app.config import settings  # noqa: E402
from app.database import Base, get_db  # noqa: E402
from app.main import app  # noqa: E402
from app.models import (  # noqa: E402
    Achievement,
    CertificateStatus,
    Department,
    Employee,
    EmployeeRole,
    EmployeeRoleAssignment,
    OwnerType,
    Section,
    Student,
    StudentType,
)

# Tripwire: if the app resolved anything other than our throwaway URL, a real
# database is one drop_all() away from being wiped. Stop the suite here.
assert settings.database_url == TEST_DATABASE_URL, (
    "Test suite refusing to run: app resolved DATABASE_URL="
    f"{settings.database_url!r}, expected {TEST_DATABASE_URL!r}. "
    "Something is overriding the test environment."
)
assert "supabase" not in settings.database_url.lower(), (
    "Test suite refusing to run against a Supabase database."
)

# bcrypt at its production cost is ~0.3s per hash, and the fixtures hash a
# password for every account they build -- enough on its own to push this suite
# past two minutes, which is long enough that people stop running it. Tests are
# not defending against offline cracking, so drop the work factor to bcrypt's
# minimum. This only rebinds the context inside the test process; the cost used
# by the running app is passlib's default and is untouched.
pwd_context.update(bcrypt__default_rounds=4)

TEST_PASSWORD = "test-password"


@pytest.fixture(scope="session")
def engine():
    if TEST_DATABASE_URL.startswith("sqlite"):
        # StaticPool keeps every session on the one connection that holds the
        # in-memory database; without it each checkout gets an empty DB.
        eng = create_engine(
            TEST_DATABASE_URL,
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
    else:
        eng = create_engine(TEST_DATABASE_URL)
    yield eng
    eng.dispose()


@pytest.fixture
def db_session(engine):
    """A clean schema per test. Endpoints commit, so there is no outer
    transaction to roll back -- the schema is dropped and rebuilt instead."""
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    session = TestingSessionLocal()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=engine)


@pytest.fixture
def client(db_session):
    """TestClient wired to the same session the test builds fixtures in, so
    data created in the test is visible to the endpoint and vice versa."""

    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


class Factory:
    """Builds the minimum valid object graph for a test. Every helper commits,
    matching how the endpoints under test see the world."""

    def __init__(self, session: Session):
        self.session = session
        self._counter = 0

    def _next(self) -> int:
        self._counter += 1
        return self._counter

    def department(self, name: str | None = None, location: str = "Main Block") -> Department:
        dept = Department(dept_name=name or f"Department {self._next()}", location=location)
        self.session.add(dept)
        self.session.commit()
        self.session.refresh(dept)
        return dept

    def section(
        self,
        department: Department,
        section_name: str = "A",
        year: int = 1,
        coordinator: Employee | None = None,
    ) -> Section:
        section = Section(
            section_name=section_name,
            year=year,
            department_id=department.dept_id,
            coordinator_id=coordinator.emp_id if coordinator else None,
        )
        self.session.add(section)
        self.session.commit()
        self.session.refresh(section)
        return section

    def employee(
        self,
        roles=(EmployeeRole.faculty,),
        department: Department | None = None,
        name: str | None = None,
        email: str | None = None,
        password: str = TEST_PASSWORD,
        hod: Employee | None = None,
        is_approved: bool = True,
    ) -> Employee:
        n = self._next()
        employee = Employee(
            name=name or f"Employee {n}",
            email=email or f"employee{n}@example.com",
            password_hash=hash_password(password),
            department_id=department.dept_id if department else None,
            hod_id=hod.emp_id if hod else None,
            is_approved=is_approved,
        )
        for role in roles:
            employee.roles.append(EmployeeRoleAssignment(role=EmployeeRole(role)))
        self.session.add(employee)
        self.session.commit()
        self.session.refresh(employee)
        return employee

    def student(
        self,
        department: Department | None = None,
        coordinator: Employee | None = None,
        section: Section | None = None,
        name: str | None = None,
        email: str | None = None,
        password: str = TEST_PASSWORD,
        student_type: StudentType = StudentType.inhouse,
        year: int | None = None,
    ) -> Student:
        n = self._next()
        student = Student(
            name=name or f"Student {n}",
            email=email or f"student{n}@example.com",
            password_hash=hash_password(password),
            student_type=student_type,
            department_id=department.dept_id if department else None,
            coordinator_id=coordinator.emp_id if coordinator else None,
            section_id=section.section_id if section else None,
            year=year if year is not None else (section.year if section else None),
        )
        self.session.add(student)
        self.session.commit()
        self.session.refresh(student)
        return student

    def achievement(
        self,
        student: Student | None = None,
        employee: Employee | None = None,
        title: str | None = None,
        category: str = "Certificate",
        sub_category: str | None = None,
        file_url: str = "https://files.test.invalid/proof.pdf",
        status: CertificateStatus = CertificateStatus.pending,
        is_featured: bool = False,
        metadata_fields: dict | None = None,
    ) -> Achievement:
        if (student is None) == (employee is None):
            raise ValueError("achievement() needs exactly one of student= or employee=")
        record = Achievement(
            title=title or f"Achievement {self._next()}",
            category=category,
            sub_category=sub_category,
            file_url=file_url,
            owner_type=OwnerType.student if student else OwnerType.employee,
            student_id=student.student_id if student else None,
            employee_id=employee.emp_id if employee else None,
            status=status,
            is_featured=is_featured,
            metadata_fields=metadata_fields,
        )
        self.session.add(record)
        self.session.commit()
        self.session.refresh(record)
        return record


@pytest.fixture
def factory(db_session) -> Factory:
    return Factory(db_session)


def auth_header(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def as_employee():
    """Header factory for an employee acting as one specific role, mirroring
    how a multi-role account gets exactly one active role per session."""

    def _as_employee(employee: Employee, role) -> dict:
        token = create_access_token(
            subject_id=employee.emp_id,
            entity_type="employee",
            role=EmployeeRole(role).value,
        )
        return auth_header(token)

    return _as_employee


@pytest.fixture
def as_student():
    def _as_student(student: Student) -> dict:
        token = create_access_token(
            subject_id=student.student_id, entity_type="student", role="student"
        )
        return auth_header(token)

    return _as_student


@pytest.fixture
def as_pending_employee():
    """Header carrying the short-lived role-selection token -- the one that is
    supposed to be useless against any role-gated endpoint."""

    def _as_pending(employee: Employee) -> dict:
        return auth_header(create_pending_token(subject_id=employee.emp_id))

    return _as_pending
