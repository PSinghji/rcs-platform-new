from fastapi import APIRouter, Depends, HTTPException
from app.database import templates_col
from app.dependencies_ui import get_current_user_ui
from datetime import datetime
from bson import ObjectId
import pytz
# Define IST timezone
IST = pytz.timezone('Asia/Kolkata')
router = APIRouter(prefix="/templates", tags=["Templates"])

# ================= CREATE TEMPLATE =================

@router.post("/create")
def create_template(payload: dict, user=Depends(get_current_user_ui)):
    """
    User / Reseller / Admin:
    Create template → goes to pending for admin approval
    """

    name = payload.get("name")
    template_type = payload.get("template_type")
    content = payload.get("content")

    if not name or not template_type or not content:
        raise HTTPException(400, "Invalid payload")

    if template_type not in ["plain", "rich", "carousel"]:
        raise HTTPException(400, "Invalid template type")

    # Minimal Jio structure validation
    if template_type in ["rich", "carousel"]:
        try:
            _ = content["data"]["content"]["richCardDetails"]
        except Exception:
            raise HTTPException(400, "Invalid Jio RCS structure")

    doc = {
        "name": name,
        "template_type": template_type,

        # STORED AS-IS (Jio compliant)
        "content": content,

        # Ownership
        "owner_id": ObjectId(user["_id"]),
        "owner_role": user["role"],
        "owner_name": user.get("name", ""),

        # Approval workflow
        "status": "pending",
        "admin_comment": "",

        # Timestamps
        "created_at": datetime.now(IST),
        "updated_at": datetime.now(IST),
        "approved_at": None,
        "approved_by": None
    }

    templates_col.insert_one(doc)

    return {
        "status": "success",
        "message": "Template submitted for admin approval"
    }

# ================= MY TEMPLATES =================

@router.get("/my")
def get_my_templates(user=Depends(get_current_user_ui)):
    """
    User / Reseller:
    See all OWN templates (any status)
    """
    cursor = templates_col.find(
        {"owner_id": ObjectId(user["_id"])},
        {"content": 0}
    ).sort("created_at", -1)

    return [
        {
            **t,
            "id": str(t["_id"])
        }
        for t in cursor
    ]

# ================= APPROVED TEMPLATES =================

@router.get("/approved")
def get_approved_templates(user=Depends(get_current_user_ui)):
    """
    Used by Campaign Creation dropdown
    Shows ALL approved templates (global)
    """
    cursor = templates_col.find(
        {"status": "approved"},
        {"content": 0}
    ).sort("created_at", -1)

    return [
        {
            **t,
            "id": str(t["_id"])
        }
        for t in cursor
    ]
