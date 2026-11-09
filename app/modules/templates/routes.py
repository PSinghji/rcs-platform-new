from fastapi import APIRouter, Depends, HTTPException
from app.database import templates_col
from app.dependencies_ui import get_current_user_ui
from datetime import datetime
from bson import ObjectId
import pytz
from app.utils.template_variables import extract_template_variables
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

    # Minimal Jio structure validation. UI stores the provider content object
    # directly; API clients may also send the full data.content wrapper.
    if template_type in ["rich", "carousel"]:
        provider_content = content.get("data", {}).get("content", content)
        if not isinstance(provider_content, dict) or "richCardDetails" not in provider_content:
            raise HTTPException(400, "Invalid Jio RCS structure")

    variables = extract_template_variables(content)

    doc = {
        "name": name,
        "template_type": template_type,

        # STORED AS-IS (Jio compliant)
        "content": content,
        "message_mode": "dynamic" if variables else "simple",
        "variables": variables,

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
