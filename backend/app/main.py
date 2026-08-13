from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

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
