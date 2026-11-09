from fastapi import Request, HTTPException, status
from jose import jwt, JWTError
from bson import ObjectId
from bson.errors import InvalidId
from app.config import settings
from app.database import users_col


# ================= AUTH =================

def get_current_user_ui(request: Request):
    token = request.cookies.get("token")
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated"
        )

    try:
        payload = jwt.decode(
            token,
            settings.JWT_SECRET,
            algorithms=["HS256"]
        )

        uid = payload.get("uid")
        if not uid:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token"
            )

        try:
            user = users_col.find_one({"_id": ObjectId(uid)})
        except InvalidId:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid user id"
            )

        if not user:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="User not found"
            )

        return user

    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token"
        )


# ================= ROLE GUARDS =================

def require_admin_ui(user):
    if user.get("role") != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required"
        )


def require_reseller_ui(user):
    if user.get("role") not in ("reseller", "admin"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Reseller access required"
        )


def require_user_ui(user):
    if user.get("role") not in ("user", "reseller", "admin"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User access required"
        )


# ================= ROUTE ENFORCEMENT =================

def enforce_ui_access(request: Request, user):
    """
    Final UI security gate.
    Call this at the TOP of every /ui route.
    """
    path = request.url.path

    # --- Admin only ---
    if path.startswith("/ui/admin"):
        require_admin_ui(user)

    if path.startswith("/ui/admin/templates/approvals"):
        require_admin_ui(user)

    if path.startswith("/ui/campaigns/all"):
        require_admin_ui(user)

    # --- Reseller ---
    if path.startswith("/ui/reseller"):
        require_reseller_ui(user)

    if path.startswith("/ui/users"):
        require_reseller_ui(user)

    # --- User / Common ---
    if path.startswith("/ui/user"):
        require_user_ui(user)

    if path.startswith("/ui/templates"):
        require_user_ui(user)

    if path.startswith("/ui/campaigns"):
        require_user_ui(user)

    if path.startswith("/ui/wallet"):
        require_user_ui(user)
