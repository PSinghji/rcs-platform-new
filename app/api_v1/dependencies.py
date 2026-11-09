from bson import ObjectId
from bson.errors import InvalidId
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt

from app.config import settings
from app.database import campaigns_col, users_col


bearer_scheme = HTTPBearer(auto_error=False)


def get_api_user(
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
):
    if not credentials or credentials.scheme.lower() != "bearer":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Bearer access token required",
            headers={"WWW-Authenticate": "Bearer"},
        )

    try:
        payload = jwt.decode(
            credentials.credentials,
            settings.JWT_SECRET,
            algorithms=["HS256"],
        )
        if payload.get("type") not in (None, "access"):
            raise HTTPException(status_code=401, detail="Access token required")
        uid = payload.get("uid")
        if not uid:
            raise HTTPException(status_code=401, detail="Invalid access token")
        user_id = ObjectId(uid)
    except (JWTError, InvalidId, TypeError):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired access token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    user = users_col.find_one({"_id": user_id, "active": True})
    if not user:
        raise HTTPException(status_code=401, detail="User is inactive or no longer exists")
    return user


def get_owned_campaign(campaign_id: str, user: dict):
    try:
        campaign_oid = ObjectId(campaign_id)
    except (InvalidId, TypeError):
        raise HTTPException(status_code=400, detail="Invalid campaign ID")

    query = {"_id": campaign_oid}
    if user.get("role") != "admin":
        query["$or"] = [
            {"user_id": user["_id"]},
            {"user_id": str(user["_id"])},
        ]

    campaign = campaigns_col.find_one(query)
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")
    return campaign
