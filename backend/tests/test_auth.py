"""Login, role selection, and registration.

The properties worth protecting here are the ones that decide *who can act as
what*: an account only ever gets a token for a role it actually holds, an
unapproved employee cannot log in at all, self-service registration cannot
hand out verification authority, and the short-lived role-selection token is
useless against anything role-gated.
"""

from app.models import Employee, EmployeeRole, Student
from conftest import TEST_PASSWORD


def login(client, email, password=TEST_PASSWORD, role=None):
    body = {"email": email, "password": password}
    if role is not None:
        body["role"] = role
    return client.post("/auth/login", json=body)


# --------------------------------------------------------------------------
# Login
# --------------------------------------------------------------------------


def test_student_login_returns_a_student_token(client, factory):
    student = factory.student(email="learner@example.com")

    response = login(client, "learner@example.com")

    assert response.status_code == 200
    body = response.json()
    assert body["role"] == "student"
    assert body["access_token"]
    assert body["requires_role_selection"] is False

    me = client.get("/auth/me", headers={"Authorization": f"Bearer {body['access_token']}"})
    assert me.status_code == 200
    assert me.json() == {
        "id": student.student_id,
        "name": student.name,
        "email": "learner@example.com",
        "role": "student",
    }


def test_wrong_password_is_rejected(client, factory):
    factory.student(email="learner@example.com")

    response = login(client, "learner@example.com", password="not-the-password")

    assert response.status_code == 401
    assert response.json()["detail"] == "Invalid email or password"


def test_unknown_email_is_rejected(client, factory):
    response = login(client, "nobody@example.com")

    assert response.status_code == 401


def test_single_role_employee_gets_a_token_without_a_picker(client, factory):
    dept = factory.department()
    factory.employee(roles=[EmployeeRole.faculty], department=dept, email="prof@example.com")

    response = login(client, "prof@example.com")

    assert response.status_code == 200
    body = response.json()
    assert body["requires_role_selection"] is False
    assert body["role"] == "faculty"
    assert body["access_token"]


def test_multi_role_employee_must_pick_a_role(client, factory):
    dept = factory.department()
    factory.employee(
        roles=[EmployeeRole.faculty, EmployeeRole.hod], department=dept, email="dual@example.com"
    )

    response = login(client, "dual@example.com")

    assert response.status_code == 200
    body = response.json()
    assert body["requires_role_selection"] is True
    assert body["access_token"] is None, "no session should exist before a role is chosen"
    assert sorted(body["roles"]) == ["faculty", "hod"]
    assert body["pending_token"]


def test_prelogin_role_choice_skips_the_picker(client, factory):
    dept = factory.department()
    factory.employee(
        roles=[EmployeeRole.faculty, EmployeeRole.hod], department=dept, email="dual@example.com"
    )

    response = login(client, "dual@example.com", role="hod")

    assert response.status_code == 200
    body = response.json()
    assert body["requires_role_selection"] is False
    assert body["role"] == "hod"
    assert body["access_token"]


def test_prelogin_role_the_account_does_not_hold_is_refused(client, factory):
    dept = factory.department()
    factory.employee(roles=[EmployeeRole.faculty], department=dept, email="prof@example.com")

    response = login(client, "prof@example.com", role="admin")

    assert response.status_code == 403
    assert "does not hold the admin role" in response.json()["detail"]


def test_unapproved_employee_cannot_log_in(client, factory):
    dept = factory.department()
    factory.employee(
        roles=[EmployeeRole.faculty],
        department=dept,
        email="waiting@example.com",
        is_approved=False,
    )

    response = login(client, "waiting@example.com")

    assert response.status_code == 403
    assert "pending admin approval" in response.json()["detail"]


def test_employee_with_no_roles_cannot_log_in(client, factory):
    factory.employee(roles=[], email="roleless@example.com")

    response = login(client, "roleless@example.com")

    assert response.status_code == 403
    assert response.json()["detail"] == "Account has no roles assigned"


# --------------------------------------------------------------------------
# Role selection
# --------------------------------------------------------------------------


def test_select_role_issues_a_token_for_a_held_role(client, factory):
    dept = factory.department()
    employee = factory.employee(
        roles=[EmployeeRole.faculty, EmployeeRole.admin], department=dept, email="dual@example.com"
    )
    pending_token = login(client, "dual@example.com").json()["pending_token"]

    response = client.post("/auth/select-role", json={"pending_token": pending_token, "role": "admin"})

    assert response.status_code == 200
    assert response.json()["role"] == "admin"

    me = client.get(
        "/auth/me", headers={"Authorization": f"Bearer {response.json()['access_token']}"}
    )
    assert me.json() == {
        "id": employee.emp_id,
        "name": employee.name,
        "email": "dual@example.com",
        "role": "admin",
    }


def test_select_role_refuses_a_role_the_account_does_not_hold(client, factory):
    dept = factory.department()
    factory.employee(
        roles=[EmployeeRole.faculty, EmployeeRole.hod], department=dept, email="dual@example.com"
    )
    pending_token = login(client, "dual@example.com").json()["pending_token"]

    response = client.post("/auth/select-role", json={"pending_token": pending_token, "role": "admin"})

    assert response.status_code == 403
    assert response.json()["detail"] == "You do not hold this role"


def test_an_access_token_is_not_accepted_as_a_role_selection_token(client, factory):
    """The two token kinds are distinguished by entity_type, not just by shape."""
    dept = factory.department()
    factory.employee(roles=[EmployeeRole.faculty], department=dept, email="prof@example.com")
    access_token = login(client, "prof@example.com").json()["access_token"]

    response = client.post("/auth/select-role", json={"pending_token": access_token, "role": "faculty"})

    assert response.status_code == 401
    assert "role-selection token" in response.json()["detail"]


def test_pending_token_is_useless_against_role_gated_endpoints(
    client, factory, as_pending_employee
):
    """A pending token carries no role claim, so it must not open a verifier
    or admin queue -- that is the whole reason it exists as a separate kind."""
    dept = factory.department()
    employee = factory.employee(
        roles=[EmployeeRole.admin, EmployeeRole.hod], department=dept
    )
    headers = as_pending_employee(employee)

    assert client.get("/achievements/pending", headers=headers).status_code == 403
    assert client.get("/employees/faculty", headers=headers).status_code == 403
    assert client.get("/students", headers=headers).status_code == 403


def test_pending_token_opens_no_session_at_all(client, factory, as_pending_employee):
    """Not just the role-gated endpoints: an employee who has passed the
    password check but not yet picked a role has no active role, and so
    should have no session either. `get_current_identity` used to treat
    "not a student" as "an employee", which let a pending token read /auth/me
    and submit achievements for its five-minute lifetime."""
    dept = factory.department()
    employee = factory.employee(roles=[EmployeeRole.faculty, EmployeeRole.hod], department=dept)
    headers = as_pending_employee(employee)

    assert client.get("/auth/me", headers=headers).status_code == 401
    assert client.get("/achievements/mine", headers=headers).status_code == 401

    submission = client.post(
        "/achievements",
        json={
            "title": "Submitted before picking a role",
            "category": "Certificate",
            "file_url": "https://files.example.com/x.pdf",
        },
        headers=headers,
    )
    assert submission.status_code == 401


def test_a_token_with_an_unknown_entity_type_is_rejected(client, factory):
    """Belt-and-braces on the same check: only the two session kinds the app
    actually issues are accepted, whatever else is signed with the key."""
    from datetime import datetime, timedelta, timezone

    from jose import jwt

    from app.config import settings

    employee = factory.employee()
    forged = jwt.encode(
        {
            "sub": str(employee.emp_id),
            "entity_type": "superuser",
            "role": "admin",
            "exp": datetime.now(timezone.utc) + timedelta(minutes=5),
        },
        settings.jwt_secret,
        algorithm=settings.jwt_algorithm,
    )

    response = client.get("/auth/me", headers={"Authorization": f"Bearer {forged}"})

    assert response.status_code == 401


def test_a_token_signed_with_the_wrong_key_is_rejected(client, factory):
    from datetime import datetime, timedelta, timezone

    from jose import jwt

    employee = factory.employee(roles=[EmployeeRole.admin])
    forged = jwt.encode(
        {
            "sub": str(employee.emp_id),
            "entity_type": "employee",
            "role": "admin",
            "exp": datetime.now(timezone.utc) + timedelta(minutes=5),
        },
        "not-the-servers-signing-key",
        algorithm="HS256",
    )

    response = client.get("/auth/me", headers={"Authorization": f"Bearer {forged}"})

    assert response.status_code == 401


def test_an_expired_token_is_rejected(client, factory):
    from datetime import datetime, timedelta, timezone

    from jose import jwt

    from app.config import settings

    student = factory.student()
    expired = jwt.encode(
        {
            "sub": str(student.student_id),
            "entity_type": "student",
            "role": "student",
            "exp": datetime.now(timezone.utc) - timedelta(minutes=1),
        },
        settings.jwt_secret,
        algorithm=settings.jwt_algorithm,
    )

    response = client.get("/auth/me", headers={"Authorization": f"Bearer {expired}"})

    assert response.status_code == 401


def test_a_token_for_a_deleted_account_is_rejected(client, factory, db_session, as_employee):
    """Rejecting a registration deletes the row; any token already issued for
    it has to stop working."""
    dept = factory.department()
    employee = factory.employee(roles=[EmployeeRole.faculty], department=dept)
    headers = as_employee(employee, EmployeeRole.faculty)
    assert client.get("/auth/me", headers=headers).status_code == 200

    db_session.delete(employee)
    db_session.commit()

    assert client.get("/auth/me", headers=headers).status_code == 401


def test_garbage_token_is_rejected(client, factory):
    factory.department()

    response = client.get("/auth/me", headers={"Authorization": "Bearer not-a-real-jwt"})

    assert response.status_code == 401


# --------------------------------------------------------------------------
# Student self-registration
# --------------------------------------------------------------------------


def test_student_registration_creates_an_account_and_logs_in(client, db_session, factory):
    dept = factory.department()

    response = client.post(
        "/auth/register",
        json={
            "name": "New Student",
            "email": "new@example.com",
            "password": "hunter2hunter2",
            "student_type": "inhouse",
            "department_id": dept.dept_id,
        },
    )

    assert response.status_code == 201
    assert response.json()["role"] == "student"

    created = db_session.query(Student).filter(Student.email == "new@example.com").one()
    assert created.department_id == dept.dept_id
    assert created.password_hash != "hunter2hunter2", "password must not be stored in the clear"
    assert login(client, "new@example.com", password="hunter2hunter2").status_code == 200


def test_registration_rejects_an_email_already_used_by_a_student(client, factory):
    factory.student(email="taken@example.com")

    response = client.post(
        "/auth/register",
        json={
            "name": "Impostor",
            "email": "taken@example.com",
            "password": "hunter2hunter2",
            "student_type": "inhouse",
        },
    )

    assert response.status_code == 409


def test_registration_rejects_an_email_already_used_by_an_employee(client, factory):
    factory.employee(email="taken@example.com")

    response = client.post(
        "/auth/register",
        json={
            "name": "Impostor",
            "email": "taken@example.com",
            "password": "hunter2hunter2",
            "student_type": "inhouse",
        },
    )

    assert response.status_code == 409


def test_registration_rejects_an_unknown_section(client, factory):
    response = client.post(
        "/auth/register",
        json={
            "name": "New Student",
            "email": "new@example.com",
            "password": "hunter2hunter2",
            "student_type": "inhouse",
            "section_id": 9999,
        },
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "Invalid section ID"


def test_registration_rejects_a_section_from_another_department(client, factory):
    dept_a = factory.department(name="CSE")
    dept_b = factory.department(name="Mechanical")
    section = factory.section(dept_a, section_name="A", year=1)

    response = client.post(
        "/auth/register",
        json={
            "name": "New Student",
            "email": "new@example.com",
            "password": "hunter2hunter2",
            "student_type": "inhouse",
            "department_id": dept_b.dept_id,
            "section_id": section.section_id,
        },
    )

    assert response.status_code == 400
    assert "does not belong to selected department" in response.json()["detail"]


def test_registration_rejects_a_section_from_another_year(client, factory):
    dept = factory.department()
    section = factory.section(dept, section_name="A", year=1)

    response = client.post(
        "/auth/register",
        json={
            "name": "New Student",
            "email": "new@example.com",
            "password": "hunter2hunter2",
            "student_type": "inhouse",
            "section_id": section.section_id,
            "year": 3,
        },
    )

    assert response.status_code == 400
    assert "does not match selected year" in response.json()["detail"]


def test_registration_infers_department_and_year_from_the_section(client, db_session, factory):
    """PR #11 review outcome: the section is the source of truth, not the
    separately-submitted department/year fields."""
    dept = factory.department()
    section = factory.section(dept, section_name="B", year=3)

    response = client.post(
        "/auth/register",
        json={
            "name": "New Student",
            "email": "new@example.com",
            "password": "hunter2hunter2",
            "student_type": "inhouse",
            "section_id": section.section_id,
        },
    )

    assert response.status_code == 201
    created = db_session.query(Student).filter(Student.email == "new@example.com").one()
    assert created.department_id == dept.dept_id
    assert created.year == 3


def test_registration_inherits_the_sections_coordinator(client, db_session, factory):
    dept = factory.department()
    coordinator = factory.employee(roles=[EmployeeRole.faculty], department=dept)
    section = factory.section(dept, section_name="A", year=2, coordinator=coordinator)

    client.post(
        "/auth/register",
        json={
            "name": "New Student",
            "email": "new@example.com",
            "password": "hunter2hunter2",
            "student_type": "inhouse",
            "section_id": section.section_id,
        },
    )

    created = db_session.query(Student).filter(Student.email == "new@example.com").one()
    assert created.coordinator_id == coordinator.emp_id


def test_registration_without_a_section_leaves_the_student_unassigned(client, db_session, factory):
    dept = factory.department()

    client.post(
        "/auth/register",
        json={
            "name": "Outhouse Student",
            "email": "new@example.com",
            "password": "hunter2hunter2",
            "student_type": "outhouse",
            "department_id": dept.dept_id,
        },
    )

    created = db_session.query(Student).filter(Student.email == "new@example.com").one()
    assert created.coordinator_id is None
    assert created.section_id is None


# --------------------------------------------------------------------------
# Employee self-registration
# --------------------------------------------------------------------------


def test_employee_registration_starts_unapproved_and_cannot_log_in(client, db_session, factory):
    """Self-assigning verification authority outright would let anyone grant
    themselves review power, so the account is inert until an admin approves."""
    dept = factory.department()

    response = client.post(
        "/auth/register-employee",
        json={
            "name": "Hopeful Faculty",
            "email": "hopeful@example.com",
            "password": "hunter2hunter2",
            "role": "faculty",
            "department_id": dept.dept_id,
        },
    )

    assert response.status_code == 201
    assert "approve" in response.json()["message"]

    created = db_session.query(Employee).filter(Employee.email == "hopeful@example.com").one()
    assert created.is_approved is False
    assert created.role_names == ["faculty"]

    assert login(client, "hopeful@example.com", password="hunter2hunter2").status_code == 403


def test_employee_registration_refuses_the_admin_role(client, factory):
    """Admin is the role that approves everyone else; it cannot be self-granted."""
    dept = factory.department()

    response = client.post(
        "/auth/register-employee",
        json={
            "name": "Hopeful Admin",
            "email": "hopeful@example.com",
            "password": "hunter2hunter2",
            "role": "admin",
            "department_id": dept.dept_id,
        },
    )

    assert response.status_code == 422


def test_employee_registration_refuses_the_principal_role(client, factory):
    dept = factory.department()

    response = client.post(
        "/auth/register-employee",
        json={
            "name": "Hopeful Principal",
            "email": "hopeful@example.com",
            "password": "hunter2hunter2",
            "role": "principal",
            "department_id": dept.dept_id,
        },
    )

    assert response.status_code == 422


def test_employee_registration_rejects_a_duplicate_email(client, factory):
    factory.employee(email="taken@example.com")

    response = client.post(
        "/auth/register-employee",
        json={
            "name": "Impostor",
            "email": "taken@example.com",
            "password": "hunter2hunter2",
            "role": "faculty",
        },
    )

    assert response.status_code == 409


def test_me_reports_the_role_the_session_is_acting_as(client, factory, as_employee):
    """A multi-role employee acts as exactly one role per session, so /me must
    echo the token's active role rather than the full role set."""
    dept = factory.department()
    employee = factory.employee(
        roles=[EmployeeRole.faculty, EmployeeRole.hod, EmployeeRole.admin], department=dept
    )

    as_hod = client.get("/auth/me", headers=as_employee(employee, EmployeeRole.hod))
    as_admin = client.get("/auth/me", headers=as_employee(employee, EmployeeRole.admin))

    assert as_hod.json()["role"] == "hod"
    assert as_admin.json()["role"] == "admin"
    assert as_hod.json()["id"] == as_admin.json()["id"] == employee.emp_id
