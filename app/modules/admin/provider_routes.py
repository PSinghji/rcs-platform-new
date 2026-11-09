from bson import ObjectId
from fastapi import APIRouter, Request, Form, HTTPException, Depends
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from app.database import service_providers_col, users_col # Added users_col
from datetime import datetime
from app.dependencies_ui import get_current_user_ui
import pytz

IST = pytz.timezone('Asia/Kolkata')
templates = Jinja2Templates(directory="templates")
router = APIRouter()

# ================= LIST PROVIDERS UI =================
@router.get("/ui/admin/providers", response_class=HTMLResponse)
async def list_providers(request: Request, current_user=Depends(get_current_user_ui)):
    if not current_user:
        return RedirectResponse(url="/auth/login", status_code=303)

    # RE-FETCH USER TO GET LIVE WALLET BALANCE
    # This prevents the 0 balance issue
    user_data = users_col.find_one({"_id": ObjectId(current_user["_id"])})
    
    providers_list = list(service_providers_col.find())
    
    return templates.TemplateResponse(
        "admin/providers_list.html", 
        {
            "request": request, 
            "providers": providers_list,
            "user": user_data # Now contains live wallet_balance
        }
    )

# Logic to handle the "Add Provider" Form
@router.post("/ui/admin/providers/create")
async def create_provider(
    name: str = Form(...),
    code: str = Form(...),
    type: str = Form("RCS"),
    status: str = Form("ACTIVE")
):
    new_provider = {
        "name": name,
        "code": code.lower().strip(),
        "type": type,
        "status": status,
        "created_at": datetime.now(IST)
    }
    service_providers_col.insert_one(new_provider)
    return RedirectResponse(url="/ui/admin/providers", status_code=303)

# ================= EDIT PROVIDER UI (GET) =================
@router.get("/ui/admin/providers/update/{provider_id}", response_class=HTMLResponse)
async def edit_provider_page(request: Request, provider_id: str, current_user=Depends(get_current_user_ui)):
    if not current_user:
        return RedirectResponse(url="/auth/login", status_code=303)

    # Fetch live user data for header balance
    user_data = users_col.find_one({"_id": ObjectId(current_user["_id"])})
    
    provider = service_providers_col.find_one({"_id": ObjectId(provider_id)})
    if not provider:
        raise HTTPException(status_code=404, detail="Provider not found")

    return templates.TemplateResponse(
        "admin/providers_edit.html", 
        {"request": request, "provider": provider, "user": user_data}
    )

# ================= UPDATE PROVIDER LOGIC (POST) =================
@router.post("/ui/admin/providers/update/{provider_id}")
async def update_provider(
    provider_id: str,
    name: str = Form(...),
    code: str = Form(None), 
    type: str = Form("RCS"),
    status: str = Form("ACTIVE")
):
    if not code:
        raise HTTPException(status_code=400, detail="Provider Code is required")

    update_data = {
        "name": name,
        "code": code.lower().strip(),
        "type": type,
        "status": status,
        "updated_at": datetime.now(IST)
    }
    
    result = service_providers_col.update_one(
        {"_id": ObjectId(provider_id)},
        {"$set": update_data}
    )
    
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Provider not found")
        
    return RedirectResponse(url="/ui/admin/providers", status_code=303)