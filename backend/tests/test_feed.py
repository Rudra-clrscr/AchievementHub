"""The public achievement feed.

This is the only unauthenticated read surface in the app, so the property that
matters most is negative: nothing that has not cleared both verification tiers
may ever appear here, whoever asks.
"""

import pytest

from app.models import CertificateStatus, EmployeeRole


@pytest.fixture
def dept(factory):
    return factory.department(name="Computer Science")


@pytest.fixture
def coordinator(factory, dept):
    return factory.employee(roles=[EmployeeRole.faculty], department=dept, name="Prof Faculty")


@pytest.fixture
def student(factory, dept, coordinator):
    return factory.student(department=dept, coordinator=coordinator, name="Ada Student")


def titles(response):
    return {item["title"] for item in response.json()}


@pytest.mark.parametrize(
    "status",
    [CertificateStatus.pending, CertificateStatus.verified, CertificateStatus.rejected],
)
def test_only_approved_records_are_published(client, factory, student, status):
    factory.achievement(student=student, title="Not Ready", status=status)

    assert client.get("/feed/latest").json() == []


def test_an_approved_record_is_published_with_its_owners_name(client, factory, student):
    factory.achievement(
        student=student,
        title="NPTEL Machine Learning",
        category="Certificate",
        status=CertificateStatus.approved,
    )

    response = client.get("/feed/latest")

    assert response.status_code == 200
    item = response.json()[0]
    assert item["title"] == "NPTEL Machine Learning"
    assert item["student_name"] == "Ada Student"
    assert item["owner_type"] == "student"
    assert item["type"] == "certificate"


def test_a_faculty_record_is_published_under_the_faculty_name(client, factory, coordinator):
    """`student_name` carries whichever owner the record belongs to; the field
    name is a leftover from before faculty achievements existed."""
    factory.achievement(
        employee=coordinator, title="FDP on Deep Learning", status=CertificateStatus.approved
    )

    item = client.get("/feed/latest").json()[0]

    assert item["owner_type"] == "employee"
    assert item["student_name"] == "Prof Faculty"


def test_the_feed_is_readable_without_a_token(client, factory, student):
    factory.achievement(student=student, title="Public", status=CertificateStatus.approved)

    response = client.get("/feed/latest")

    assert response.status_code == 200
    assert titles(response) == {"Public"}


def test_filtering_by_owner_type(client, factory, student, coordinator):
    factory.achievement(student=student, title="Student Work", status=CertificateStatus.approved)
    factory.achievement(
        employee=coordinator, title="Faculty Work", status=CertificateStatus.approved
    )

    students_only = client.get("/feed/latest", params={"owner_type": "student"})
    faculty_only = client.get("/feed/latest", params={"owner_type": "employee"})

    assert titles(students_only) == {"Student Work"}
    assert titles(faculty_only) == {"Faculty Work"}


def test_filtering_by_category(client, factory, student):
    factory.achievement(
        student=student, title="A Patent", category="Patent", status=CertificateStatus.approved
    )
    factory.achievement(
        student=student,
        title="A Certificate",
        category="Certificate",
        status=CertificateStatus.approved,
    )

    response = client.get("/feed/latest", params={"category": "patent"})

    assert titles(response) == {"A Patent"}


def test_searching_by_title(client, factory, student):
    factory.achievement(
        student=student, title="IEEE Paper on Robotics", status=CertificateStatus.approved
    )
    factory.achievement(
        student=student, title="Hackathon Winner", status=CertificateStatus.approved
    )

    response = client.get("/feed/latest", params={"search": "robotics"})

    assert titles(response) == {"IEEE Paper on Robotics"}


def test_search_does_not_leak_unapproved_records(client, factory, student):
    """Every filter narrows the approved set; none of them widens it."""
    factory.achievement(
        student=student, title="Secret Pending Award", status=CertificateStatus.pending
    )

    response = client.get("/feed/latest", params={"search": "Secret"})

    assert response.json() == []


def test_the_top_feed_holds_only_featured_records(client, factory, student):
    factory.achievement(
        student=student,
        title="Featured Work",
        status=CertificateStatus.approved,
        is_featured=True,
    )
    factory.achievement(
        student=student, title="Ordinary Work", status=CertificateStatus.approved
    )

    response = client.get("/feed/top")

    assert titles(response) == {"Featured Work"}


def test_the_top_feed_does_not_publish_unapproved_records(client, factory, student):
    factory.achievement(
        student=student,
        title="Featured But Pending",
        status=CertificateStatus.pending,
        is_featured=True,
    )

    assert client.get("/feed/top").json() == []


def test_multi_word_categories_become_url_safe_types(client, factory, student):
    factory.achievement(
        student=student,
        title="Conference Talk",
        category="Event Participation",
        status=CertificateStatus.approved,
    )

    assert client.get("/feed/latest").json()[0]["type"] == "event-participation"
