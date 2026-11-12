from datetime import datetime

import pytz
from bson import ObjectId
from bson.errors import InvalidId
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field

from app.api_v1.dependencies import get_api_user
from app.database import templates_col
from app.utils.template_variables import extract_template_variables


router = APIRouter(prefix="/templates", tags=["API Templates"])
IST = pytz.timezone("Asia/Kolkata")


class TemplateCreateRequest(BaseModel):
    name: str = Field(description="Template display name")
    template_type: str = Field(description="One of: plain, text, rich, or carousel")
    content: dict = Field(description="Template content payload")

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "name": "Simple Service Update",
                    "template_type": "plain",
                    "content": {"plainText": "Your service request has been completed."},
                },
                {
                    "name": "Dynamic Coupon Offer",
                    "template_type": "plain",
                    "content": {
                        "plainText": "Hello {{name}}, use coupon {{coupon_code}} before {{expiry_date}}."
                    },
                },
            ]
        }
    )


def _serialize(template: dict, include_content: bool = False):
    result = {
        "id": str(template["_id"]),
        "name": template.get("name", ""),
        "template_type": template.get("template_type", ""),
        "status": template.get("status", "pending"),
        "admin_comment": template.get("admin_comment", ""),
        "created_at": template.get("created_at"),
        "updated_at": template.get("updated_at"),
        "approved_at": template.get("approved_at"),
        "message_mode": template.get("message_mode", "dynamic" if template.get("variables") else "simple"),
        "variables": template.get("variables", []),
    }
    if include_content:
        result["content"] = template.get("content", {})
    return result


def _owner_query(user: dict):
    return {
        "$or": [
            {"owner_id": user["_id"]},
            {"owner_id": str(user["_id"])},
            {"user_id": user["_id"]},
            {"user_id": str(user["_id"])},
        ]
    }


@router.post(
    "",
    status_code=201,
    summary="Create Template",
    description=(
        "Create either a simple or dynamic RCS template. Simple templates contain ordinary content. Dynamic "
        "templates contain placeholders such as {{name}} or {{coupon_code}} in any string field, including rich-card "
        "titles, descriptions, URLs, and action values. Placeholder names are detected automatically and returned "
        "as variables. Non-admin templates remain pending until an administrator approves them."
    ),
    responses={
        201: {
            "description": "Template created",
            "content": {"application/json": {"example": {
                "status": "success",
                "template_id": "64f1234567890abcdef12345",
                "approval_status": "pending",
                "message": "Template submitted for admin approval",
            }}},
        },
        400: {"description": "Invalid template name, type, or content"},
        401: {"description": "Bearer token missing, invalid, or expired"},
    },
)
def create_template(data: TemplateCreateRequest, user=Depends(get_api_user)):
    name = data.name.strip()
    template_type = data.template_type.strip().lower()
    if not name or template_type not in {"plain", "text", "rich", "carousel"}:
        raise HTTPException(status_code=400, detail="Invalid template name or type")

    if template_type in {"rich", "carousel"}:
        provider_content = data.content.get("data", {}).get("content", data.content)
        if not isinstance(provider_content, dict) or "richCardDetails" not in provider_content:
            raise HTTPException(status_code=400, detail="Invalid Jio RCS content structure")

    variables = extract_template_variables(data.content)

    now = datetime.now(IST)
    approval_status = "approved" if user.get("role") == "admin" else "pending"
    document = {
        "name": name,
        "template_type": template_type,
        "content": data.content,
        "message_mode": "dynamic" if variables else "simple",
        "variables": variables,
        "owner_id": user["_id"],
        "owner_role": user.get("role", "user"),
        "owner_name": user.get("name", ""),
        "status": approval_status,
        "admin_comment": "",
        "created_at": now,
        "updated_at": now,
        "approved_at": now if approval_status == "approved" else None,
        "approved_by": user["_id"] if approval_status == "approved" else None,
    }
    result = templates_col.insert_one(document)
    return {
        "status": "success",
        "template_id": str(result.inserted_id),
        "approval_status": approval_status,
        "message": (
            "Template created and approved"
            if approval_status == "approved"
            else "Template submitted for admin approval"
        ),
    }


@router.get("", include_in_schema=False)
def list_my_templates(
    status: str = Query(default=None),
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    user=Depends(get_api_user),
):
    query = _owner_query(user)
    if status:
        query = {"$and": [query, {"status": status}]}
    cursor = templates_col.find(query, {"content": 0}).sort("created_at", -1).skip(offset).limit(limit)
    return {
        "items": [_serialize(item) for item in cursor],
        "limit": limit,
        "offset": offset,
        "total": templates_col.count_documents(query),
    }


@router.get(
    "/approved",
    summary="List Approved Templates",
    description=(
        "Return approved templates that can be used to obtain a template_id before campaign creation. "
        "Click Authorize once and Swagger sends the Bearer token automatically."
    ),
    responses={
        200: {
            "description": "Approved template list",
            "content": {"application/json": {"example": {"items": [{
                "id": "64f1234567890abcdef12345",
                "name": "October Offer",
                "template_type": "plain",
                "status": "approved",
                "admin_comment": "",
                "created_at": "2026-10-09T10:00:00+05:30",
                "updated_at": "2026-10-09T10:05:00+05:30",
                "approved_at": "2026-10-09T10:05:00+05:30",
            }]}}},
        },
        401: {"description": "Bearer token missing, invalid, or expired"},
    },
)
def list_approved_templates(
    limit: int = Query(default=100, ge=1, le=200, description="Maximum number of approved templates to return"),
    user=Depends(get_api_user),
):
    cursor = templates_col.find({"status": "approved"}, {"content": 0}).sort("created_at", -1).limit(limit)
    return {"items": [_serialize(item) for item in cursor]}


@router.get("/{template_id}", include_in_schema=False)
def get_template(template_id: str, user=Depends(get_api_user)):
    try:
        template_oid = ObjectId(template_id)
    except (InvalidId, TypeError):
        raise HTTPException(status_code=400, detail="Invalid template ID")

    template = templates_col.find_one({"_id": template_oid})
    if not template:
        raise HTTPException(status_code=404, detail="Template not found")

    owned = any(
        template.get(field) in (user["_id"], str(user["_id"]))
        for field in ("owner_id", "user_id")
    )
    if user.get("role") != "admin" and not owned and template.get("status") != "approved":
        raise HTTPException(status_code=403, detail="Access denied")
    return _serialize(template, include_content=True)


@router.get("/{template_id}/status")
def get_template_status(template_id: str, user=Depends(get_api_user)):
    template = get_template(template_id, user)
    return {
        "template_id": template["id"],
        "status": template["status"],
        "admin_comment": template.get("admin_comment", ""),
    }
