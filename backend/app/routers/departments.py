from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Department, Section
from app.schemas import DepartmentOut, SectionOut

router = APIRouter(prefix="/departments", tags=["departments"])


@router.get("", response_model=list[DepartmentOut])
def list_departments(db: Session = Depends(get_db)):
    return db.query(Department).order_by(Department.dept_name).all()


@router.get("/{dept_id}/sections", response_model=list[SectionOut])
def list_department_sections(
    dept_id: int,
    year: int | None = None,
    db: Session = Depends(get_db)
):
    query = db.query(Section).filter(Section.department_id == dept_id)
    if year is not None:
        query = query.filter(Section.year == year)
    return query.order_by(Section.section_name).all()
