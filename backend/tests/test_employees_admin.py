"""Admin-only employee directory: HOD assignment and registration approval.

The headline here is the 2026-08-18 regression. The Department-Year-Section PR
put a "one HOD per department" guard inside `assign_hod`, which meant that the
moment a department held more than one HOD-role employee, assigning *any* HOD
to *any* faculty member was refused outright -- and the self-registration flow
had already created exactly that situation in production.

The fix moved the check to `approve_registration`, the point where a second HOD
can first come into existence. The general lesson, and the reason both halves
are pinned down below: enforce an invariant where it can first be violated, not
at every point that later reads the data.
"""

import pytest

from app.models import Employee, EmployeeRole


@pytest.fixture
def dept(factory):
    return factory.department(name="Computer Science")


@pytest.fixture
def admin(factory, dept):
    return factory.employee(roles=[EmployeeRole.admin], department=dept, name="Dept Admin")


@pytest.fixture
def hod(factory, dept):
    return factory.employee(roles=[EmployeeRole.hod], department=dept, name="First HOD")


@pytest.fixture
def faculty(factory, dept):
    return factory.employee(roles=[EmployeeRole.faculty], department=dept, name="Some Faculty")


# --------------------------------------------------------------------------
# The 08-18 regression
# --------------------------------------------------------------------------


def test_hod_assignment_works_in_a_department_that_holds_several_hods(
    client, factory, dept, admin, hod, faculty, as_employee
):
    """The exact regression: three HOD-role employees in one department used to
    make every assignment 403 with "A different HOD is already assigned to this
    department". Assignment must not care how many HODs exist."""
    factory.employee(roles=[EmployeeRole.hod], department=dept, name="Second HOD")
    factory.employee(roles=[EmployeeRole.hod], department=dept, name="Third HOD")

    response = client.patch(
        f"/employees/{faculty.emp_id}/hod",
        json={"hod_id": hod.emp_id},
        headers=as_employee(admin, EmployeeRole.admin),
    )

    assert response.status_code == 200, response.json()
    assert response.json()["hod_id"] == hod.emp_id
    assert response.json()["hod_name"] == "First HOD"


def test_every_hod_in_an_over_populated_department_can_receive_faculty(
    client, factory, dept, admin, hod, faculty, as_employee
):
    """Departments that were over-approved before the guard existed are left
    alone on purpose -- each of their HODs stays usable."""
    second_hod = factory.employee(roles=[EmployeeRole.hod], department=dept, name="Second HOD")
    other_faculty = factory.employee(roles=[EmployeeRole.faculty], department=dept)
    headers = as_employee(admin, EmployeeRole.admin)

    first = client.patch(
        f"/employees/{faculty.emp_id}/hod", json={"hod_id": hod.emp_id}, headers=headers
    )
    second = client.patch(
        f"/employees/{other_faculty.emp_id}/hod",
        json={"hod_id": second_hod.emp_id},
        headers=headers,
    )

    assert first.status_code == 200
    assert second.status_code == 200
    assert second.json()["hod_id"] == second_hod.emp_id


def test_approving_a_second_hod_for_a_department_is_refused(
    client, factory, dept, admin, hod, as_employee
):
    """The invariant still holds -- just at the point it can first be broken."""
    applicant = factory.employee(
        roles=[EmployeeRole.hod], department=dept, name="Would-be HOD", is_approved=False
    )

    response = client.patch(
        f"/employees/{applicant.emp_id}/approve",
        headers=as_employee(admin, EmployeeRole.admin),
    )

    assert response.status_code == 400
    assert "First HOD is already the approved HOD" in response.json()["detail"]


def test_approving_the_first_hod_for_a_department_succeeds(
    client, factory, dept, admin, as_employee
):
    applicant = factory.employee(
        roles=[EmployeeRole.hod], department=dept, name="New HOD", is_approved=False
    )

    response = client.patch(
        f"/employees/{applicant.emp_id}/approve",
        headers=as_employee(admin, EmployeeRole.admin),
    )

    assert response.status_code == 200
    assert response.json()["requested_role"] == "hod"


def test_an_unapproved_hod_does_not_block_another_applicant(
    client, factory, dept, admin, as_employee
):
    """Only approved HODs count against the limit; a queue of applicants must
    not deadlock itself."""
    factory.employee(roles=[EmployeeRole.hod], department=dept, is_approved=False)
    applicant = factory.employee(roles=[EmployeeRole.hod], department=dept, is_approved=False)

    response = client.patch(
        f"/employees/{applicant.emp_id}/approve",
        headers=as_employee(admin, EmployeeRole.admin),
    )

    assert response.status_code == 200


def test_the_hod_limit_does_not_apply_to_faculty_applicants(
    client, factory, dept, admin, hod, as_employee
):
    applicant = factory.employee(roles=[EmployeeRole.faculty], department=dept, is_approved=False)

    response = client.patch(
        f"/employees/{applicant.emp_id}/approve",
        headers=as_employee(admin, EmployeeRole.admin),
    )

    assert response.status_code == 200
    assert response.json()["requested_role"] == "faculty"


def test_the_hod_limit_is_skipped_for_an_applicant_with_no_department(
    client, factory, dept, admin, hod, as_employee
):
    """A department-scoped invariant cannot be evaluated without a department."""
    applicant = factory.employee(roles=[EmployeeRole.hod], department=None, is_approved=False)

    response = client.patch(
        f"/employees/{applicant.emp_id}/approve",
        headers=as_employee(admin, EmployeeRole.admin),
    )

    assert response.status_code == 200


def test_a_second_hod_in_a_different_department_is_unaffected(
    client, factory, admin, hod, as_employee
):
    other_dept = factory.department(name="Mechanical")
    applicant = factory.employee(
        roles=[EmployeeRole.hod], department=other_dept, is_approved=False
    )

    response = client.patch(
        f"/employees/{applicant.emp_id}/approve",
        headers=as_employee(admin, EmployeeRole.admin),
    )

    assert response.status_code == 404, "and it is out of this admin's scope anyway"


# --------------------------------------------------------------------------
# HOD assignment
# --------------------------------------------------------------------------


def test_assignment_pulls_the_faculty_into_the_admins_department(
    client, db_session, factory, dept, admin, hod, as_employee
):
    """Keeping department_id in sync matters because the admin branch of the
    faculty scope filter is department-based -- an unsynced faculty member
    would vanish from every admin queue the moment they got a HOD."""
    unattached = factory.employee(roles=[EmployeeRole.faculty], department=None)

    response = client.patch(
        f"/employees/{unattached.emp_id}/hod",
        json={"hod_id": hod.emp_id},
        headers=as_employee(admin, EmployeeRole.admin),
    )

    assert response.status_code == 200
    assert db_session.get(Employee, unattached.emp_id).department_id == dept.dept_id


def test_reassigning_a_faculty_member_to_a_different_hod(
    client, factory, dept, admin, hod, faculty, as_employee
):
    second_hod = factory.employee(roles=[EmployeeRole.hod], department=dept, name="Second HOD")
    headers = as_employee(admin, EmployeeRole.admin)

    client.patch(f"/employees/{faculty.emp_id}/hod", json={"hod_id": hod.emp_id}, headers=headers)
    response = client.patch(
        f"/employees/{faculty.emp_id}/hod", json={"hod_id": second_hod.emp_id}, headers=headers
    )

    assert response.status_code == 200
    assert response.json()["hod_id"] == second_hod.emp_id


def test_cannot_assign_a_hod_from_another_department(
    client, factory, admin, faculty, as_employee
):
    other_dept = factory.department(name="Mechanical")
    foreign_hod = factory.employee(roles=[EmployeeRole.hod], department=other_dept)

    response = client.patch(
        f"/employees/{faculty.emp_id}/hod",
        json={"hod_id": foreign_hod.emp_id},
        headers=as_employee(admin, EmployeeRole.admin),
    )

    assert response.status_code == 404
    assert "HOD not found in your department" in response.json()["detail"]


def test_cannot_assign_a_hod_to_someone_who_is_not_faculty(
    client, factory, dept, admin, hod, as_employee
):
    clerk = factory.employee(roles=[EmployeeRole.admin], department=dept)

    response = client.patch(
        f"/employees/{clerk.emp_id}/hod",
        json={"hod_id": hod.emp_id},
        headers=as_employee(admin, EmployeeRole.admin),
    )

    assert response.status_code == 404
    assert "Faculty member not found" in response.json()["detail"]


def test_cannot_name_a_non_hod_as_the_hod(client, factory, dept, admin, faculty, as_employee):
    plain_faculty = factory.employee(roles=[EmployeeRole.faculty], department=dept)

    response = client.patch(
        f"/employees/{faculty.emp_id}/hod",
        json={"hod_id": plain_faculty.emp_id},
        headers=as_employee(admin, EmployeeRole.admin),
    )

    assert response.status_code == 404


def test_cannot_assign_a_hod_to_faculty_in_another_department(
    client, factory, admin, hod, as_employee
):
    other_dept = factory.department(name="Mechanical")
    foreign_faculty = factory.employee(roles=[EmployeeRole.faculty], department=other_dept)

    response = client.patch(
        f"/employees/{foreign_faculty.emp_id}/hod",
        json={"hod_id": hod.emp_id},
        headers=as_employee(admin, EmployeeRole.admin),
    )

    assert response.status_code == 404


# --------------------------------------------------------------------------
# Listing and rejection
# --------------------------------------------------------------------------


def test_faculty_listing_is_scoped_and_resolves_hod_names(
    client, factory, dept, admin, hod, faculty, as_employee
):
    other_dept = factory.department(name="Mechanical")
    factory.employee(roles=[EmployeeRole.faculty], department=other_dept, name="Foreign Faculty")
    faculty.hod_id = hod.emp_id
    factory.session.commit()

    response = client.get("/employees/faculty", headers=as_employee(admin, EmployeeRole.admin))

    assert response.status_code == 200
    names = {row["name"]: row for row in response.json()}
    assert "Foreign Faculty" not in names
    assert names["Some Faculty"]["hod_name"] == "First HOD"


def test_hod_listing_is_scoped_to_the_admins_department(
    client, factory, dept, admin, hod, as_employee
):
    other_dept = factory.department(name="Mechanical")
    factory.employee(roles=[EmployeeRole.hod], department=other_dept, name="Foreign HOD")

    response = client.get("/employees/hods", headers=as_employee(admin, EmployeeRole.admin))

    assert [row["name"] for row in response.json()] == ["First HOD"]


def test_pending_listing_shows_only_unapproved_accounts(
    client, factory, dept, admin, faculty, as_employee
):
    applicant = factory.employee(
        roles=[EmployeeRole.faculty], department=dept, name="Applicant", is_approved=False
    )

    response = client.get("/employees/pending", headers=as_employee(admin, EmployeeRole.admin))

    assert [row["emp_id"] for row in response.json()] == [applicant.emp_id]
    assert response.json()[0]["department_name"] == "Computer Science"


def test_rejecting_a_registration_deletes_the_account(
    client, db_session, factory, dept, admin, as_employee
):
    applicant = factory.employee(roles=[EmployeeRole.faculty], department=dept, is_approved=False)

    response = client.delete(
        f"/employees/{applicant.emp_id}/reject",
        headers=as_employee(admin, EmployeeRole.admin),
    )

    assert response.status_code == 204
    assert db_session.get(Employee, applicant.emp_id) is None


def test_an_approved_account_cannot_be_rejected(client, factory, admin, faculty, as_employee):
    response = client.delete(
        f"/employees/{faculty.emp_id}/reject", headers=as_employee(admin, EmployeeRole.admin)
    )

    assert response.status_code == 404


def test_approval_is_what_unlocks_login(client, factory, dept, admin, as_employee):
    """End to end across the two routers: register -> blocked -> approve -> in."""
    client.post(
        "/auth/register-employee",
        json={
            "name": "Hopeful Faculty",
            "email": "hopeful@example.com",
            "password": "hunter2hunter2",
            "role": "faculty",
            "department_id": dept.dept_id,
        },
    )
    credentials = {"email": "hopeful@example.com", "password": "hunter2hunter2"}

    assert client.post("/auth/login", json=credentials).status_code == 403

    pending = client.get("/employees/pending", headers=as_employee(admin, EmployeeRole.admin))
    emp_id = pending.json()[0]["emp_id"]
    client.patch(f"/employees/{emp_id}/approve", headers=as_employee(admin, EmployeeRole.admin))

    accepted = client.post("/auth/login", json=credentials)
    assert accepted.status_code == 200
    assert accepted.json()["role"] == "faculty"


# --------------------------------------------------------------------------
# Admin-only gating
# --------------------------------------------------------------------------


ADMIN_ONLY_REQUESTS = [
    ("get", "/employees/faculty", None),
    ("get", "/employees/hods", None),
    ("get", "/employees/pending", None),
    ("patch", "/employees/1/hod", {"hod_id": 1}),
    ("patch", "/employees/1/approve", None),
    ("delete", "/employees/1/reject", None),
]


@pytest.mark.parametrize("method,path,body", ADMIN_ONLY_REQUESTS)
@pytest.mark.parametrize("role", [EmployeeRole.faculty, EmployeeRole.hod, EmployeeRole.principal])
def test_employee_directory_is_closed_to_every_non_admin_role(
    client, factory, dept, as_employee, method, path, body, role
):
    """Deciding who reviews whom is an admin action. A coordinator or HOD able
    to reassign their own reports could hand off the ones they would rather not
    review, which defeats the point of assignment."""
    employee = factory.employee(roles=[role], department=dept)

    response = getattr(client, method)(
        path, headers=as_employee(employee, role), **({"json": body} if body else {})
    )

    assert response.status_code == 403


@pytest.mark.parametrize("method,path,body", ADMIN_ONLY_REQUESTS)
def test_employee_directory_is_closed_to_students(
    client, factory, as_student, method, path, body
):
    student = factory.student()

    response = getattr(client, method)(
        path, headers=as_student(student), **({"json": body} if body else {})
    )

    assert response.status_code == 403
