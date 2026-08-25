"""The submit -> pending -> verified -> approved pipeline.

This is the workflow the whole product exists to run, and it is where the
role model actually bites. Two things are easy to break and expensive to
notice in production:

* **Scope.** A faculty coordinator sees only their own students; a HOD sees
  only the faculty assigned to them; an admin sees their whole department.
  Widening any of these silently hands someone review power over records
  they were never meant to see.
* **Tier.** Faculty and HOD move `pending -> verified`. Admin moves
  `verified -> approved`. Neither tier may skip or repeat the other's step,
  because `approved` is what publishes a record to the public feed and to
  accreditation dumps.
"""

import pytest

from app.models import Achievement, CertificateStatus, EmployeeRole


@pytest.fixture
def dept(factory):
    return factory.department(name="Computer Science")


@pytest.fixture
def hod(factory, dept):
    return factory.employee(roles=[EmployeeRole.hod], department=dept, name="Dept Head")


@pytest.fixture
def admin(factory, dept):
    return factory.employee(roles=[EmployeeRole.admin], department=dept, name="Dept Admin")


@pytest.fixture
def coordinator(factory, dept, hod):
    return factory.employee(
        roles=[EmployeeRole.faculty], department=dept, hod=hod, name="Section Coordinator"
    )


@pytest.fixture
def student(factory, dept, coordinator):
    return factory.student(department=dept, coordinator=coordinator, name="Assigned Student")


def submit(client, headers, **overrides):
    body = {
        "title": "NPTEL Machine Learning",
        "category": "Certificate",
        "file_url": "https://files.example.com/nptel.pdf",
    }
    body.update(overrides)
    return client.post("/achievements", json=body, headers=headers)


def ids(response):
    return {item["id"] for item in response.json()}


# --------------------------------------------------------------------------
# Submission
# --------------------------------------------------------------------------


def test_student_submission_lands_as_pending_and_student_owned(client, student, as_student):
    response = submit(client, as_student(student), sub_category="NPTEL")

    assert response.status_code == 201
    body = response.json()
    assert body["status"] == "pending"
    assert body["owner_type"] == "student"
    assert body["student_id"] == student.student_id
    assert body["employee_id"] is None
    assert body["verified_by"] is None
    assert body["verified_at"] is None
    assert body["sub_category"] == "NPTEL"


def test_faculty_submission_lands_as_pending_and_employee_owned(
    client, coordinator, as_employee
):
    response = submit(client, as_employee(coordinator, EmployeeRole.faculty), title="FDP on AI")

    assert response.status_code == 201
    body = response.json()
    assert body["status"] == "pending"
    assert body["owner_type"] == "employee"
    assert body["employee_id"] == coordinator.emp_id
    assert body["student_id"] is None


def test_submission_status_cannot_be_forged_by_the_client(client, student, as_student):
    """`status` is not part of AchievementCreate, so a client that sends it
    must not be able to publish straight to the feed."""
    response = client.post(
        "/achievements",
        json={
            "title": "Self-approved",
            "category": "Certificate",
            "file_url": "https://files.example.com/x.pdf",
            "status": "approved",
        },
        headers=as_student(student),
    )

    assert response.status_code == 201
    assert response.json()["status"] == "pending"


def test_submission_without_a_file_is_refused(client, student, as_student):
    response = submit(client, as_student(student), file_url="   ")

    assert response.status_code == 422
    assert response.json()["detail"] == "file_url is required"


def test_submission_requires_authentication(client, student):
    response = submit(client, headers={})

    assert response.status_code == 401


def test_metadata_fields_round_trip(client, student, as_student):
    response = submit(
        client,
        as_student(student),
        category="Patent",
        metadata_fields={"patent_number": "IN123456", "grant_amount": 5000},
    )

    assert response.status_code == 201
    assert response.json()["metadata_fields"] == {
        "patent_number": "IN123456",
        "grant_amount": 5000,
    }


# --------------------------------------------------------------------------
# /achievements/mine
# --------------------------------------------------------------------------


def test_mine_lists_only_the_callers_own_records(
    client, factory, dept, coordinator, student, as_student
):
    other_student = factory.student(department=dept, coordinator=coordinator)
    mine = factory.achievement(student=student)
    factory.achievement(student=other_student)

    response = client.get("/achievements/mine", headers=as_student(student))

    assert response.status_code == 200
    assert ids(response) == {mine.id}


def test_mine_for_an_employee_lists_their_own_submissions_not_their_students(
    client, factory, coordinator, student, as_employee
):
    own = factory.achievement(employee=coordinator)
    factory.achievement(student=student)

    response = client.get(
        "/achievements/mine", headers=as_employee(coordinator, EmployeeRole.faculty)
    )

    assert ids(response) == {own.id}


def test_mine_shows_records_at_every_status(client, factory, student, as_student):
    pending = factory.achievement(student=student, status=CertificateStatus.pending)
    verified = factory.achievement(student=student, status=CertificateStatus.verified)
    approved = factory.achievement(student=student, status=CertificateStatus.approved)
    rejected = factory.achievement(student=student, status=CertificateStatus.rejected)

    response = client.get("/achievements/mine", headers=as_student(student))

    assert ids(response) == {pending.id, verified.id, approved.id, rejected.id}


# --------------------------------------------------------------------------
# /achievements/pending -- scope
# --------------------------------------------------------------------------


def test_faculty_queue_holds_only_their_own_students_pending_records(
    client, factory, dept, hod, coordinator, student, as_employee
):
    other_coordinator = factory.employee(roles=[EmployeeRole.faculty], department=dept, hod=hod)
    other_student = factory.student(department=dept, coordinator=other_coordinator)

    mine = factory.achievement(student=student)
    factory.achievement(student=other_student)

    response = client.get(
        "/achievements/pending", headers=as_employee(coordinator, EmployeeRole.faculty)
    )

    assert response.status_code == 200
    assert ids(response) == {mine.id}


def test_faculty_queue_excludes_records_already_reviewed(
    client, factory, coordinator, student, as_employee
):
    pending = factory.achievement(student=student, status=CertificateStatus.pending)
    factory.achievement(student=student, status=CertificateStatus.verified)
    factory.achievement(student=student, status=CertificateStatus.approved)
    factory.achievement(student=student, status=CertificateStatus.rejected)

    response = client.get(
        "/achievements/pending", headers=as_employee(coordinator, EmployeeRole.faculty)
    )

    assert ids(response) == {pending.id}


def test_faculty_cannot_see_faculty_authored_records(
    client, factory, coordinator, as_employee
):
    """Faculty verify students, not peers -- reviewing your own tier would let
    two coordinators verify each other."""
    factory.achievement(employee=coordinator)

    response = client.get(
        "/achievements/pending", headers=as_employee(coordinator, EmployeeRole.faculty)
    )

    assert ids(response) == set()


def test_hod_queue_holds_pending_records_of_their_assigned_faculty(
    client, factory, dept, hod, coordinator, as_employee
):
    other_hod = factory.employee(roles=[EmployeeRole.hod], department=dept)
    unassigned_faculty = factory.employee(
        roles=[EmployeeRole.faculty], department=dept, hod=other_hod
    )

    mine = factory.achievement(employee=coordinator)
    factory.achievement(employee=unassigned_faculty)

    response = client.get("/achievements/pending", headers=as_employee(hod, EmployeeRole.hod))

    assert response.status_code == 200
    assert ids(response) == {mine.id}


def test_hod_queue_does_not_include_student_records(
    client, factory, hod, student, as_employee
):
    factory.achievement(student=student)

    response = client.get("/achievements/pending", headers=as_employee(hod, EmployeeRole.hod))

    assert ids(response) == set()


def test_admin_queue_holds_verified_records_not_pending_ones(
    client, factory, admin, student, as_employee
):
    """Admin is the second tier: their queue is what faculty already passed,
    not raw submissions."""
    verified = factory.achievement(student=student, status=CertificateStatus.verified)
    factory.achievement(student=student, status=CertificateStatus.pending)

    response = client.get("/achievements/pending", headers=as_employee(admin, EmployeeRole.admin))

    assert response.status_code == 200
    assert ids(response) == {verified.id}


def test_admin_queue_spans_students_and_faculty_of_their_department(
    client, factory, dept, admin, coordinator, student, as_employee
):
    student_record = factory.achievement(student=student, status=CertificateStatus.verified)
    faculty_record = factory.achievement(employee=coordinator, status=CertificateStatus.verified)

    response = client.get("/achievements/pending", headers=as_employee(admin, EmployeeRole.admin))

    assert ids(response) == {student_record.id, faculty_record.id}


def test_admin_queue_stops_at_the_department_boundary(
    client, factory, admin, student, as_employee
):
    other_dept = factory.department(name="Mechanical")
    other_coordinator = factory.employee(roles=[EmployeeRole.faculty], department=other_dept)
    other_student = factory.student(department=other_dept, coordinator=other_coordinator)

    mine = factory.achievement(student=student, status=CertificateStatus.verified)
    factory.achievement(student=other_student, status=CertificateStatus.verified)
    factory.achievement(employee=other_coordinator, status=CertificateStatus.verified)

    response = client.get("/achievements/pending", headers=as_employee(admin, EmployeeRole.admin))

    assert ids(response) == {mine.id}


def test_students_cannot_open_a_verification_queue(client, student, as_student):
    response = client.get("/achievements/pending", headers=as_student(student))

    assert response.status_code == 403


def test_principal_has_no_verification_scope(client, factory, dept, student, as_employee):
    """Principal is a monitoring role, not a verification one; the scope
    filters deliberately fall through to matching nothing."""
    principal = factory.employee(roles=[EmployeeRole.principal], department=dept)
    factory.achievement(student=student)

    response = client.get(
        "/achievements/pending", headers=as_employee(principal, EmployeeRole.principal)
    )

    assert response.status_code == 403


# --------------------------------------------------------------------------
# Verification -- tier transitions
# --------------------------------------------------------------------------


def test_faculty_moves_a_student_record_from_pending_to_verified(
    client, factory, coordinator, student, as_employee
):
    record = factory.achievement(student=student, status=CertificateStatus.pending)

    response = client.patch(
        f"/achievements/{record.id}/verify",
        json={"approve": True},
        headers=as_employee(coordinator, EmployeeRole.faculty),
    )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "verified"
    assert body["verified_by"] == coordinator.emp_id
    assert body["verified_at"] is not None


def test_admin_moves_a_verified_record_to_approved(
    client, factory, admin, student, as_employee
):
    record = factory.achievement(student=student, status=CertificateStatus.verified)

    response = client.patch(
        f"/achievements/{record.id}/verify",
        json={"approve": True},
        headers=as_employee(admin, EmployeeRole.admin),
    )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "approved"
    assert body["approved_by"] == admin.emp_id
    assert body["approved_at"] is not None


def test_approval_does_not_overwrite_the_coordinators_signature(
    client, coordinator, admin, student, as_student, as_employee
):
    """Both tiers used to write verified_by, so approving erased whoever did
    tier one -- and with it any chance of showing a coordinator what they had
    reviewed. The two signatures are now separate and both survive."""
    record_id = submit(client, as_student(student)).json()["id"]

    client.patch(
        f"/achievements/{record_id}/verify",
        json={"approve": True},
        headers=as_employee(coordinator, EmployeeRole.faculty),
    )
    approved = client.patch(
        f"/achievements/{record_id}/verify",
        json={"approve": True},
        headers=as_employee(admin, EmployeeRole.admin),
    ).json()

    assert approved["verified_by"] == coordinator.emp_id, "tier 1 signature was erased"
    assert approved["approved_by"] == admin.emp_id
    assert approved["verified_at"] is not None
    assert approved["approved_at"] is not None


def test_tier_one_does_not_fill_in_the_approval_signature(
    client, coordinator, student, as_student, as_employee
):
    record_id = submit(client, as_student(student)).json()["id"]

    verified = client.patch(
        f"/achievements/{record_id}/verify",
        json={"approve": True},
        headers=as_employee(coordinator, EmployeeRole.faculty),
    ).json()

    assert verified["verified_by"] == coordinator.emp_id
    assert verified["approved_by"] is None
    assert verified["approved_at"] is None


def test_admin_cannot_approve_a_record_faculty_has_not_seen(
    client, factory, admin, student, as_employee
):
    """Skipping tier one would defeat the point of having two."""
    record = factory.achievement(student=student, status=CertificateStatus.pending)

    response = client.patch(
        f"/achievements/{record.id}/verify",
        json={"approve": True},
        headers=as_employee(admin, EmployeeRole.admin),
    )

    assert response.status_code == 422
    assert "already verified" in response.json()["detail"]


def test_faculty_cannot_re_review_a_record_they_already_verified(
    client, factory, coordinator, student, as_employee
):
    record = factory.achievement(student=student, status=CertificateStatus.verified)

    response = client.patch(
        f"/achievements/{record.id}/verify",
        json={"approve": True},
        headers=as_employee(coordinator, EmployeeRole.faculty),
    )

    assert response.status_code == 422
    assert "already been reviewed" in response.json()["detail"]


def test_faculty_rejection_marks_the_record_rejected(
    client, factory, coordinator, student, as_employee
):
    record = factory.achievement(student=student, status=CertificateStatus.pending)

    response = client.patch(
        f"/achievements/{record.id}/verify",
        json={"approve": False, "remarks": "Certificate is illegible"},
        headers=as_employee(coordinator, EmployeeRole.faculty),
    )

    assert response.status_code == 200
    assert response.json()["status"] == "rejected"


def test_admin_rejection_marks_the_record_rejected(
    client, factory, admin, student, as_employee
):
    record = factory.achievement(student=student, status=CertificateStatus.verified)

    response = client.patch(
        f"/achievements/{record.id}/verify",
        json={"approve": False},
        headers=as_employee(admin, EmployeeRole.admin),
    )

    assert response.json()["status"] == "rejected"


def test_remarks_are_stored_without_discarding_existing_metadata(
    client, factory, coordinator, student, as_employee
):
    record = factory.achievement(
        student=student, metadata_fields={"patent_number": "IN123456"}
    )

    response = client.patch(
        f"/achievements/{record.id}/verify",
        json={"approve": False, "remarks": "Wrong document attached"},
        headers=as_employee(coordinator, EmployeeRole.faculty),
    )

    assert response.json()["metadata_fields"] == {
        "patent_number": "IN123456",
        "remarks": "Wrong document attached",
    }


def test_remarks_are_stored_on_a_record_that_had_no_metadata(
    client, factory, coordinator, student, as_employee
):
    """The companion to the test above. This path worked even while the other
    was silently dropping remarks, which is exactly why the bug survived: the
    plain-certificate case is the one anyone would try by hand."""
    record = factory.achievement(student=student, metadata_fields=None)

    response = client.patch(
        f"/achievements/{record.id}/verify",
        json={"approve": False, "remarks": "Blurry scan"},
        headers=as_employee(coordinator, EmployeeRole.faculty),
    )

    assert response.json()["metadata_fields"] == {"remarks": "Blurry scan"}


def test_verifying_without_remarks_leaves_metadata_untouched(
    client, factory, coordinator, student, as_employee
):
    record = factory.achievement(student=student, metadata_fields={"patent_number": "IN123456"})

    response = client.patch(
        f"/achievements/{record.id}/verify",
        json={"approve": True},
        headers=as_employee(coordinator, EmployeeRole.faculty),
    )

    assert response.json()["metadata_fields"] == {"patent_number": "IN123456"}


def test_a_record_without_a_usable_file_cannot_be_approved(
    client, factory, coordinator, student, as_employee
):
    """Charter guardrail: never move a record forward without proof attached."""
    record = factory.achievement(student=student, file_url="   ")

    response = client.patch(
        f"/achievements/{record.id}/verify",
        json={"approve": True},
        headers=as_employee(coordinator, EmployeeRole.faculty),
    )

    assert response.status_code == 422
    assert "without a verified file_url" in response.json()["detail"]


def test_a_record_without_a_usable_file_can_still_be_rejected(
    client, factory, coordinator, student, as_employee
):
    record = factory.achievement(student=student, file_url="   ")

    response = client.patch(
        f"/achievements/{record.id}/verify",
        json={"approve": False},
        headers=as_employee(coordinator, EmployeeRole.faculty),
    )

    assert response.status_code == 200
    assert response.json()["status"] == "rejected"


# --------------------------------------------------------------------------
# Verification -- scope enforcement
# --------------------------------------------------------------------------


def test_faculty_cannot_verify_another_coordinators_student(
    client, factory, dept, hod, coordinator, as_employee
):
    other_coordinator = factory.employee(roles=[EmployeeRole.faculty], department=dept, hod=hod)
    other_student = factory.student(department=dept, coordinator=other_coordinator)
    record = factory.achievement(student=other_student)

    response = client.patch(
        f"/achievements/{record.id}/verify",
        json={"approve": True},
        headers=as_employee(coordinator, EmployeeRole.faculty),
    )

    assert response.status_code == 404
    assert "access denied" in response.json()["detail"]


def test_hod_cannot_verify_faculty_assigned_to_another_hod(
    client, factory, dept, hod, as_employee
):
    other_hod = factory.employee(roles=[EmployeeRole.hod], department=dept)
    other_faculty = factory.employee(roles=[EmployeeRole.faculty], department=dept, hod=other_hod)
    record = factory.achievement(employee=other_faculty)

    response = client.patch(
        f"/achievements/{record.id}/verify",
        json={"approve": True},
        headers=as_employee(hod, EmployeeRole.hod),
    )

    assert response.status_code == 404


def test_admin_cannot_verify_outside_their_department(client, factory, admin, as_employee):
    other_dept = factory.department(name="Mechanical")
    other_coordinator = factory.employee(roles=[EmployeeRole.faculty], department=other_dept)
    other_student = factory.student(department=other_dept, coordinator=other_coordinator)
    record = factory.achievement(student=other_student, status=CertificateStatus.verified)

    response = client.patch(
        f"/achievements/{record.id}/verify",
        json={"approve": True},
        headers=as_employee(admin, EmployeeRole.admin),
    )

    assert response.status_code == 404


def test_students_cannot_verify_anything(client, factory, student, as_student):
    record = factory.achievement(student=student)

    response = client.patch(
        f"/achievements/{record.id}/verify",
        json={"approve": True},
        headers=as_student(student),
    )

    assert response.status_code == 403


def test_verifying_a_record_that_does_not_exist_is_a_404(
    client, coordinator, as_employee
):
    response = client.patch(
        "/achievements/99999/verify",
        json={"approve": True},
        headers=as_employee(coordinator, EmployeeRole.faculty),
    )

    assert response.status_code == 404


def test_a_multi_role_employee_is_bound_by_the_role_they_logged_in_as(
    client, factory, dept, student, as_employee
):
    """Holding both roles must not collapse the two tiers: acting as admin on
    a pending record is refused even though the same person could verify it
    as faculty."""
    both = factory.employee(roles=[EmployeeRole.faculty, EmployeeRole.admin], department=dept)
    student.coordinator_id = both.emp_id
    factory.session.commit()
    record = factory.achievement(student=student, status=CertificateStatus.pending)

    as_admin = client.patch(
        f"/achievements/{record.id}/verify",
        json={"approve": True},
        headers=as_employee(both, EmployeeRole.admin),
    )
    assert as_admin.status_code == 422

    as_faculty = client.patch(
        f"/achievements/{record.id}/verify",
        json={"approve": True},
        headers=as_employee(both, EmployeeRole.faculty),
    )
    assert as_faculty.status_code == 200
    assert as_faculty.json()["status"] == "verified"


# --------------------------------------------------------------------------
# End to end
# --------------------------------------------------------------------------


def test_full_pipeline_submission_to_public_feed(
    client, db_session, coordinator, admin, student, as_student, as_employee
):
    """The one test that ties the product together: nothing reaches the public
    feed until both tiers have passed it."""
    submission = submit(client, as_student(student), title="IEEE Paper Presentation")
    record_id = submission.json()["id"]

    assert client.get("/feed/latest").json() == []

    faculty_queue = client.get(
        "/achievements/pending", headers=as_employee(coordinator, EmployeeRole.faculty)
    )
    assert ids(faculty_queue) == {record_id}

    client.patch(
        f"/achievements/{record_id}/verify",
        json={"approve": True},
        headers=as_employee(coordinator, EmployeeRole.faculty),
    )
    assert client.get("/feed/latest").json() == [], "verified is not yet public"

    admin_queue = client.get(
        "/achievements/pending", headers=as_employee(admin, EmployeeRole.admin)
    )
    assert ids(admin_queue) == {record_id}

    client.patch(
        f"/achievements/{record_id}/verify",
        json={"approve": True},
        headers=as_employee(admin, EmployeeRole.admin),
    )

    feed = client.get("/feed/latest")
    assert feed.status_code == 200
    assert [item["title"] for item in feed.json()] == ["IEEE Paper Presentation"]
    assert feed.json()[0]["student_name"] == student.name

    final = db_session.get(Achievement, record_id)
    assert final.status == CertificateStatus.approved
    assert final.verified_by == coordinator.emp_id
    assert final.approved_by == admin.emp_id


def test_a_rejected_record_never_reaches_the_feed(
    client, coordinator, student, as_student, as_employee
):
    record_id = submit(client, as_student(student)).json()["id"]

    client.patch(
        f"/achievements/{record_id}/verify",
        json={"approve": False, "remarks": "Not a recognised certificate"},
        headers=as_employee(coordinator, EmployeeRole.faculty),
    )

    assert client.get("/feed/latest").json() == []


# --------------------------------------------------------------------------
# /achievements/reviewed -- a verifier's own history
# --------------------------------------------------------------------------


def review(client, record_id, headers, approve=True, remarks=None):
    body = {"approve": approve}
    if remarks is not None:
        body["remarks"] = remarks
    return client.patch(f"/achievements/{record_id}/verify", json=body, headers=headers)


def test_a_coordinator_sees_what_they_verified(
    client, coordinator, student, as_student, as_employee
):
    record_id = submit(client, as_student(student), title="NPTEL Course").json()["id"]
    review(client, record_id, as_employee(coordinator, EmployeeRole.faculty))

    response = client.get(
        "/achievements/reviewed", headers=as_employee(coordinator, EmployeeRole.faculty)
    )

    assert response.status_code == 200
    assert ids(response) == {record_id}
    assert response.json()[0]["owner_name"] == student.name
    assert response.json()[0]["title"] == "NPTEL Course"


def test_history_survives_the_record_being_approved_by_an_admin(
    client, coordinator, admin, student, as_student, as_employee
):
    """The whole point of splitting the two signatures: a coordinator's history
    must not empty out as records complete the pipeline."""
    record_id = submit(client, as_student(student)).json()["id"]
    review(client, record_id, as_employee(coordinator, EmployeeRole.faculty))
    review(client, record_id, as_employee(admin, EmployeeRole.admin))

    coordinator_history = client.get(
        "/achievements/reviewed", headers=as_employee(coordinator, EmployeeRole.faculty)
    )
    admin_history = client.get(
        "/achievements/reviewed", headers=as_employee(admin, EmployeeRole.admin)
    )

    assert ids(coordinator_history) == {record_id}
    assert ids(admin_history) == {record_id}
    assert coordinator_history.json()[0]["status"] == "approved"


def test_an_admin_sees_what_they_approved_not_what_they_merely_could_have(
    client, factory, coordinator, admin, student, as_student, as_employee
):
    acted_on = submit(client, as_student(student)).json()["id"]
    review(client, acted_on, as_employee(coordinator, EmployeeRole.faculty))
    review(client, acted_on, as_employee(admin, EmployeeRole.admin))

    # Verified and sitting in this admin's queue, but never actioned by them.
    factory.achievement(student=student, status=CertificateStatus.verified)

    response = client.get("/achievements/reviewed", headers=as_employee(admin, EmployeeRole.admin))

    assert ids(response) == {acted_on}


def test_a_hod_sees_the_faculty_records_they_verified(
    client, factory, dept, hod, coordinator, as_employee
):
    record = factory.achievement(employee=coordinator, title="FDP on AI")
    review(client, record.id, as_employee(hod, EmployeeRole.hod))

    response = client.get("/achievements/reviewed", headers=as_employee(hod, EmployeeRole.hod))

    assert ids(response) == {record.id}
    assert response.json()[0]["owner_name"] == coordinator.name


def test_one_verifier_does_not_see_the_history_of_another(
    client, factory, dept, hod, coordinator, student, as_student, as_employee
):
    other_coordinator = factory.employee(roles=[EmployeeRole.faculty], department=dept, hod=hod)
    other_student = factory.student(department=dept, coordinator=other_coordinator)

    mine = submit(client, as_student(student)).json()["id"]
    review(client, mine, as_employee(coordinator, EmployeeRole.faculty))

    theirs = factory.achievement(student=other_student)
    review(client, theirs.id, as_employee(other_coordinator, EmployeeRole.faculty))

    response = client.get(
        "/achievements/reviewed", headers=as_employee(coordinator, EmployeeRole.faculty)
    )

    assert ids(response) == {mine}


def test_rejections_appear_in_history_with_their_remarks(
    client, coordinator, student, as_student, as_employee
):
    record_id = submit(client, as_student(student)).json()["id"]
    review(
        client,
        record_id,
        as_employee(coordinator, EmployeeRole.faculty),
        approve=False,
        remarks="Certificate is illegible",
    )

    response = client.get(
        "/achievements/reviewed", headers=as_employee(coordinator, EmployeeRole.faculty)
    )

    assert ids(response) == {record_id}
    entry = response.json()[0]
    assert entry["status"] == "rejected"
    assert entry["metadata_fields"]["remarks"] == "Certificate is illegible"


def test_history_can_be_filtered_by_status(
    client, factory, coordinator, admin, student, as_student, as_employee
):
    approved_id = submit(client, as_student(student), title="Approved one").json()["id"]
    review(client, approved_id, as_employee(coordinator, EmployeeRole.faculty))
    review(client, approved_id, as_employee(admin, EmployeeRole.admin))

    rejected_id = submit(client, as_student(student), title="Rejected one").json()["id"]
    review(client, rejected_id, as_employee(coordinator, EmployeeRole.faculty), approve=False)

    still_verified_id = submit(client, as_student(student), title="Awaiting admin").json()["id"]
    review(client, still_verified_id, as_employee(coordinator, EmployeeRole.faculty))

    headers = as_employee(coordinator, EmployeeRole.faculty)
    assert ids(client.get("/achievements/reviewed", headers=headers)) == {
        approved_id,
        rejected_id,
        still_verified_id,
    }
    assert ids(
        client.get("/achievements/reviewed", params={"status": "approved"}, headers=headers)
    ) == {approved_id}
    assert ids(
        client.get("/achievements/reviewed", params={"status": "rejected"}, headers=headers)
    ) == {rejected_id}


def test_an_unknown_status_filter_is_rejected(client, coordinator, as_employee):
    response = client.get(
        "/achievements/reviewed",
        params={"status": "banana"},
        headers=as_employee(coordinator, EmployeeRole.faculty),
    )

    assert response.status_code == 422


def test_history_is_empty_before_anything_is_reviewed(
    client, factory, coordinator, student, as_employee
):
    factory.achievement(student=student)

    response = client.get(
        "/achievements/reviewed", headers=as_employee(coordinator, EmployeeRole.faculty)
    )

    assert response.json() == []


def test_history_keeps_records_whose_student_was_reassigned(
    client, factory, dept, hod, coordinator, student, as_student, as_employee, db_session
):
    """Scope answers "what may I review now?" and legitimately changes.
    History should not rewrite itself when a student moves to another
    coordinator -- the review still happened."""
    record_id = submit(client, as_student(student)).json()["id"]
    review(client, record_id, as_employee(coordinator, EmployeeRole.faculty))

    other_coordinator = factory.employee(roles=[EmployeeRole.faculty], department=dept, hod=hod)
    student.coordinator_id = other_coordinator.emp_id
    db_session.commit()

    response = client.get(
        "/achievements/reviewed", headers=as_employee(coordinator, EmployeeRole.faculty)
    )

    assert ids(response) == {record_id}


def test_students_have_no_review_history(client, student, as_student):
    response = client.get("/achievements/reviewed", headers=as_student(student))

    assert response.status_code == 403


def test_history_requires_authentication(client):
    assert client.get("/achievements/reviewed").status_code == 401


def test_a_multi_role_employee_gets_the_history_of_the_role_they_logged_in_as(
    client, factory, dept, student, as_student, as_employee, db_session
):
    """One person, two tiers: what they verified as faculty and what they
    approved as admin are different lists."""
    both = factory.employee(roles=[EmployeeRole.faculty, EmployeeRole.admin], department=dept)
    student.coordinator_id = both.emp_id
    db_session.commit()

    verified_only = submit(client, as_student(student), title="Verified only").json()["id"]
    review(client, verified_only, as_employee(both, EmployeeRole.faculty))

    went_all_the_way = submit(client, as_student(student), title="Fully approved").json()["id"]
    review(client, went_all_the_way, as_employee(both, EmployeeRole.faculty))
    review(client, went_all_the_way, as_employee(both, EmployeeRole.admin))

    as_faculty = client.get(
        "/achievements/reviewed", headers=as_employee(both, EmployeeRole.faculty)
    )
    as_admin = client.get("/achievements/reviewed", headers=as_employee(both, EmployeeRole.admin))

    assert ids(as_faculty) == {verified_only, went_all_the_way}
    assert ids(as_admin) == {went_all_the_way}
