"""One-off: add an Admin (HOD) test account to an already-seeded DB.

seed.py skips entirely once any Department row exists, so it won't add this
retroactively to a live DB that was seeded before the admin role existed.

Run with: python -m app.seed_admin
"""

from app.auth import hash_password
from app.database import SessionLocal
from app.models import Department, Employee, EmployeeRole


def run():
    db = SessionLocal()
    try:
        if db.query(Employee).filter(Employee.email == "hod@example.edu").first():
            print("Admin (HOD) account already present, skipping.")
            return

        dept = db.query(Department).first()
        if dept is None:
            print("No department found — run app.seed first.")
            return

        admin_hod = Employee(
            name="Dr. Vikram Nair",
            email="hod@example.edu",
            phone_number="9888888888",
            salary=120000,
            password_hash=hash_password("hod123"),
            role=EmployeeRole.admin_hod,
            department_id=dept.dept_id,
        )
        db.add(admin_hod)
        db.commit()

        print(f"Seeded admin (HOD) into department '{dept.dept_name}':")
        print(f"  admin (HOD) login: hod@example.edu / hod123")
    finally:
        db.close()


if __name__ == "__main__":
    run()
