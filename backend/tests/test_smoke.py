"""Harness sanity checks. If these fail, no other test result means anything."""

from app.models import CertificateStatus, EmployeeRole


def test_health_endpoint(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_factory_builds_a_full_object_graph(factory):
    dept = factory.department(name="Computer Science")
    hod = factory.employee(roles=[EmployeeRole.hod], department=dept)
    faculty = factory.employee(roles=[EmployeeRole.faculty], department=dept, hod=hod)
    section = factory.section(dept, section_name="A", year=2, coordinator=faculty)
    student = factory.student(department=dept, coordinator=faculty, section=section)
    record = factory.achievement(student=student)

    assert student.coordinator_id == faculty.emp_id
    assert student.year == 2
    assert faculty.hod_id == hod.emp_id
    assert record.status == CertificateStatus.pending
    assert record.owner_type.value == "student"


def test_each_test_starts_from_an_empty_database(client, factory):
    factory.department()
    assert len(client.get("/departments").json()) == 1


def test_previous_test_left_nothing_behind(client):
    assert client.get("/departments").json() == []
