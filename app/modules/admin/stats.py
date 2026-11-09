from fastapi import APIRouter, Depends, Request
from datetime import datetime, timedelta
from app.database import users_col, campaigns_col , transactions_col,messages_col, wallet_ledger_col
from bson import ObjectId


router = APIRouter(prefix="/api/admin")


async def get_all_child_ids(parent_id: str):
    """Recursively fetch all user IDs under a specific Reseller."""
    child_ids = []
    # Find direct children
    children = await users_col.find({"parent_id": parent_id}).to_list(None)
    for child in children:
        c_id = str(child["_id"])
        child_ids.append(c_id)
        # Recursive call for deeper hierarchy levels
        child_ids.extend(await get_all_child_ids(c_id))
    return child_ids

@router.get("/api/admin/dashboard-stats")
async def get_dashboard_stats(period: str = "today", user_id: str = None):
    # 1. Date Range Handling
    now = datetime.utcnow()
    start_date = now.replace(hour=0, minute=0, second=0, microsecond=0)
    
    if period == "yesterday":
        start_date -= timedelta(days=1)
        end_date = start_date + timedelta(days=1)
    elif period == "7days":
        start_date -= timedelta(days=7)
        end_date = now
    else: # today
        end_date = now

    # 2. Hierarchy Filter Logic
    target_user_ids = []
    if user_id:
        target_user_ids = [user_id] + await get_all_child_ids(user_id)
        match_query = {"user_id": {"$in": target_user_ids}} # Adjust key if needed (e.g., 'created_by')
    else:
        match_query = {} # Global view

    # 3. Campaign Aggregation
    camp_query = {**match_query, "created_at": {"$gte": start_date, "$lt": end_date}}
    campaign_stats = await campaigns_col.aggregate([
        {"$match": camp_query},
        {"$group": {
            "_id": None,
            "count": {"$sum": 1},
            "total_mobile": {"$sum": "$total_recipients"},
            "failed": {"$sum": "$failed_count"},
            "rcs": {"$sum": "$delivered_count"},
            "cutting": {"$sum": "$cutting_extra_count"}
        }}
    ]).to_list(1)

    # 4. Wallet Aggregation
    wallet_query = {**match_query, "created_at": {"$gte": start_date, "$lt": end_date}}
    wallet_stats = await wallet_ledger_col.aggregate([
        {"$match": wallet_query},
        {"$group": {"_id": "$type", "total": {"$sum": "$amount"}}}
    ]).to_list(None)

    return {
        "users": {
            "total": await users_col.count_documents({"role": "user"}),
            "resellers": await users_col.count_documents({"role": "reseller"})
        },
        "campaigns": campaign_stats[0] if campaign_stats else {"count":0, "total_mobile":0, "failed":0, "rcs":0, "cutting":0},
        "wallet": {item["_id"]: item["total"] for item in wallet_stats}
    }