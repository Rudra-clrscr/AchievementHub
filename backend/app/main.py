from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.routers import auth, certificates, departments, events, internships, patents, publications, uploads, feed

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
app.include_router(certificates.router)
app.include_router(publications.router)
app.include_router(patents.router)
app.include_router(internships.router)
app.include_router(events.router)
app.include_router(uploads.router)
app.include_router(feed.router)


@app.get("/health")
def health():
    return {"status": "ok"}
