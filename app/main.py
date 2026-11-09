from fastapi import FastAPI, Request
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from contextlib import asynccontextmanager
import logging
import os
from jose import jwt

# Import the database object and security constants
from app.database import db
from app.utils.security import SECRET_KEY, ALGORITHM 

from app.modules.admin.stats import router as admin_stats_router

# ================= ROUTER IMPORTS =================
from app.modules.auth.routes import router as auth_router
from app.modules.users.routes import router as user_router
from app.modules.campaigns.routes import router as campaign_router
from app.modules.templates.routes import router as template_router
from app.modules.templates.admin_routes import router as admin_template_router
from app.modules.webhooks.routes import router as webhook_router
from app.modules.webhooks.routes import root_router as dlr_root_router

from app.modules.ui.routes import router as ui_router
from app.modules.media.routes import router as media_router
from app.modules.admin.provider_routes import router as provider_admin_router
from app.modules.admin.report_adjustments import router as report_adjustments_router
from app.modules.providers.user_assignment_routes import router as user_provider_router
from app.api_v1.router import router as api_v1_router
from app.api_v1.portal import router as api_portal_router

# ================= LIFESPAN (DB INIT) =================
@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.db = db
    logging.info("Database attached to app state.")
    yield

# ================= APP INIT =================
logging.basicConfig(level=logging.DEBUG)

app = FastAPI(
    title="RCS Platform API",
    description=(
        "Postman-style interactive API console. First execute POST /api/v1/auth/token, "
        "copy access_token, click Authorize, and paste the token. Swagger automatically "
        "adds the Bearer prefix to every protected request."
    ),
    version="1.0.0",
    lifespan=lifespan,
    swagger_ui_parameters={
        "persistAuthorization": True,
        "tryItOutEnabled": True,
        "displayRequestDuration": True,
        "filter": True,
        "docExpansion": "list",
        "defaultModelRendering": "example",
    },
)

templates = Jinja2Templates(directory="templates")
app.state.templates = templates 

# ================= ROUTER REGISTRATION =================
app.include_router(admin_stats_router, include_in_schema=False)
app.include_router(dlr_root_router, include_in_schema=False)
app.include_router(auth_router, include_in_schema=False)
app.include_router(campaign_router, include_in_schema=False)
app.include_router(user_router, include_in_schema=False)
app.include_router(template_router, include_in_schema=False)
app.include_router(admin_template_router, include_in_schema=False)
app.include_router(webhook_router, include_in_schema=False)
app.include_router(ui_router, include_in_schema=False)
app.include_router(media_router, include_in_schema=False)
app.include_router(provider_admin_router, include_in_schema=False)
app.include_router(report_adjustments_router, include_in_schema=False)
app.include_router(user_provider_router, include_in_schema=False)
app.include_router(api_v1_router)
app.include_router(api_portal_router, include_in_schema=False)

# ================= STATIC FILES =================
# ✅ FIX: Pointing to the absolute path where your media is actually saved
# This ensures that /static/uploads/file.mp4 is correctly resolved and served with the right MIME type.
STATIC_PATH = os.getenv("RCS_STATIC_PATH", "/var/www/rcs-platform/static")
if not os.path.exists(STATIC_PATH):
    os.makedirs(STATIC_PATH, exist_ok=True)

app.mount("/static", StaticFiles(directory=STATIC_PATH), name="static")

# ================= ROOT & HEALTH =================
@app.api_route("/", methods=["GET", "HEAD"], include_in_schema=False)
def root():
    return RedirectResponse(url="/ui/login")

@app.get("/health", include_in_schema=False)
def health():
    return {"status": "ok"}

# ================= AUTH MIDDLEWARE =================
@app.middleware("http")
async def auth_middleware(request: Request, call_next):
    if request.url.path.startswith("/ui") and "/login" not in request.url.path:
        token = request.cookies.get("token")
        
        if not token:
            return RedirectResponse(url="/ui/login")
        
        try:
            payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
            request.state.user = payload 
        except Exception:
            response = RedirectResponse(url="/ui/login")
            response.delete_cookie("token")
            return response

    return await call_next(request)
