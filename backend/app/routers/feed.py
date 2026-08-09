from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import desc
from typing import List
from app.database import get_db
from app.models import (
    Achievement, CertificateStatus, Student, Employee
)
from app.schemas import FeedItem

router = APIRouter(prefix="/feed", tags=["feed"])

def fetch_achievements(db: Session, owner_type: str = None, category: str = None, is_featured: bool = None, search: str = None, limit: int = 100):
    query = db.query(Achievement, Student.name.label("student_name"), Employee.name.label("employee_name"))\
        .outerjoin(Student, Achievement.student_id == Student.student_id)\
        .outerjoin(Employee, Achievement.employee_id == Employee.emp_id)
        
    query = query.filter(Achievement.status == CertificateStatus.approved)
    
    if owner_type:
        query = query.filter(Achievement.owner_type == owner_type)
            
    if is_featured is not None:
        query = query.filter(Achievement.is_featured == is_featured)
    
    if category:
        query = query.filter(Achievement.category.ilike(f"%{category}%"))
    
    if search:
        search_filter = Achievement.title.ilike(f"%{search}%")
        query = query.filter(search_filter)
        
    records = query.order_by(desc(Achievement.verified_at)).limit(limit).all()
    
    feed_items = []
    for record, student_name, employee_name in records:
        feed_items.append(
            FeedItem(
                id=record.id,
                type=record.category.lower().replace(" ", "-"),  # For URL routing
                title=record.title,
                owner_type=record.owner_type.value,
                student_name=student_name if record.owner_type.value == "student" else employee_name,
                category=record.category,
                verified_at=record.verified_at,
                file_url=record.file_url,
                is_featured=record.is_featured,
                thumbnail_url=record.thumbnail_url
            )
        )
    return feed_items

@router.get("/latest", response_model=List[FeedItem])
def get_latest_feed(owner_type: str = None, category: str = None, search: str = None, db: Session = Depends(get_db)):
    return fetch_achievements(db, owner_type=owner_type, category=category, search=search, limit=100)

@router.get("/top", response_model=List[FeedItem])
def get_top_feed(db: Session = Depends(get_db)):
    return fetch_achievements(db, is_featured=True, limit=20)
