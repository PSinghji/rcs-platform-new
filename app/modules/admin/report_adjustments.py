import math
from datetime import datetime, timedelta

import pytz
from bson import ObjectId
from bson.errors import InvalidId
from fastapi import APIRouter, Body, Depends, HTTPException, Query, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from pymongo import UpdateOne

from app.database import campaigns_col, db, messages_col, users_col
from app.dependencies_ui import get_current_user_ui


router = APIRouter(prefix="/ui/admin/report-adjustments", tags=["Admin Report Adjustments"])
templates = Jinja2Templates(directory="templates")
adjustments_col = db.report_adjustments
IST = pytz.timezone("Asia/Kolkata")
BATCH_SIZE = 10000


def _require_admin(user):
    if not user or user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")


def _object_id(value: str, label: str):
    try:
        return ObjectId(value)
    except (InvalidId, TypeError):
        raise HTTPException(status_code=400, detail=f"Invalid {label}")


def _user_filter(user_id):
    return {"$or": [{"user_id": user_id}, {"user_id": str(user_id)}]}


def _load_campaign_for_user(user_id: str, campaign_id: str):
    user_oid = _object_id(user_id, "user id")
    campaign_oid = _object_id(campaign_id, "campaign id")
    campaign = campaigns_col.find_one({"$and": [{"_id": campaign_oid}, _user_filter(user_oid)]})
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found for the selected user")
    return campaign


def _preview(campaign: dict, failure_percent: float):
    if not math.isfinite(failure_percent) or not 0 <= failure_percent <= 100:
        raise HTTPException(status_code=400, detail="Failure percentage must be between 0 and 100")
    if str(campaign.get("status", "")).lower() != "completed":
        raise HTTPException(status_code=409, detail="Only completed campaigns can be adjusted")

    campaign_id = campaign["_id"]
    total = int(campaign.get("total_numbers") or messages_col.count_documents({"campaign_id": campaign_id}))
    current_failed = messages_col.count_documents({"campaign_id": campaign_id, "status": "failed"})
    current_delivered = messages_col.count_documents({"campaign_id": campaign_id, "status": "delivered"})
    target_failed = int((total * failure_percent / 100.0) + 0.5)
    failed_delta = target_failed - current_failed

    if failed_delta > current_delivered:
        raise HTTPException(
            status_code=409,
            detail=f"Need {failed_delta} delivered messages but only {current_delivered} are available",
        )

    if failed_delta > 0:
        direction = "delivered_to_failed"
        action_label = "Delivered → Failed"
    elif failed_delta < 0:
        direction = "failed_to_delivered"
        action_label = "Failed → Delivered"
    else:
        direction = "none"
        action_label = "No status change required"

    return {
        "campaign_id": str(campaign_id),
        "campaign_name": campaign.get("campaign_name", ""),
        "campaign_status": campaign.get("status", ""),
        "total_numbers": total,
        "failure_percent": failure_percent,
        "success_percent": 100 - failure_percent,
        "current_failed": current_failed,
        "current_success": total - current_failed,
        "current_delivered": current_delivered,
        "target_failed": target_failed,
        "target_success": total - target_failed,
        "messages_to_change": abs(failed_delta),
        "direction": direction,
        "action_label": action_label,
        "projected_delivered": current_delivered - failed_delta,
    }


def _failed_documents_for_restore(campaign_id, limit):
    projection = {"_id": 1, "sent_at": 1, "updated_at": 1, "created_at": 1}
    documents = list(
        messages_col.find(
            {"campaign_id": campaign_id, "status": "failed", "is_fake": True},
            projection,
        ).sort("_id", 1).limit(limit)
    )
    remaining = limit - len(documents)
    if remaining > 0:
        documents.extend(
            messages_col.find(
                {"campaign_id": campaign_id, "status": "failed", "is_fake": {"$ne": True}},
                projection,
            ).sort("_id", 1).limit(remaining)
        )
    return documents


@router.get("", response_class=HTMLResponse)
def report_adjustment_page(request: Request, user=Depends(get_current_user_ui)):
    _require_admin(user)
    managed_users = list(
        users_col.find(
            {"active": True},
            {"name": 1, "username": 1, "role": 1},
        ).sort([("name", 1), ("username", 1)])
    )
    return templates.TemplateResponse(
        "admin/report_adjustments.html",
        {"request": request, "user": user, "managed_users": managed_users, "title": "Report Adjustment"},
    )


@router.get("/campaigns")
def campaigns_for_user(
    user_id: str,
    date_from: str | None = Query(default=None, description="Campaign start date in YYYY-MM-DD format"),
    date_to: str | None = Query(default=None, description="Campaign end date in YYYY-MM-DD format"),
    user=Depends(get_current_user_ui),
):
    _require_admin(user)
    user_oid = _object_id(user_id, "user id")
    filters = [_user_filter(user_oid)]
    created_at_filter = {}
    try:
        if date_from:
            created_at_filter["$gte"] = IST.localize(datetime.strptime(date_from, "%Y-%m-%d"))
        if date_to:
            created_at_filter["$lt"] = IST.localize(datetime.strptime(date_to, "%Y-%m-%d")) + timedelta(days=1)
    except ValueError:
        raise HTTPException(status_code=400, detail="Dates must use YYYY-MM-DD format")
    if date_from and date_to and date_from > date_to:
        raise HTTPException(status_code=400, detail="From date cannot be after To date")
    if created_at_filter:
        filters.append({"created_at": created_at_filter})
    query = filters[0] if len(filters) == 1 else {"$and": filters}
    campaigns = campaigns_col.find(
        query,
        {"campaign_name": 1, "total_numbers": 1, "delivered_count": 1, "failed_count": 1, "status": 1, "created_at": 1},
    ).sort("created_at", -1)
    return {
        "items": [
            {
                "id": str(item["_id"]),
                "campaign_name": item.get("campaign_name", ""),
                "total_numbers": int(item.get("total_numbers", 0)),
                "delivered_count": int(item.get("delivered_count", 0)),
                "failed_count": int(item.get("failed_count", 0)),
                "status": item.get("status", ""),
            }
            for item in campaigns
        ]
    }


@router.post("/preview")
def preview_adjustment(payload: dict = Body(...), user=Depends(get_current_user_ui)):
    _require_admin(user)
    campaign = _load_campaign_for_user(payload.get("user_id"), payload.get("campaign_id"))
    try:
        failure_percent = float(payload.get("failure_percent"))
    except (TypeError, ValueError):
        raise HTTPException(status_code=400, detail="Failure percentage is required")
    return _preview(campaign, failure_percent)


@router.post("/apply")
def apply_adjustment(payload: dict = Body(...), user=Depends(get_current_user_ui)):
    _require_admin(user)
    campaign = _load_campaign_for_user(payload.get("user_id"), payload.get("campaign_id"))
    try:
        failure_percent = float(payload.get("failure_percent"))
    except (TypeError, ValueError):
        raise HTTPException(status_code=400, detail="Failure percentage is required")

    before = _preview(campaign, failure_percent)
    remaining = before["messages_to_change"]
    modified = 0

    while remaining > 0:
        batch_size = min(BATCH_SIZE, remaining)
        if before["direction"] == "delivered_to_failed":
            ids = [
                item["_id"]
                for item in messages_col.find(
                    {"campaign_id": campaign["_id"], "status": "delivered"},
                    {"_id": 1},
                ).sort("_id", 1).limit(batch_size)
            ]
            if not ids:
                break
            result = messages_col.update_many(
                {"_id": {"$in": ids}, "campaign_id": campaign["_id"], "status": "delivered"},
                {"$set": {"status": "failed", "vendor_dlr": "UNREACHABLE"}, "$unset": {"delivered_at": ""}},
            )
            batch_modified = result.modified_count
        elif before["direction"] == "failed_to_delivered":
            documents = _failed_documents_for_restore(campaign["_id"], batch_size)
            if not documents:
                break
            operations = []
            for document in documents:
                delivered_at = document.get("sent_at") or document.get("updated_at") or document.get("created_at")
                set_values = {
                    "status": "delivered",
                    "vendor_dlr": "FDEL : MESSAGE SENT",
                    "is_fake": True,
                }
                if delivered_at:
                    set_values["delivered_at"] = delivered_at
                operations.append(
                    UpdateOne(
                        {"_id": document["_id"], "campaign_id": campaign["_id"], "status": "failed"},
                        {"$set": set_values, "$unset": {"remarks": ""}},
                    )
                )
            result = messages_col.bulk_write(operations, ordered=False)
            batch_modified = result.modified_count
        else:
            break

        modified += batch_modified
        remaining -= batch_modified
        if batch_modified == 0:
            break

    actual_failed = messages_col.count_documents({"campaign_id": campaign["_id"], "status": "failed"})
    actual_delivered = messages_col.count_documents({"campaign_id": campaign["_id"], "status": "delivered"})
    actual_fake_delivered = messages_col.count_documents(
        {"campaign_id": campaign["_id"], "status": "delivered", "is_fake": True}
    )
    campaigns_col.update_one(
        {"_id": campaign["_id"]},
        {"$set": {
            "failed_count": actual_failed,
            "delivered_count": actual_delivered,
            "fake_delivered_count": actual_fake_delivered,
        }},
    )

    audit = {
        "campaign_id": campaign["_id"],
        "campaign_name": campaign.get("campaign_name", ""),
        "user_id": _object_id(payload.get("user_id"), "user id"),
        "failure_percent": failure_percent,
        "direction": before["direction"],
        "requested_changes": before["messages_to_change"],
        "modified_messages": modified,
        "before": before,
        "after": {
            "failed_count": actual_failed,
            "delivered_count": actual_delivered,
            "fake_delivered_count": actual_fake_delivered,
        },
        "performed_by": user["_id"],
        "performed_at": datetime.now(IST),
    }
    adjustments_col.insert_one(audit)

    if modified != before["messages_to_change"]:
        raise HTTPException(
            status_code=409,
            detail=f"Only {modified} of {before['messages_to_change']} messages were changed; counters were reconciled",
        )

    return {
        "status": "success",
        "message": (
            f"{modified} delivered messages changed to failed"
            if before["direction"] == "delivered_to_failed"
            else f"{modified} failed messages restored as delivered"
            if before["direction"] == "failed_to_delivered"
            else "Campaign already matches the requested percentages"
        ),
        "campaign_id": str(campaign["_id"]),
        "failed_count": actual_failed,
        "delivered_count": actual_delivered,
        "success_count": before["target_success"],
    }
