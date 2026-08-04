from app.achievements import build_achievement_router
from app.models import Internship
from app.schemas import InternshipCreate, InternshipOut

router = build_achievement_router(
    model=Internship,
    id_attr="internship_id",
    prefix="/internships",
    tag="internships",
    create_schema=InternshipCreate,
    out_schema=InternshipOut,
)
