from fastapi import APIRouter, Depends, HTTPException
from bson import ObjectId
from datetime import datetime

from app.dependencies_ui import get_current_user_ui
from app.database import service_providers_col

import pytz

# Define IST timezone
IST = pytz.timezone('Asia/Kolkata')
router = APIRouter(
    prefix="/ui/admin/providers",
    tags=["Admin Providers"]
)


def ensure_admin(user):
    if user["role"] != "admin":
        raise HTTPException(status_code=403, detail="Admin only")


# ================= LIST PROVIDERS =================
@router.get("")
def list_providers(user=Depends(get_current_user_ui)):
    ensure_admin(user)

    providers = list(
        service_providers_col.find(
            {"status": "ACTIVE"},
            {"name": 1, "status": 1}
        )
    )

    # Convert ObjectId → string
    for p in providers:
        p["_id"] = str(p["_id"])

    return providers


# ================= CREATE PROVIDER =================
@router.post("")
def create_provider(payload: dict, user=Depends(get_current_user_ui)):
    ensure_admin(user)

    name = payload.get("name")
    ptype = payload.get("type", "RCS")

    if not name:
        raise HTTPException(status_code=400, detail="Provider name required")

    service_providers_col.insert_one({
        "name": name,
        "type": ptype,
        "status": "ACTIVE",
        "created_at": datetime.now(IST)
    })

    return {"status": "created"}


# ================= ENABLE / DISABLE =================
@router.post("/{provider_id}/toggle")
def toggle_provider(provider_id: str, user=Depends(get_current_user_ui)):
    ensure_admin(user)

    provider = service_providers_col.find_one(
        {"_id": ObjectId(provider_id)}
    )
    if not provider:
        raise HTTPException(status_code=404, detail="Provider not found")

    new_status = "INACTIVE" if provider["status"] == "ACTIVE" else "ACTIVE"

    service_providers_col.update_one(
        {"_id": provider["_id"]},
        {"$set": {"status": new_status}}
    )

    return {"status": new_status}
