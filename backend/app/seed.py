"""Dev seed data: one department, one faculty coordinator, one inhouse student.

Run with: python -m app.seed
"""

from app.auth import hash_password
from app.database import SessionLocal
from app.models import Department, Employee, EmployeeRole, Student, StudentType


def run():
    db = SessionLocal()
    try:
        if db.query(Department).count() > 0:
            print("Seed data already present, skipping.")
            return

        dept = Department(dept_name="Computer Science", location="Block A")
        db.add(dept)
        db.flush()

        coordinator = Employee(
            name="Dr. Asha Rao",
            email="coordinator@example.edu",
            phone_number="9999999999",
            salary=80000,
            password_hash=hash_password("coordinator123"),
            role=EmployeeRole.faculty_coordinator,
            department_id=dept.dept_id,
        )
        db.add(coordinator)
        db.flush()

        student = Student(
            name="Rahul Sharma",
            email="student@example.edu",
            password_hash=hash_password("student123"),
            student_type=StudentType.inhouse,
            department_id=dept.dept_id,
            coordinator_id=coordinator.emp_id,
        )
        db.add(student)
        db.commit()

        print("Seeded:")
        print(f"  coordinator login: coordinator@example.edu / coordinator123")
        print(f"  student login:     student@example.edu / student123")
    finally:
        db.close()


if __name__ == "__main__":
    run()
