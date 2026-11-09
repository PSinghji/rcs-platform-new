from fastapi import APIRouter, Request, Depends, HTTPException
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from bson import ObjectId
from datetime import datetime, date
from io import StringIO
import csv
import json
import logging
import re
import pandas as pd
from io import BytesIO
from fastapi.responses import StreamingResponse
from app.database import (
    campaigns_col,
    messages_col,
    templates_col,
    user_providers_col,
    service_providers_col,
    whitelist_col,
    users_col
)
from app.dependencies_ui import get_current_user_ui
from app.redis_client import redis_client
from app.models.whitelist import whitelist_document
from app.models.campaign import campaign_document
from app.models.message import message_document
from app.utils.wallet import perform_wallet_transaction, debit_wallet , campaign_debit_transaction
from app.utils.notifications import send_campaign_alert
from app.utils.template_variables import (
    extract_template_variables,
    missing_template_variables,
    normalize_variables,
)
from datetime import datetime , timedelta
import pytz

# Define IST timezone
IST = pytz.timezone('Asia/Kolkata')
# -------------------------
# Template config
# -------------------------
templates = Jinja2Templates(directory="templates")

# -------------------------
# Router
# -------------------------
router = APIRouter(prefix="/ui/campaigns", tags=["Campaigns"])



def get_now_ist():
    """
    Forces the current time into IST regardless of server location.
    """
    return datetime.now(IST)


def format_vendor_dlr_for_viewer(vendor_dlr, current_user):
    """Keep raw vendor diagnostics for admins and mask internal prefixes for users."""
    if not vendor_dlr:
        return "-"

    role = str((current_user or {}).get("role", "")).strip().lower()
    if role == "admin":
        return vendor_dlr

    # FDEL is an internal/vendor-facing prefix and must not be exposed to users.
    if re.match(r"^\s*FDEL\s*:\s*MESSAGE\s+SENT\s*$", str(vendor_dlr), re.IGNORECASE):
        return "MESSAGE SENT"

    return vendor_dlr
# =====================================================
# GET: Create Campaign Page
# =====================================================
@router.get("/create")
def campaign_page(
    request: Request,
    current_user=Depends(get_current_user_ui)
):
    """
    Campaign creation page with strict role-based approved template visibility
    """

    tpl_query = {"status": "approved"}

    # -------------------------------
    # USER
    # -------------------------------
    # if current_user["role"] == "user":
    #     tpl_query["owner_id"] = current_user["_id"]

    # # -------------------------------
    # # RESELLER
    # # -------------------------------
    # elif current_user["role"] == "reseller":
    #     tpl_query["$or"] = [
    #         {
    #             "owner_id": current_user["_id"],
    #             "owner_role": "reseller"
    #         }
    #     ]

    # # -------------------------------
    # # ADMIN
    # # -------------------------------
    # elif current_user["role"] == "admin":
    #     pass  # admin sees all approved templates
    
    tpl_query["owner_id"] = current_user["_id"]
    # -------------------------------
    # FETCH
    # -------------------------------
    approved_templates = list(
        templates_col.find(
            tpl_query,
            {
                "name": 1,
                "template_type": 1,
                "owner_role": 1,
                "variables": 1,
                "message_mode": 1,
            }
        ).sort("created_at", -1)
    )

    # Convert ObjectId → string
    for t in approved_templates:
        # Keep templates created before personalization support compatible.
        if not t.get("variables"):
            full_template = templates_col.find_one({"_id": t["_id"]}, {"content": 1}) or {}
            t["variables"] = extract_template_variables(full_template.get("content", {}))
        t["message_mode"] = "dynamic" if t.get("variables") else "simple"
        t["_id"] = str(t["_id"])

    return templates.TemplateResponse(
        "campaigns/create.html",
        {
            "request": request,
            "templates": approved_templates,
            "user": current_user
        }
    )

# =====================================================
# POST: Create Campaign (OPTIMIZED FOR 5 LAKH PRODUCTION)
# =====================================================
logger = logging.getLogger("rcs_api")

@router.post("/create")
async def create_campaign(
    payload: dict,
    current_user=Depends(get_current_user_ui)
):
    try:
        # 1. LIGHTWEIGHT DATA EXTRACTION
        template_id = payload.get("template_id")
        raw_recipients = payload.get("recipients") or [
            {"mobile": number, "variables": {}} for number in payload.get("numbers", [])
        ]

        # Deduplicate by mobile while retaining recipient-level personalization.
        recipients_by_mobile = {}
        for item in raw_recipients:
            if not isinstance(item, dict):
                item = {"mobile": item, "variables": {}}
            mobile = re.sub(r"\D", "", str(item.get("mobile", "")))
            if len(mobile) == 12 and mobile.startswith("91"):
                mobile = mobile[2:]
            if re.fullmatch(r"[6-9]\d{9}", mobile):
                recipients_by_mobile[mobile] = {
                    "mobile": mobile,
                    "variables": normalize_variables(item.get("variables", {})),
                }
        recipients = list(recipients_by_mobile.values())
        total_messages = len(recipients)

        campaign_name = str(payload.get("campaign_name") or f"Campaign {datetime.now(IST).strftime('%Y-%m-%d %H:%M')}").strip()

        if not template_id or not recipients:
            raise HTTPException(400, "Template and recipients are required")

        duplicate_name = campaigns_col.find_one({
            "$and": [
                {"$or": [{"user_id": current_user["_id"]}, {"user_id": str(current_user["_id"])}]},
                {"campaign_name": {"$regex": f"^{re.escape(campaign_name)}$", "$options": "i"}},
            ]
        }, {"_id": 1})
        if duplicate_name:
            raise HTTPException(status_code=409, detail="Campaign name already exists for this user")
        
        template = templates_col.find_one({"_id": ObjectId(template_id), "status": "approved"})
        if not template:
            raise HTTPException(status_code=404, detail="Approved template not found")

        required_variables = template.get("variables") or extract_template_variables(template.get("content", {}))
        if required_variables:
            invalid_rows = []
            for index, recipient in enumerate(recipients, start=1):
                missing = missing_template_variables(required_variables, recipient["variables"])
                if missing:
                    invalid_rows.append(f"row {index}: {', '.join(missing)}")
                    if len(invalid_rows) >= 5:
                        break
            if invalid_rows:
                raise HTTPException(
                    status_code=400,
                    detail="Missing dynamic values (" + "; ".join(invalid_rows) + ")",
                )

        # 2. RESOLVE CREDENTIALS & SNAPSHOTS
        active_provider = current_user.get("active_provider")
        active_creds = current_user.get("provider_credentials", {}).get(active_provider, {})
        if required_variables and str(active_provider).lower() != "jio":
            raise HTTPException(
                status_code=400,
                detail="Dynamic templates are currently supported only with the Jio provider",
            )
        
        api_key = active_creds.get("api_key")
        agent_id = active_creds.get("agent_id")
        cutting_pct = float(current_user.get("cutting_percent", 0.0))
        cutting_threshold = int(current_user.get("cutting_threshold", 100))

        # 3. BILLING & CREDIT CHECK
        cost = float(current_user.get("per_message_cost", 1.0)) * total_messages
        wallet_balance = float(current_user.get("wallet_balance", 0))
        
        
        if wallet_balance < cost:
            raise HTTPException(status_code=402, detail=f"Insufficient balance. Required: {cost}")

        # 4. WALLET DEBIT
        success, message = await campaign_debit_transaction(
            current_user=current_user,
            amount=cost,
            campaign_name=campaign_name,
            debit_reason=f"Batch: {total_messages}"
        )
        if not success:
            raise HTTPException(status_code=402, detail=message)
        
        # 5. CREATE PENDING HEADER (Aligned with DB Fields)
        # We mark it 'pending' so Senders don't pick it up until Puncher finishes
        campaign_doc = campaign_document(
            user_id=current_user["_id"],
            campaign_name=campaign_name,
            template_id=template_id,
            template_name=template["name"],
            template_type=template["template_type"],
            total_numbers=total_messages,
            valid_numbers=total_messages, # Fix: required positional arg
            provider_code=active_provider,
            provider_name=str(active_provider).upper() if active_provider else "UNKNOWN", # Fix: required positional arg
            agent_id=agent_id, # Fix: required positional arg
            cutting_percent=cutting_pct,
            cutting_threshold=cutting_threshold,
            created_by=current_user["_id"],
            message_mode="dynamic" if required_variables else "simple",
            template_variables=required_variables,
        )
       
        campaign_doc["created_at"] = datetime.now(IST)
        campaign_doc["updated_at"] = datetime.now(IST)
        campaign_doc["status"] = "pending" # Prevents Sender/Puncher race conditions

        result = campaigns_col.insert_one(campaign_doc)
        campaign_id = result.inserted_id

        # Send notification email to admin about new campaign creation
        if result.inserted_id:
            send_campaign_alert(campaign_name, current_user["name"], total_messages)
        # 6. FAST CHUNKED PUSH TO REDIS
        # Offloads heavy work to the background Submitter
        chunk_size = 50000 
        for i in range(0, total_messages, chunk_size):
            batch = recipients[i : i + chunk_size]
            upload_job = {
                "campaign_id": str(campaign_id),
                "user_id": str(current_user["_id"]),
                "recipients": batch
            }
            redis_client.lpush("rcs:campaign_upload", json.dumps(upload_job))

        return {
            "status": "success",
            "message": "Campaign accepted. Processing in background.",
            "campaign_id": str(campaign_id)
        }

    except HTTPException as he:
        # Re-raise the balance/validation error so FastAPI sends 402/400 to the UI
        raise he

    except Exception as e:
        # Only catch actual code crashes here
        logger.critical(f"Critical API Error: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal Server Error")

# =====================================================
# GET: Campaign List
# =====================================================
@router.get("/list/{target_user_id}")
@router.get("/list")
def campaign_list(
    request: Request,
    target_user_id: str = None,
    current_user=Depends(get_current_user_ui)
):

    if target_user_id and current_user.get("role") == "admin":
        filter_user_id = target_user_id
        # Optional: Fetch target user details to show their name in the UI
        display_user = users_col.find_one({"_id": ObjectId(target_user_id)})
    else:
        # Default to the logged-in user's own campaigns
        filter_user_id = str(current_user["_id"])
        display_user = current_user
    
    filter_query = {
        "$or": [
            {"user_id": filter_user_id}, 
            {"user_id": ObjectId(filter_user_id)}
        ]
    }

    campaigns = list(
        campaigns_col.find(
            filter_query,
            {
                "campaign_name": 1,
                "template_name": 1,
                "provider_name": 1,
                "status": 1,
                "total_numbers": 1,
                "queued_count": 1,
                "sent_count": 1,
                "delivered_count": 1,
                "created_at": 1
            }
        ).sort("created_at", -1)
    )

    for c in campaigns:
        c["_id"] = str(c["_id"])
        c["campaign_name"] = c.get("campaign_name") or "Unnamed Campaign"
        c["provider_name"] = c.get("provider_name", "-")
        c["queued_count"] = c.get("queued_count", 0)
        c["sent_count"] = c.get("sent_count", 0)
        c["delivered_count"] = c.get("delivered_count", 0)
        c["total_numbers"] = c.get("total_numbers", 0)
        # --- IST Conversion Logic ---
        if c.get("created_at"):
            # Add 5 hours and 30 minutes to the UTC time
            ist_time = c["created_at"] + timedelta(hours=5, minutes=30)
            c["created_at"] = ist_time.strftime("%d-%m-%Y %H:%M")
        else:
            c["created_at"] = "-"

    return templates.TemplateResponse(
        "campaigns/list.html",
        {
            "request": request,
            "campaigns": campaigns,
            "user": current_user,
            "target_user": display_user
        }
    )

# =====================================================
# GET: Campaign View (Pagination + Filtering)
# =====================================================
@router.get("/view/{campaign_id}")
async def view_campaign_details(
    request: Request, 
    campaign_id: str, 
    page: int = 1, 
    limit: int = 50, 
    status: str = None,
    search: str = None,
    current_user=Depends(get_current_user_ui)
):
    page = max(1, page)
    limit = max(10, min(limit, 100))
    campaign_oid = ObjectId(campaign_id)
    campaign = campaigns_col.find_one({"_id": campaign_oid})

    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")

    query = {"campaign_id": campaign_oid}
    if status:
        query["status"] = status
    if search:
        query["mobile"] = {"$regex": search}

    total_records = messages_col.count_documents(query)
    total_pages = (total_records + limit - 1) // limit

    if total_pages > 0:
        page = min(page, total_pages)
    else:
        page = 1

    skip = (page - 1) * limit
    messages = list(messages_col.find(query).skip(skip).limit(limit).sort("_id", -1))
    
    # --- IST TIME CONVERSION FOR VIEW ---
    for m in messages:
        dt_field = m.get("updated_at") or m.get("created_at")
        if dt_field and isinstance(dt_field, datetime):
            ist_time = dt_field + timedelta(hours=5, minutes=30)
            m["display_time"] = ist_time.strftime("%d-%m-%Y %H:%M:%S")
        else:
            m["display_time"] = "-"
        m["display_vendor_dlr"] = format_vendor_dlr_for_viewer(
            m.get("vendor_dlr"), current_user
        )

    window = 2
    start_page = max(1, page - window)
    end_page = min(total_pages, page + window)

    return templates.TemplateResponse("campaigns/view.html", {
        "request": request,
        "user": current_user,
        "campaign": campaign,
        "messages": messages,
        "page": page,
        "limit": limit,
        "total_pages": total_pages,
        "total_records": total_records,
        "start_page": start_page,
        "end_page": end_page,
        "status_filter": status,
        "search_query": search,
        "total_messages": campaign.get("total_numbers", 0)
    })
# =====================================================
# GET: Export Campaign (Excel)
# =====================================================
@router.get("/export/{campaign_id}")
async def export_campaign_data(
    campaign_id: str,
    status: str = None,
    current_user=Depends(get_current_user_ui),
):
    campaign_oid = ObjectId(campaign_id)
    campaign = campaigns_col.find_one(
        {"_id": campaign_oid},
        {"template_name": 1},
    )
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")

    template_name = campaign.get("template_name") or "-"
    query = {"campaign_id": campaign_oid}
    if status:
        query["status"] = status
    
    def generate_csv():
        output = StringIO()
        writer = csv.writer(output)
        writer.writerow(["Mobile", "Status", "Template Name", "Sent Time (IST)"])
        buffered_bytes = output.tell()

        # Export order is not significant. Avoiding a full collection sort and
        # reading only required fields keeps large campaign exports responsive.
        projection = {
            "_id": 0,
            "mobile": 1,
            "status": 1,
            "updated_at": 1,
            "created_at": 1,
        }
        cursor = messages_col.find(query, projection=projection).batch_size(5000)

        for doc in cursor:
            # --- IST TIME CONVERSION FOR EXCEL ---
            raw_time = doc.get("updated_at") or doc.get("created_at")
            if raw_time and isinstance(raw_time, datetime):
                ist_time = raw_time + timedelta(hours=5, minutes=30)
                formatted_time = ist_time.strftime("%Y-%m-%d %H:%M:%S")
            else:
                formatted_time = "-"

            writer.writerow([
                doc.get("mobile"),
                str(doc.get("status", "pending")).upper(),
                template_name,
                formatted_time
            ])

            # Sending one HTTP chunk per database row is very expensive. Flush
            # a moderately sized buffer instead (roughly 256 KB).
            buffered_bytes = output.tell()
            if buffered_bytes >= 256 * 1024:
                yield output.getvalue()
                output.seek(0)
                output.truncate(0)
                buffered_bytes = 0

        if buffered_bytes:
            yield output.getvalue()
            output.truncate(0)
            output.seek(0)

    return StreamingResponse(
        generate_csv(),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename=RCS_Report_{campaign_id}.csv"}
    )
# =====================================================
# Utils (OPTIONAL)
# =====================================================
def clean_numbers_backend(lines):
    seen = set()
    valid = []

    for num in lines:
        num = num.strip().replace("+91", "")
        if num.startswith("91") and len(num) == 12:
            num = num[2:]

        if re.match(r"^[6-9]\d{9}$", num) and num not in seen:
            seen.add(num)
            valid.append(num)

    return valid

# =====================================================
# GET: Campaign Progress
# =====================================================
@router.get("/progress/{campaign_id}")
async def get_campaign_progress(campaign_id: str):
    # Fetch using exact field names from your MongoDB Compass screenshot
    campaign = campaigns_col.find_one(
        {"_id": ObjectId(campaign_id)},
        {
            "tatak_number": 1, "total_numbers": 1, 
            "submitted_count": 1, "delivered_count": 1, 
            "read_count": 1, "failed_count": 1, 
            "clicked_count": 1, "replied_count": 1, "status": 1
        }
    )
    if not campaign: return {"total": 1}

    # Standardize output keys for the Frontend
    return {
        "total": int(campaign.get("tatak_number") or campaign.get("total_numbers") or 0),
        "sent": int(campaign.get("submitted_count", 0)),
        "delivered": int(campaign.get("delivered_count", 0)),
        "read": int(campaign.get("read_count", 0)),
        "failed": int(campaign.get("failed_count", 0)),
        "clicked": int(campaign.get("clicked_count", 0)),
        "replied": int(campaign.get("replied_count", 0)),
        "status": campaign.get("status", "queued")
    }
