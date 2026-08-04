from app.achievements import build_achievement_router
from app.models import ResearchPublication
from app.schemas import PublicationCreate, PublicationOut

router = build_achievement_router(
    model=ResearchPublication,
    id_attr="pub_id",
    prefix="/publications",
    tag="publications",
    create_schema=PublicationCreate,
    out_schema=PublicationOut,
)
