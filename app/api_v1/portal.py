from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.templating import Jinja2Templates

from app.dependencies_ui import get_current_user_ui


router = APIRouter(prefix="/ui/api", tags=["API Portal"])
templates = Jinja2Templates(directory="templates")
DOCUMENT_PATH = Path("/var/www/rcs-platform/static/docs/RCS_API_Consumer_Guide.docx")
SAMPLE_XLSX_PATH = Path("/var/www/rcs-platform/static/docs/RCS_Campaign_Bulk_Upload_Template.xlsx")


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
    if not DOCUMENT_PATH.exists():
        raise HTTPException(status_code=404, detail="API document is not available")
    return FileResponse(
        DOCUMENT_PATH,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        filename="RCS_API_Consumer_Guide.docx",
    )


@router.get("/sample-campaign-upload/download")
def download_campaign_upload_sample(user=Depends(get_current_user_ui)):
    if not SAMPLE_XLSX_PATH.exists():
        raise HTTPException(status_code=404, detail="Campaign upload sample is not available")
    return FileResponse(
        SAMPLE_XLSX_PATH,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        filename="RCS_Campaign_Bulk_Upload_Template.xlsx",
    )
