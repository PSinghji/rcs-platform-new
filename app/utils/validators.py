from fastapi import HTTPException
from app.utils.security import ROLE_ADMIN, ROLE_RESELLER
import os

def admin_only(user):
    if user["role"] != ROLE_ADMIN:
        raise HTTPException(403, "Admin access required")

def admin_or_reseller(user):
    if user["role"] not in [ROLE_ADMIN, ROLE_RESELLER]:
        raise HTTPException(403, "Access denied")
from fastapi import HTTPException
from app.utils.security import ROLE_ADMIN, ROLE_RESELLER

def admin_only(user):
    if user["role"] != ROLE_ADMIN:
        raise HTTPException(403, "Admin access required")

def admin_or_reseller(user):
    if user["role"] not in [ROLE_ADMIN, ROLE_RESELLER]:
        raise HTTPException(403, "Access denied")

MEDIA_RULES = {
    "image": (2 * 1024 * 1024, ["jpg", "jpeg", "png"]),
    "video": (10 * 1024 * 1024, ["mp4"]),
    "file": (5 * 1024 * 1024, ["pdf"])
}

def validate_media(file, media_type):
    max_size, allowed_ext = MEDIA_RULES[media_type]
    ext = file.filename.split(".")[-1].lower()

    if ext not in allowed_ext:
        raise HTTPException(400, f"Invalid file type: {ext}")

    file.file.seek(0, os.SEEK_END)
    size = file.file.tell()
    file.file.seek(0)

    if size > max_size:
        raise HTTPException(400, "File size exceeded")
