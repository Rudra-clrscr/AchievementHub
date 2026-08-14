from pathlib import Path
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.config import settings
from app.routers import auth, departments, achievements, students, employees, uploads
from app.routers import feed

app = FastAPI(title="AchievementHub API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def ensure_schema_migrations():
    from sqlalchemy import text
    from app.database import engine
    with engine.connect().execution_options(isolation_level="AUTOCOMMIT") as conn:
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
            print("Schema startup migration notice:", e)

uploads_dir = Path("uploads")
uploads_dir.mkdir(exist_ok=True)
app.mount("/uploads/files", StaticFiles(directory="uploads"), name="uploads")

app.include_router(auth.router)
app.include_router(departments.router)
app.include_router(achievements.router)
app.include_router(students.router)
app.include_router(employees.router)
app.include_router(uploads.router)
app.include_router(feed.router)


@app.get("/health")
def health():
    return {"status": "ok"}
