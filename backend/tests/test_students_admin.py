"""Admin-only student directory and the Department-Year-Section hierarchy.

Coordinators are assigned per section rather than student-by-student, so
assigning a section coordinator has to cascade to everyone already sitting in
that section -- otherwise the students who registered before the assignment
keep pointing at nobody and drop out of every verification queue.
"""

import pytest

from app.models import EmployeeRole, Student


@pytest.fixture
def dept(factory):
    return factory.department(name="Computer Science")


@pytest.fixture
def admin(factory, dept):
    return factory.employee(roles=[EmployeeRole.admin], department=dept, name="Dept Admin")


@pytest.fixture
def coordinator(factory, dept):
    return factory.employee(roles=[EmployeeRole.faculty], department=dept, name="Coordinator One")


def test_student_listing_is_scoped_to_the_admins_department(
    client, factory, dept, admin, coordinator, as_employee
):
    other_dept = factory.department(name="Mechanical")
    section = factory.section(dept, section_name="A", year=2, coordinator=coordinator)
    mine = factory.student(
        department=dept, coordinator=coordinator, section=section, name="Ours"
    )
    factory.student(department=other_dept, name="Theirs")

    response = client.get("/students", headers=as_employee(admin, EmployeeRole.admin))

    assert response.status_code == 200
    rows = response.json()
    assert [row["name"] for row in rows] == ["Ours"]
    assert rows[0]["student_id"] == mine.student_id
    assert rows[0]["section_name"] == "A"
    assert rows[0]["year"] == 2
    assert rows[0]["coordinator_name"] == "Coordinator One"


def test_students_with_no_department_are_visible_to_every_admin(
    client, factory, admin, as_employee
):
    """Unattached registrations must not become invisible to everyone."""
    factory.student(department=None, name="Unattached")

    response = client.get("/students", headers=as_employee(admin, EmployeeRole.admin))

    assert [row["name"] for row in response.json()] == ["Unattached"]


def test_coordinator_listing_returns_department_faculty_only(
    client, factory, dept, admin, coordinator, as_employee
):
    other_dept = factory.department(name="Mechanical")
    factory.employee(roles=[EmployeeRole.faculty], department=other_dept, name="Foreign Faculty")
    factory.employee(roles=[EmployeeRole.hod], department=dept, name="A HOD")

    response = client.get("/students/coordinators", headers=as_employee(admin, EmployeeRole.admin))

    assert [row["name"] for row in response.json()] == ["Coordinator One"]


def test_assigning_a_coordinator_to_one_student(
    client, db_session, factory, dept, admin, coordinator, as_employee
):
    student = factory.student(department=dept)

    response = client.patch(
        f"/students/{student.student_id}/coordinator",
        json={"coordinator_id": coordinator.emp_id},
        headers=as_employee(admin, EmployeeRole.admin),
    )

    assert response.status_code == 200
    assert response.json()["coordinator_name"] == "Coordinator One"
    assert db_session.get(Student, student.student_id).coordinator_id == coordinator.emp_id


def test_cannot_assign_a_coordinator_from_another_department(
    client, factory, dept, admin, as_employee
):
    other_dept = factory.department(name="Mechanical")
    foreign = factory.employee(roles=[EmployeeRole.faculty], department=other_dept)
    student = factory.student(department=dept)

    response = client.patch(
        f"/students/{student.student_id}/coordinator",
        json={"coordinator_id": foreign.emp_id},
        headers=as_employee(admin, EmployeeRole.admin),
    )

    assert response.status_code == 404
    assert "Coordinator not found in your department" in response.json()["detail"]


def test_cannot_assign_a_coordinator_to_a_student_in_another_department(
    client, factory, dept, admin, coordinator, as_employee
):
    other_dept = factory.department(name="Mechanical")
    foreign_student = factory.student(department=other_dept)

    response = client.patch(
        f"/students/{foreign_student.student_id}/coordinator",
        json={"coordinator_id": coordinator.emp_id},
        headers=as_employee(admin, EmployeeRole.admin),
    )

    assert response.status_code == 404


def test_assigning_a_section_coordinator_cascades_to_its_students(
    client, db_session, factory, dept, admin, coordinator, as_employee
):
    section = factory.section(dept, section_name="A", year=2)
    early_bird = factory.student(department=dept, section=section)
    also_enrolled = factory.student(department=dept, section=section)
    other_section = factory.section(dept, section_name="B", year=2)
    elsewhere = factory.student(department=dept, section=other_section)

    response = client.patch(
        f"/students/sections/{section.section_id}/coordinator",
        json={"coordinator_id": coordinator.emp_id},
        headers=as_employee(admin, EmployeeRole.admin),
    )

    assert response.status_code == 200
    assert response.json()["coordinator_id"] == coordinator.emp_id

    db_session.expire_all()
    assert db_session.get(Student, early_bird.student_id).coordinator_id == coordinator.emp_id
    assert db_session.get(Student, also_enrolled.student_id).coordinator_id == coordinator.emp_id
    assert db_session.get(Student, elsewhere.student_id).coordinator_id is None


def test_a_student_joining_later_inherits_the_section_coordinator(
    client, db_session, factory, dept, admin, coordinator, as_employee
):
    """The cascade covers students who already exist; registration covers the
    ones who arrive afterwards. Both halves are needed for the section to be
    the single source of truth."""
    section = factory.section(dept, section_name="A", year=2)
    client.patch(
        f"/students/sections/{section.section_id}/coordinator",
        json={"coordinator_id": coordinator.emp_id},
        headers=as_employee(admin, EmployeeRole.admin),
    )

    client.post(
        "/auth/register",
        json={
            "name": "Late Joiner",
            "email": "late@example.com",
            "password": "hunter2hunter2",
            "student_type": "inhouse",
            "section_id": section.section_id,
        },
    )

    joined = db_session.query(Student).filter(Student.email == "late@example.com").one()
    assert joined.coordinator_id == coordinator.emp_id


def test_cannot_assign_a_coordinator_to_a_section_in_another_department(
    client, factory, admin, coordinator, as_employee
):
    other_dept = factory.department(name="Mechanical")
    foreign_section = factory.section(other_dept, section_name="A", year=1)

    response = client.patch(
        f"/students/sections/{foreign_section.section_id}/coordinator",
        json={"coordinator_id": coordinator.emp_id},
        headers=as_employee(admin, EmployeeRole.admin),
    )

    assert response.status_code == 404
    assert "Section not found in your department" in response.json()["detail"]


def test_sections_are_listed_publicly_for_the_registration_form(client, factory, dept):
    """Registration happens before login, so the section picker must be open."""
    factory.section(dept, section_name="A", year=1)
    factory.section(dept, section_name="B", year=1)
    factory.section(dept, section_name="A", year=3)

    all_sections = client.get(f"/departments/{dept.dept_id}/sections")
    year_one = client.get(f"/departments/{dept.dept_id}/sections", params={"year": 1})

    assert all_sections.status_code == 200
    assert len(all_sections.json()) == 3
    assert {row["section_name"] for row in year_one.json()} == {"A", "B"}
    assert all(row["year"] == 1 for row in year_one.json())


@pytest.mark.parametrize(
    "method,path,body",
    [
        ("get", "/students", None),
        ("get", "/students/coordinators", None),
        ("patch", "/students/1/coordinator", {"coordinator_id": 1}),
        ("patch", "/students/sections/1/coordinator", {"coordinator_id": 1}),
    ],
)
@pytest.mark.parametrize("role", [EmployeeRole.faculty, EmployeeRole.hod, EmployeeRole.principal])
def test_student_directory_is_closed_to_every_non_admin_role(
    client, factory, dept, as_employee, method, path, body, role
):
    employee = factory.employee(roles=[role], department=dept)

    response = getattr(client, method)(
        path, headers=as_employee(employee, role), **({"json": body} if body else {})
    )

    assert response.status_code == 403
