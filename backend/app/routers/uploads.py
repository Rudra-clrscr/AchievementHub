from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from pydantic import BaseModel

from app.auth import get_current_identity
from app.uploads import compress_and_store

router = APIRouter(prefix="/uploads", tags=["uploads"])

ALLOWED_CATEGORIES = {"certificates", "publications", "patents", "internships", "events"}


class UploadResponse(BaseModel):
    file_url: str
    original_size: int
    stored_size: int
    content_type: str


@router.post("", response_model=UploadResponse, status_code=status.HTTP_201_CREATED)
def upload_file(
    category: str = Form(...),
    file: UploadFile = File(...),
    _identity=Depends(get_current_identity),
):
    if category not in ALLOWED_CATEGORIES:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Unknown upload category")

    result = compress_and_store(file, category)
    return UploadResponse(
        file_url=result.url,
        original_size=result.original_size,
        stored_size=result.stored_size,
        content_type=result.content_type,
    )
