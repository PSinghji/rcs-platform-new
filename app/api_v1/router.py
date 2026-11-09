from fastapi import APIRouter

from app.api_v1.auth import router as auth_router
from app.api_v1.campaigns import router as campaigns_router
from app.api_v1.templates import router as templates_router


router = APIRouter(prefix="/api/v1")
router.include_router(auth_router)
router.include_router(templates_router)
router.include_router(campaigns_router)


@router.get("/health", tags=["API System"], include_in_schema=False)
def api_health():
    return {"status": "ok", "version": "v1"}
