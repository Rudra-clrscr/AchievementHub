from app.achievements import build_achievement_router
from app.models import Patent
from app.schemas import PatentCreate, PatentOut

router = build_achievement_router(
    model=Patent,
    id_attr="patent_id",
    prefix="/patents",
    tag="patents",
    create_schema=PatentCreate,
    out_schema=PatentOut,
)
