"""Standalone developer script to seed test Faculty, HOD, and Student accounts into the database.

Run from backend directory with:
  python -m app.seed_test_employee
"""

from app.auth import hash_password
from app.database import SessionLocal
from app.models import Department, Employee, EmployeeRole, Student, StudentType


def run():
    db = SessionLocal()
    try:
        # Ensure at least one department exists
        dept = db.query(Department).first()
        if not dept:
            dept = Department(dept_name="Computer Science & Engineering", location="Block A")
            db.add(dept)
            db.flush()

        # 1. Seed Faculty Coordinator account if missing
        faculty_email = "test_faculty@example.edu"
        faculty = db.query(Employee).filter(Employee.email == faculty_email).first()
        if not faculty:
            faculty = Employee(
                name="Prof. Rajesh Sharma",
                email=faculty_email,
                phone_number="9876543210",
                salary=85000,
                password_hash=hash_password("faculty123"),
                role=EmployeeRole.faculty_coordinator,
                department_id=dept.dept_id,
            )
            db.add(faculty)
            db.flush()
            print(f"Created Faculty account: {faculty_email} / faculty123")
        else:
            print(f"Faculty account '{faculty_email}' already exists.")

        # 2. Seed HOD account if missing
        hod_email = "test_hod@example.edu"
        hod = db.query(Employee).filter(Employee.email == hod_email).first()
        if not hod:
            hod = Employee(
                name="Dr. Anita Verma",
                email=hod_email,
                phone_number="9876543211",
                salary=130000,
                password_hash=hash_password("hod123"),
                role=EmployeeRole.admin_hod,
                department_id=dept.dept_id,
            )
            db.add(hod)
            print(f"Created HOD account: {hod_email} / hod123")
        else:
            print(f"HOD account '{hod_email}' already exists.")

        # 3. Seed Admin (Clerk) account if missing
        admin_email = "test_admin@example.edu"
        admin = db.query(Employee).filter(Employee.email == admin_email).first()
        if not admin:
            admin = Employee(
                name="Suresh Kumar",
                email=admin_email,
                phone_number="9876543212",
                salary=75000,
                password_hash=hash_password("admin123"),
                role=EmployeeRole.admin_clerk,
                department_id=dept.dept_id,
            )
            db.add(admin)
            print(f"Created Admin account: {admin_email} / admin123")
        else:
            print(f"Admin account '{admin_email}' already exists.")

        # 3. Seed pre-linked Student account if missing
        student_email = "test_student@example.edu"
        student = db.query(Student).filter(Student.email == student_email).first()
        if not student:
            student = Student(
                name="Aarav Gupta",
                email=student_email,
                password_hash=hash_password("student123"),
                student_type=StudentType.inhouse,
                department_id=dept.dept_id,
                coordinator_id=faculty.emp_id,
            )
            db.add(student)
            print(f"Created Student account (linked to Faculty emp_id={faculty.emp_id}): {student_email} / student123")
        else:
            # Ensure existing test student is linked to faculty coordinator
            if student.coordinator_id != faculty.emp_id or student.department_id != dept.dept_id:
                student.coordinator_id = faculty.emp_id
                student.department_id = dept.dept_id
                print(f"Updated Student account '{student_email}' linkage to Faculty emp_id={faculty.emp_id}.")
            else:
                print(f"Student account '{student_email}' already exists and linked.")

        db.commit()

        # Direct database enum & schema fix & verification
        from sqlalchemy import text
        with db.bind.connect().execution_options(isolation_level="AUTOCOMMIT") as conn:
            for enum_name in ["certificatestatus", "absolutecertificatestatus"]:
                for val in ["pending_hod", "pending_admin", "revision_required"]:
                    try:
                        conn.execute(text(f"ALTER TYPE {enum_name} ADD VALUE IF NOT EXISTS '{val}'"))
                    except Exception:
                        pass

            try:
                conn.execute(text("ALTER TABLE certificates ADD COLUMN IF NOT EXISTS owner_type ownertype NOT NULL DEFAULT 'student'"))
                conn.execute(text("ALTER TABLE certificates ADD COLUMN IF NOT EXISTS employee_id INTEGER REFERENCES employees(emp_id)"))
                conn.execute(text("ALTER TABLE certificates ALTER COLUMN student_id DROP NOT NULL"))
            except Exception as e:
                print("Schema update notice:", e)

            enums = conn.execute(text("SELECT enumlabel FROM pg_enum JOIN pg_type ON pg_enum.enumtypid = pg_type.oid WHERE typname = 'certificatestatus' ORDER BY enumsortorder")).fetchall()
            print("DB certificatestatus enum values:", [row[0] for row in enums])
    finally:
        db.close()


if __name__ == "__main__":
    run()

