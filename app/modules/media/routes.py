import os
import shutil
from uuid import uuid4
from fastapi import APIRouter, UploadFile, File, HTTPException, Depends
from app.dependencies_ui import get_current_user_ui

router = APIRouter(prefix="/api/media", tags=["Media"])

STATIC_PATH = os.getenv("RCS_STATIC_PATH", "/var/www/rcs-platform/static")
UPLOAD_DIR = os.path.join(STATIC_PATH, "uploads")
PUBLIC_BASE_URL = os.getenv("RCS_PUBLIC_BASE_URL", "https://rcs.ostpl.com").rstrip("/")
os.makedirs(UPLOAD_DIR, exist_ok=True)

ALLOWED_TYPES = ("image/jpeg", "image/png", "image/gif","image/webp", "video/mp4", "application/pdf")
MAX_SIZE_MB = 10

@router.post("/upload")
async def upload_media(file: UploadFile = File(...), user=Depends(get_current_user_ui)):
    if file.content_type not in ALLOWED_TYPES:
        raise HTTPException(status_code=400, detail="Invalid media type.")

    ext = file.filename.split(".")[-1].lower()
    filename = f"{uuid4()}.{ext}"
    file_path = os.path.join(UPLOAD_DIR, filename)

    try:
        # Reset file pointer and stream to disk
        await file.seek(0)
        with open(file_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
        
        # Validate Size after save
        if os.path.getsize(file_path) > MAX_SIZE_MB * 1024 * 1024:
            os.remove(file_path)
            raise HTTPException(status_code=400, detail="File too large.")

    except Exception as e:
        if isinstance(e, HTTPException): raise e
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        await file.close()

    # The URL that the frontend will use to PREVIEW
    public_url = f"{PUBLIC_BASE_URL}/static/uploads/{filename}"
    return {"status": "success", "fileUrl": public_url}
