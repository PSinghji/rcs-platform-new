import csv
import hashlib
import io
import json
import re
import uuid
from datetime import datetime, timedelta, timezone
from io import StringIO

from bson import ObjectId
from fastapi import APIRouter, Depends, File, Form, Header, HTTPException, Path, Query, UploadFile
from fastapi.responses import StreamingResponse
from openpyxl import load_workbook
from pydantic import BaseModel
from pymongo.errors import DuplicateKeyError

from app.api_v1.dependencies import get_api_user, get_owned_campaign
from app.database import campaigns_col, db, messages_col, templates_col
from app.modules.campaigns.routes import create_campaign as create_campaign_ui


router = APIRouter(prefix="/campaigns", tags=["API Campaigns"])
api_requests_col = db.api_requests
MAX_JSON_NUMBERS = 100000
MAX_UPLOAD_NUMBERS = 500000
MAX_UPLOAD_BYTES = 20 * 1024 * 1024


class CampaignCreateRequest(BaseModel):
    campaign_name: str
    template_id: str
    numbers: list[str]


def _serialize_campaign(campaign: dict):
    return {
        "id": str(campaign["_id"]),
        "campaign_name": campaign.get("campaign_name", ""),
        "template_id": str(campaign.get("template_id", "")),
        "template_name": campaign.get("template_name", ""),
        "status": campaign.get("status", "queued"),
        "total_numbers": int(campaign.get("total_numbers", 0)),
        "queued_count": int(campaign.get("queued_count", 0)),
        "sent_count": int(campaign.get("sent_count", 0)),
        "delivered_count": int(campaign.get("delivered_count", 0)),
        "read_count": int(campaign.get("read_count", 0)),
        "clicked_count": int(campaign.get("clicked_count", 0)),
        "replied_count": int(campaign.get("replied_count", 0)),
        "failed_count": int(campaign.get("failed_count", 0)),
        "created_at": campaign.get("created_at"),
        "completed_at": campaign.get("completed_at"),
    }


def _normalize_numbers(values):
    result = []
    seen = set()
    for value in values:
        number = re.sub(r"\D", "", str(value or ""))
        if len(number) == 12 and number.startswith("91"):
            number = number[2:]
        if re.fullmatch(r"[6-9]\d{9}", number) and number not in seen:
            seen.add(number)
            result.append(number)
    return result


def _read_uploaded_numbers(filename: str, content: bytes):
    suffix = (filename or "").lower().rsplit(".", 1)[-1]
    if suffix == "xlsx":
        try:
            workbook = load_workbook(io.BytesIO(content), read_only=True, data_only=True)
            worksheet = workbook.worksheets[0]
            rows = worksheet.iter_rows(values_only=True)
            header = next(rows, None)
            if not header:
                raise HTTPException(status_code=400, detail="Excel file is empty")
            normalized_headers = [str(value or "").strip().lower() for value in header]
            try:
                mobile_column = normalized_headers.index("mobile")
            except ValueError:
                raise HTTPException(status_code=400, detail='Excel file must contain a "Mobile" column in the first row')
            return [row[mobile_column] for row in rows if mobile_column < len(row)]
        except HTTPException:
            raise
        except Exception:
            raise HTTPException(status_code=400, detail="Invalid XLSX file")

    if suffix not in {"csv", "txt"}:
        raise HTTPException(status_code=400, detail="Number file must be CSV, TXT, or XLSX")
    try:
        text = content.decode("utf-8-sig")
    except UnicodeDecodeError:
        raise HTTPException(status_code=400, detail="CSV or TXT file must use UTF-8 encoding")
    values = []
    for row in csv.reader(io.StringIO(text)):
        values.extend(row)
    return values


def _validate_template(template_id: str):
    try:
        template = templates_col.find_one({"_id": ObjectId(template_id), "status": "approved"})
    except Exception:
        template = None
    if not template:
        raise HTTPException(status_code=400, detail="Approved template not found")
    return template


def _idempotency_fingerprint(campaign_name: str, template_id: str, numbers: list[str]):
    digest = hashlib.sha256()
    digest.update(campaign_name.strip().encode())
    digest.update(template_id.encode())
    for number in numbers:
        digest.update(number.encode())
        digest.update(b"\n")
    return digest.hexdigest()


def _reserve_request(user: dict, key: str, fingerprint: str):
    if not 8 <= len(key) <= 128:
        raise HTTPException(status_code=400, detail="Idempotency-Key must contain 8 to 128 characters")
    api_requests_col.create_index([("user_id", 1), ("key", 1)], unique=True)
    document = {
        "user_id": user["_id"],
        "key": key,
        "fingerprint": fingerprint,
        "status": "processing",
        "created_at": datetime.now(timezone.utc),
    }
    try:
        api_requests_col.insert_one(document)
        return None
    except DuplicateKeyError:
        existing = api_requests_col.find_one({"user_id": user["_id"], "key": key})
        if existing.get("fingerprint") != fingerprint:
            raise HTTPException(status_code=409, detail="Idempotency-Key was already used for a different request")
        if existing.get("status") == "completed":
            return existing.get("response")
        raise HTTPException(status_code=409, detail="An identical campaign request is already processing")


async def _create_campaign(
    campaign_name: str,
    template_id: str,
    numbers: list[str],
    idempotency_key: str | None,
    user: dict,
):
    campaign_name = campaign_name.strip()
    if not campaign_name:
        raise HTTPException(status_code=400, detail="Campaign name is required")
    _validate_template(template_id)
    if not numbers:
        raise HTTPException(status_code=400, detail="No valid mobile numbers were supplied")

    # API consumers may provide a stable key when they want safe retry semantics.
    # For normal interactive use, generate one so callers are not forced to do it.
    idempotency_key = (idempotency_key or "").strip() or str(uuid.uuid4())

    fingerprint = _idempotency_fingerprint(campaign_name, template_id, numbers)
    previous_response = _reserve_request(user, idempotency_key, fingerprint)
    if previous_response:
        return previous_response

    try:
        response = await create_campaign_ui(
            {
                "campaign_name": campaign_name,
                "template_id": template_id,
                "numbers": numbers,
            },
            current_user=user,
        )
        if isinstance(response, dict):
            response["idempotency_key"] = idempotency_key
        api_requests_col.update_one(
            {"user_id": user["_id"], "key": idempotency_key},
            {"$set": {"status": "completed", "response": response, "completed_at": datetime.now(timezone.utc)}},
        )
        return response
    except Exception:
        api_requests_col.delete_one({"user_id": user["_id"], "key": idempotency_key, "status": "processing"})
        raise


@router.post("", status_code=202, include_in_schema=False)
async def create_campaign_json(
    data: CampaignCreateRequest,
    idempotency_key: str | None = Header(
        default=None,
        alias="Idempotency-Key",
        description="Optional retry key. A UUID is generated automatically when omitted.",
    ),
    user=Depends(get_api_user),
):
    if len(data.numbers) > MAX_JSON_NUMBERS:
        raise HTTPException(
            status_code=413,
            detail=f"JSON requests support at most {MAX_JSON_NUMBERS} numbers; use /campaigns/upload",
        )
    numbers = _normalize_numbers(data.numbers)
    return await _create_campaign(data.campaign_name, data.template_id, numbers, idempotency_key, user)


@router.post(
    "/upload",
    status_code=202,
    summary="Create Campaign From File",
    description=(
        "Upload CSV, TXT, or XLSX mobile numbers. For XLSX, the first worksheet must contain a Mobile column. "
        "The server generates an idempotency key automatically when the optional header is omitted."
    ),
    responses={
        202: {
            "description": "Campaign accepted",
            "content": {"application/json": {"example": {
                "status": "success",
                "message": "Campaign accepted. Processing in background.",
                "campaign_id": "64f1234567890abcdef12345",
                "idempotency_key": "7d031802-58cb-4ed3-a047-6a850ab4354e",
            }}},
        },
        400: {"description": "Invalid template or number file"},
        401: {"description": "Bearer token missing, invalid, or expired"},
        402: {"description": "Insufficient wallet balance"},
        413: {"description": "File or unique-number limit exceeded"},
    },
)
async def create_campaign_upload(
    campaign_name: str = Form(..., description="Unique campaign display name"),
    template_id: str = Form(..., description="Approved template id returned by GET /api/v1/templates/approved"),
    numbers_file: UploadFile = File(
        ...,
        description='CSV/TXT file containing numbers, or XLSX file with a "Mobile" column in the first worksheet.',
    ),
    idempotency_key: str | None = Header(
        default=None,
        alias="Idempotency-Key",
        description="Optional retry key. A UUID is generated automatically when omitted.",
    ),
    user=Depends(get_api_user),
):
    content = await numbers_file.read(MAX_UPLOAD_BYTES + 1)
    if len(content) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="Number file exceeds the 20 MB limit")
    values = _read_uploaded_numbers(numbers_file.filename or "", content)
    numbers = _normalize_numbers(values)
    if len(numbers) > MAX_UPLOAD_NUMBERS:
        raise HTTPException(status_code=413, detail=f"A campaign supports at most {MAX_UPLOAD_NUMBERS} unique numbers")
    return await _create_campaign(campaign_name, template_id, numbers, idempotency_key, user)


@router.get("", include_in_schema=False)
def list_campaigns(
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    status: str = Query(default=None),
    user=Depends(get_api_user),
):
    ownership = {
        "$or": [
            {"user_id": user["_id"]},
            {"user_id": str(user["_id"])},
        ]
    }
    query = {"$and": [ownership, {"status": status}]} if status else ownership
    cursor = campaigns_col.find(query).sort("created_at", -1).skip(offset).limit(limit)
    return {
        "items": [_serialize_campaign(item) for item in cursor],
        "limit": limit,
        "offset": offset,
        "total": campaigns_col.count_documents(query),
    }


@router.get("/{campaign_id}", include_in_schema=False)
def get_campaign(campaign_id: str, user=Depends(get_api_user)):
    return _serialize_campaign(get_owned_campaign(campaign_id, user))


@router.get(
    "/{campaign_id}/status",
    summary="Get Campaign Status",
    description="Return the current processing and delivery totals for an authorized campaign.",
)
def get_campaign_status(
    campaign_id: str = Path(..., description="Campaign id returned by POST /api/v1/campaigns/upload"),
    user=Depends(get_api_user),
):
    campaign = get_owned_campaign(campaign_id, user)
    return _serialize_campaign(campaign)


@router.get(
    "/{campaign_id}/report",
    summary="Download Campaign Report",
    description="Download the campaign report as CSV. The Bearer token is required.",
    responses={200: {"description": "CSV report file"}},
)
def download_campaign_report(
    campaign_id: str = Path(..., description="Campaign id returned by POST /api/v1/campaigns/upload"),
    status: str = Query(default=None, description="Optional message status filter, for example delivered, failed, or read"),
    user=Depends(get_api_user),
):
    campaign = get_owned_campaign(campaign_id, user)
    query = {"campaign_id": campaign["_id"]}
    if status:
        query["status"] = status
    template_name = campaign.get("template_name") or "-"

    def generate_csv():
        output = StringIO()
        writer = csv.writer(output)
        writer.writerow(["Mobile", "Status", "Template Name", "Sent Time (IST)"])
        projection = {
            "_id": 0,
            "mobile": 1,
            "status": 1,
            "updated_at": 1,
            "created_at": 1,
        }
        cursor = messages_col.find(query, projection=projection).batch_size(5000)
        for message in cursor:
            raw_time = message.get("updated_at") or message.get("created_at")
            if raw_time and isinstance(raw_time, datetime):
                formatted_time = (raw_time + timedelta(hours=5, minutes=30)).strftime("%Y-%m-%d %H:%M:%S")
            else:
                formatted_time = "-"
            writer.writerow([
                message.get("mobile"),
                str(message.get("status", "pending")).upper(),
                template_name,
                formatted_time,
            ])
            if output.tell() >= 256 * 1024:
                yield output.getvalue()
                output.seek(0)
                output.truncate(0)
        if output.tell():
            yield output.getvalue()

    return StreamingResponse(
        generate_csv(),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename=RCS_Report_{campaign_id}.csv"},
    )
