from datetime import datetime, timedelta, timezone

from bson import ObjectId
from bson.errors import InvalidId
from fastapi import APIRouter, Depends, HTTPException
from jose import JWTError, jwt
from pydantic import BaseModel, ConfigDict

from app.api_v1.dependencies import get_api_user
from app.config import settings
from app.database import users_col
from app.utils.security import verify_password


router = APIRouter(prefix="/auth", tags=["API Authentication"])
ALGORITHM = "HS256"
REFRESH_TOKEN_DAYS = 7


class TokenRequest(BaseModel):
    username: str
    password: str

    model_config = ConfigDict(
        json_schema_extra={
            "example": {"username": "your_username", "password": "your_password"}
        }
    )


class TokenUserResponse(BaseModel):
    id: str
    username: str
    name: str
    role: str


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str
    expires_in: int
    user: TokenUserResponse


class RefreshRequest(BaseModel):
    refresh_token: str


def _encode_token(user: dict, token_type: str, expires_delta: timedelta):
    now = datetime.now(timezone.utc)
    payload = {
        "uid": str(user["_id"]),
        "username": user.get("username"),
        "role": user.get("role", "user"),
        "type": token_type,
        "iat": now,
        "exp": now + expires_delta,
    }
    return jwt.encode(payload, settings.JWT_SECRET, algorithm=ALGORITHM)


def _token_response(user: dict):
    access_minutes = settings.JWT_EXPIRE_MINUTES
    return {
        "access_token": _encode_token(user, "access", timedelta(minutes=access_minutes)),
        "refresh_token": _encode_token(user, "refresh", timedelta(days=REFRESH_TOKEN_DAYS)),
        "token_type": "Bearer",
        "expires_in": access_minutes * 60,
        "user": {
            "id": str(user["_id"]),
            "username": user.get("username"),
            "name": user.get("name", ""),
            "role": user.get("role", "user"),
        },
    }


@router.post(
    "/token",
    response_model=TokenResponse,
    summary="Generate Bearer Access Token",
    description=(
        "Enter the same username and password used in the portal. Copy access_token from the response, "
        "click Authorize at the top of this page, and paste only the token value."
    ),
    responses={401: {"description": "Invalid username or password"}},
)
def create_token(data: TokenRequest):
    username = data.username.strip().lower()
    user = users_col.find_one({"username": username, "active": True})
    password_hash = (user or {}).get("password") or (user or {}).get("password_hash")
    if not user or not password_hash or not verify_password(data.password, password_hash):
        raise HTTPException(status_code=401, detail="Invalid username or password")
    return _token_response(user)


@router.post("/refresh", include_in_schema=False)
def refresh_token(data: RefreshRequest):
    try:
        payload = jwt.decode(data.refresh_token, settings.JWT_SECRET, algorithms=[ALGORITHM])
        if payload.get("type") != "refresh":
            raise HTTPException(status_code=401, detail="Refresh token required")
        user = users_col.find_one({"_id": ObjectId(payload.get("uid")), "active": True})
    except (JWTError, InvalidId, TypeError, ValueError):
        raise HTTPException(status_code=401, detail="Invalid or expired refresh token")
    if not user:
        raise HTTPException(status_code=401, detail="User is inactive or no longer exists")
    return _token_response(user)


@router.get("/me", include_in_schema=False)
def current_api_user(user=Depends(get_api_user)):
    return {
        "id": str(user["_id"]),
        "username": user.get("username"),
        "name": user.get("name", ""),
        "email": user.get("email", ""),
        "role": user.get("role", "user"),
        "active": bool(user.get("active", False)),
    }


@router.post("/logout", include_in_schema=False)
def logout_api():
    return {"message": "Token discarded. Remove stored access and refresh tokens on the client."}
