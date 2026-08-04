from app.achievements import build_achievement_router
from app.models import EventParticipation
from app.schemas import EventParticipationCreate, EventParticipationOut

router = build_achievement_router(
    model=EventParticipation,
    id_attr="event_id",
    prefix="/events",
    tag="events",
    create_schema=EventParticipationCreate,
    out_schema=EventParticipationOut,
)
