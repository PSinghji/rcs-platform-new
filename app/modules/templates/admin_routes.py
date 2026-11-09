from fastapi import APIRouter, Depends, HTTPException, Query
from app.database import templates_col
from app.dependencies_ui import get_current_user_ui
from bson import ObjectId
from bson.errors import InvalidId
from datetime import datetime
import pytz
# Define IST timezone
IST = pytz.timezone('Asia/Kolkata')
router = APIRouter(
    prefix="/admin/templates",
    tags=["Admin Templates"]
)

# ================= HELPERS =================

def ensure_admin(user):
    if user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Admin only")


def parse_object_id(id_str: str) -> ObjectId:
    try:
        return ObjectId(id_str)
    except InvalidId:
        raise HTTPException(status_code=400, detail="Invalid template ID")


def serialize_template(tpl):
    tpl["id"] = str(tpl["_id"])
    tpl.pop("_id", None)
    return tpl


# ================= ROUTES =================

@router.get("/all")
def list_all_templates(
    page: int = Query(1, ge=1),
    limit: int = Query(50, le=200),
    user=Depends(get_current_user_ui)
):
    """
    Admin: list ALL templates (any user, any status)
    """
    ensure_admin(user)

    skip = (page - 1) * limit

    cursor = (
        templates_col
        .find({}, {"content": 0})
        .sort("created_at", -1)
        .skip(skip)
        .limit(limit)
    )

    return [serialize_template(t) for t in cursor]


@router.post("/{template_id}/approve")
def approve_template(
    template_id: str,
    user=Depends(get_current_user_ui)
):
    """
    Admin: approve template
    """
    ensure_admin(user)
    oid = parse_object_id(template_id)

    tpl = templates_col.find_one({"_id": oid})
    if not tpl:
        raise HTTPException(status_code=404, detail="Template not found")

    if tpl.get("status") != "pending":
        raise HTTPException(
            status_code=409,
            detail="Only pending templates can be approved"
        )

    templates_col.update_one(
        {"_id": oid},
        {"$set": {
            "status": "approved",
            "approved_at": datetime.now(IST),
            "approved_by": user["_id"],
            "updated_at": datetime.now(IST)
        }}
    )

    return {"status": "approved"}


@router.post("/{template_id}/reject")
def reject_template(
    template_id: str,
    payload: dict,
    user=Depends(get_current_user_ui)
):
    # 1. Check Admin Permission
    ensure_admin(user)
    
    # 2. Get Template
    oid = parse_object_id(template_id)
    tpl = templates_col.find_one({"_id": oid})
    
    if not tpl:
        raise HTTPException(status_code=404, detail="Template not found")

    # 3. Validation Logic (UPDATED)
    # We now ALLOW "approved" templates to be rejected too.
    current_status = tpl.get("status")
    if current_status not in ["pending", "approved"]:
        raise HTTPException(
            status_code=409,
            detail=f"Cannot reject a template that is already '{current_status}'"
        )

    # 4. Perform Update
    templates_col.update_one(
        {"_id": oid},
        {"$set": {
            "status": "rejected",
            "admin_comment": payload.get("comment", ""),
            "rejected_by": user["_id"],
            "updated_at": datetime.now(IST)
        }}
    )

    return {"status": "rejected"}



# @router.post("/{template_id}/reject")
# def reject_template(
#     template_id: str,
#     payload: dict,
#     user=Depends(get_current_user_ui)
# ):
#     """
#     Admin: reject template
#     """
#     ensure_admin(user)
#     oid = parse_object_id(template_id)

#     tpl = templates_col.find_one({"_id": oid})
#     if not tpl:
#         raise HTTPException(status_code=404, detail="Template not found")

#     if tpl.get("status") != "pending":
#         raise HTTPException(
#             status_code=409,
#             detail="Only pending templates can be rejected"
#         )

#     templates_col.update_one(
#         {"_id": oid},
#         {"$set": {
#             "status": "rejected",
#             "admin_comment": payload.get("comment", ""),
#             "rejected_by": user["_id"],
#             "updated_at": datetime.utcnow()
#         }}
#     )

#     return {"status": "rejected"}
