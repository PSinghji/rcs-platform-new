import os
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.templating import Jinja2Templates

from app.dependencies_ui import get_current_user_ui


router = APIRouter(prefix="/ui/api", tags=["API Portal"])
templates = Jinja2Templates(directory="templates")
PROJECT_ROOT = Path(__file__).resolve().parents[2]


def _artifact_path(env_name: str, filename: str) -> Path:
    """Resolve an optional override, then repo artifacts, then legacy static/docs."""
    candidates = [
        Path(os.environ[env_name]) if os.getenv(env_name) else None,
        PROJECT_ROOT / "artifacts" / filename,
        PROJECT_ROOT / "static" / "docs" / filename,
    ]
    return next((path for path in candidates if path and path.is_file()), candidates[1])


@router.get("", response_class=HTMLResponse)
def api_portal(request: Request, user=Depends(get_current_user_ui)):
    return templates.TemplateResponse(
        "api/index.html",
        {
            "request": request,
            "user": user,
            "title": "API Integration",
        },
    )


@router.get("/documentation/download")
def download_api_document(user=Depends(get_current_user_ui)):
    document_path = _artifact_path("RCS_API_DOCUMENT_PATH", "RCS_API_Consumer_Guide.docx")
    if not document_path.exists():
        raise HTTPException(status_code=404, detail="API document is not available")
    return FileResponse(
        document_path,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        filename="RCS_API_Consumer_Guide.docx",
    )


@router.get("/sample-campaign-upload/download")
def download_campaign_upload_sample(user=Depends(get_current_user_ui)):
    sample_path = _artifact_path("RCS_CAMPAIGN_SAMPLE_PATH", "RCS_Campaign_Bulk_Upload_Template.xlsx")
    if not sample_path.exists():
        raise HTTPException(status_code=404, detail="Campaign upload sample is not available")
    return FileResponse(
        sample_path,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        filename="RCS_Campaign_Bulk_Upload_Template.xlsx",
    )
