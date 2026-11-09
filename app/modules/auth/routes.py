from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse, RedirectResponse, HTMLResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
from app.database import users_col
from app.utils.security import verify_password, create_access_token

router = APIRouter(prefix="/auth", tags=["Auth"])

# Initialize templates
templates = Jinja2Templates(directory="templates")

# =========================
# UI Routes
# =========================

@router.get("/login", response_class=HTMLResponse)
async def get_login_page(request: Request):
    """
    Renders the Login HTML page. 
    The 'Request' import ensures this function works correctly.
    """
    return templates.TemplateResponse("auth/login.html", {"request": request})

# =========================
# Login Schema
# =========================

class LoginRequest(BaseModel):
    username: str
    password: str

# =========================
# API Routes
# =========================

@router.post("/login")
def login(data: LoginRequest):
    # 1. Find user by USERNAME
    user = users_col.find_one({
        "username": data.username.strip().lower(),
        "active": True
    })

    if not user:
        raise HTTPException(status_code=401, detail="Invalid credentials")

    # 2. Verify password
    pwd_hash = user.get("password") or user.get("password_hash")
    if not pwd_hash or not verify_password(data.password, pwd_hash):
        raise HTTPException(status_code=401, detail="Invalid credentials")

    # 3. Create JWT token
    token = create_access_token(
        {
            "uid": str(user["_id"]),
            "role": user.get("role", "user"),
            "username": user.get("username")
        }
    )

    # 4. Return response with HTTP-only cookie
    response = JSONResponse(
        {
            "message": "Login successful",
            "role": user.get("role", "user"),
            "name": user.get("name", ""),
            "username": user.get("username")
        }
    )

    response.set_cookie(
        key="token",
        value=token,
        httponly=True,
        secure=True,      # Crucial for HTTPS production
        samesite="Lax",
        path="/"
    )
    response.headers["Authorization"] = f"Bearer {token}"

    return response

@router.get("/logout")
def logout():
    # Redirect to the login UI page after logout
    response = RedirectResponse(url="/auth/login", status_code=302)

    # Clear JWT cookie
    response.delete_cookie(
        key="token",
        path="/"
    )

    return response