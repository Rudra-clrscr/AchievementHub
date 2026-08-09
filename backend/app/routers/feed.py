from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import desc
from typing import List
from app.database import get_db
from app.models import (
    Certificate, ResearchPublication, Patent, Internship, EventParticipation,
    CertificateStatus, Student
)
from app.schemas import FeedItem

router = APIRouter(prefix="/feed", tags=["feed"])

def fetch_achievements(db: Session, model, type_name: str, title_attr: str, category_attr: str = None, owner_type: str = None, is_featured: bool = None, search: str = None):
    query = db.query(model, Student.name.label("student_name")).outerjoin(Student, model.student_id == Student.student_id)
    query = query.filter(model.status == CertificateStatus.approved)
    
    if owner_type:
        if hasattr(model, "owner_type"):
            query = query.filter(model.owner_type == owner_type)
        elif owner_type != "student":
            return []
            
    if is_featured is not None:
        if hasattr(model, "is_featured"):
            query = query.filter(model.is_featured == is_featured)
        elif is_featured:
            return []
    
    if search:
        search_filter = getattr(model, title_attr).ilike(f"%{search}%")
        query = query.filter(search_filter)
        
    records = query.order_by(desc(model.verified_at)).limit(50).all()
    
    feed_items = []
    for record, student_name in records:
        category = getattr(record, category_attr).value if category_attr and getattr(record, category_attr) else type_name.capitalize()
        if type_name == "certificate" and hasattr(record, "category"):
             category = record.category.value
        
        feed_items.append(
            FeedItem(
                id=getattr(record, f"{type_name}_id") if hasattr(record, f"{type_name}_id") else getattr(record, "cert_id", getattr(record, "pub_id", getattr(record, "patent_id", getattr(record, "internship_id", getattr(record, "event_id", 0))))),
                type=type_name,
                title=getattr(record, title_attr),
                owner_type=record.owner_type.value if hasattr(record, "owner_type") else "student",
                student_name=student_name,
                category=category,
                verified_at=record.verified_at,
                file_url=record.file_url,
                is_featured=record.is_featured if hasattr(record, "is_featured") else False,
                thumbnail_url=record.thumbnail_url if hasattr(record, "thumbnail_url") else None
            )
        )
    return feed_items

@router.get("/latest", response_model=List[FeedItem])
def get_latest_feed(owner_type: str = None, category: str = None, search: str = None, db: Session = Depends(get_db)):
    items = []
    # Certificates
    if not category or category.lower() in ["certificate", "fdp", "external", "nptel", "ieee"]:
        items.extend(fetch_achievements(db, Certificate, "certificate", "title", "category", owner_type, None, search))
    
    # Publications
    if not category or category.lower() in ["publication", "research"]:
        items.extend(fetch_achievements(db, ResearchPublication, "publication", "title", None, owner_type, None, search))
        
    # Patents
    if not category or category.lower() == "patent":
        items.extend(fetch_achievements(db, Patent, "patent", "title", None, owner_type, None, search))
        
    # Internships
    if not category or category.lower() == "internship":
        items.extend(fetch_achievements(db, Internship, "internship", "organization", None, owner_type, None, search))
        
    # Events
    if not category or category.lower() in ["event", "sports", "hackathon"]:
        items.extend(fetch_achievements(db, EventParticipation, "event", "event_name", None, owner_type, None, search))
        
    # Sort in python (combined limit)
    from datetime import datetime
    items.sort(key=lambda x: x.verified_at if x.verified_at else datetime.min, reverse=True)
    return items[:100]

@router.get("/top", response_model=List[FeedItem])
def get_top_feed(db: Session = Depends(get_db)):
    items = []
    items.extend(fetch_achievements(db, Certificate, "certificate", "title", "category", None, True, None))
    items.extend(fetch_achievements(db, ResearchPublication, "publication", "title", None, None, True, None))
    items.extend(fetch_achievements(db, Patent, "patent", "title", None, None, True, None))
    items.extend(fetch_achievements(db, Internship, "internship", "organization", None, None, True, None))
    items.extend(fetch_achievements(db, EventParticipation, "event", "event_name", None, None, True, None))
    
    from datetime import datetime
    items.sort(key=lambda x: x.verified_at if x.verified_at else datetime.min, reverse=True)
    return items[:20]
