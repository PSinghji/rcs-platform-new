import datetime
try:
    import zoneinfo
except ImportError:
    # For older Python versions, though Ubuntu 24.04 includes it
    from backports import zoneinfo 

from bson import ObjectId
from app.database import db, messages_col, campaigns_col, users_col
from app.utils.wallet import perform_wallet_transaction

async def run_nightly_campaign_refunds():
    # 1. Align Timezones: Convert IST "Today" to UTC for MongoDB
    tz_ist = zoneinfo.ZoneInfo("Asia/Kolkata")
    now_ist = datetime.datetime.now(tz_ist)
    
    # Start of today (00:00:00 IST)
    today_start_ist = now_ist.replace(hour=0, minute=0, second=0, microsecond=0)
    # End of today (23:59:59 IST)
    today_end_ist = now_ist.replace(hour=23, minute=59, second=59, microsecond=999999)

    # Convert to UTC-naive objects for MongoDB compatibility
    query_start_utc = today_start_ist.astimezone(datetime.timezone.utc).replace(tzinfo=None)
    query_end_utc = today_end_ist.astimezone(datetime.timezone.utc).replace(tzinfo=None)

    print(f"Checking refunds for IST Range: {today_start_ist} to {today_end_ist}")
    
    # Identify the System Admin
    system_actor = users_col.find_one({"role": "admin"}) 
    if not system_actor:
        print("Error: No system admin found to act as transaction source.")
        return

    # 2. Aggregation Pipeline
    pipeline = [
        {
            "$match": {
                "status": "failed",
                "created_at": {
                    "$gte": query_start_utc, 
                    "$lte": query_end_utc
                },
                "refunded": {"$ne": True}
            }
        },
        {
            "$lookup": {
                "from": "campaigns",
                "localField": "campaign_id",
                "foreignField": "_id",
                "as": "camp"
            }
        },
        {"$unwind": "$camp"},
        {
            "$lookup": {
                "from": "users",
                "localField": "user_id",
                "foreignField": "_id",
                "as": "user"
            }
        },
        {"$unwind": "$user"},
        {
            "$match": { "user.refund_enabled": True }
        },
        {
            "$group": {
                "_id": {
                    "user_id": "$user_id",
                    "campaign_id": "$campaign_id",
                    "campaign_name": "$camp.campaign_name"
                },
                "total_refund": {"$sum": 1}, 
                "message_ids": {"$push": "$_id"}
            }
        }
    ]

    # Convert cursor to list
    refund_queue = list(messages_col.aggregate(pipeline))

    if not refund_queue:
        print(f"[{datetime.datetime.now()}] No failed messages found for refund today.")
        return

    for entry in refund_queue:
        u_id = entry["_id"]["user_id"]
        c_name = entry["_id"]["campaign_name"]
        amount = float(entry["total_refund"]) 
        m_ids = entry["message_ids"]

        # 3. Perform Transaction
        reason = f"Campaign Refund: {c_name} ({int(amount)} failed messages)"
        
        success, status_msg = await perform_wallet_transaction(
            target_user_id=u_id,
            actor_user=system_actor,
            amount=amount,
            action="credit",
            reason=reason
        )

        if success:
            # 4. Mark messages as 'refunded' using UTC time for consistency
            messages_col.update_many(
                {"_id": {"$in": m_ids}},
                {"$set": {
                    "refunded": True, 
                    "refunded_at": datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None)
                }}
            )
            print(f"SUCCESS: Refunded ₹{amount} to User {u_id} for Campaign '{c_name}'")
        else:
            print(f"FAILED: Could not refund {u_id} for {c_name}: {status_msg}")

if __name__ == "__main__":
    import asyncio
    asyncio.run(run_nightly_campaign_refunds())