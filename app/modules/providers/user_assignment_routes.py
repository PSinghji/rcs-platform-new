from fastapi import APIRouter, Depends, HTTPException
from bson import ObjectId
from datetime import datetime
import pytz



from app.dependencies_ui import get_current_user_ui
from app.database import (
    user_providers_col,
    service_providers_col,
    users_col
)

router = APIRouter(
    prefix="/admin/user-providers",
    tags=["User Provider Assignment"]
)

# Define IST timezone
IST = pytz.timezone('Asia/Kolkata')
def ensure_admin(user):
    if user["role"] != "admin":
        raise HTTPException(403, "Admin only")


# ================= ASSIGN PROVIDER TO USER =================
@router.post("")
def assign_provider(payload: dict, user=Depends(get_current_user_ui)):
    ensure_admin(user)

    user_id = payload.get("user_id")
    provider_id = payload.get("provider_id")
    credentials = payload.get("credentials", {})

    if not user_id or not provider_id:
        raise HTTPException(400, "user_id and provider_id required")

    if not users_col.find_one({"_id": ObjectId(user_id)}):
        raise HTTPException(404, "User not found")

    provider = service_providers_col.find_one({"_id": ObjectId(provider_id)})
    if not provider:
        raise HTTPException(404, "Provider not found")

    # Deactivate old provider
    user_providers_col.update_many(
        {"user_id": ObjectId(user_id)},
        {"$set": {"is_active": False}}
    )

    # Assign new provider
    user_providers_col.insert_one({
        "user_id": ObjectId(user_id),
        "provider_id": provider["_id"],
        "provider_name": provider["name"],
        "credentials": credentials,  # 🔐 SECRET
        "is_active": True,
        "created_at": datetime.now(IST)
    })

    # Save active provider reference
    users_col.update_one(
        {"_id": ObjectId(user_id)},
        {"$set": {"active_provider_id": provider["_id"]}}
    )

    return {"status": "assigned"}
