from fastapi import HTTPException
from app.utils.security import ROLE_ADMIN, ROLE_RESELLER

def admin_only(user):
    if user["role"] != ROLE_ADMIN:
        raise HTTPException(status_code=403)

def reseller_or_admin(user):
    if user["role"] not in [ROLE_ADMIN, ROLE_RESELLER]:
        raise HTTPException(status_code=403)
