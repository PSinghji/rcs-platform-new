import json
import time
import sys
import os
import uuid
import logging
import pytz  
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor
from bson import ObjectId
from pymongo import UpdateOne

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Import database collections
from app.database import users_col, messages_col, campaigns_col, templates_col
from workers.providers.jio import JioAdapter
from workers.providers.dovesoft import DoveSoftAdapter

# --- CONFIGURATION ---
IST = pytz.timezone('Asia/Kolkata')
BATCH_SIZE = 2000         
JIO_CHUNK_SIZE = 50       
THREAD_WORKERS = 50       
WORKER_ID = f"sender_{uuid.uuid4().hex[:6]}"

# --- LOGGING ---
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] [%(threadName)s] %(message)s',
    handlers=[logging.StreamHandler(sys.stdout), logging.FileHandler("/var/log/rcs_sender.log")]
)
logger = logging.getLogger("rcs_sender")

class AdapterFactory:
    @staticmethod
    def get_adapter(service_type):
        adapters = {
            "jio": JioAdapter(),
            "dovesoft": DoveSoftAdapter(),
            # Add more as you grow
        }
        # Default to Jio if service_type is missing or unknown
        return adapters.get(service_type.lower(), JioAdapter())


CACHE = {"campaign_id": None, "user": None, "template": None, "campaign": None}

# Helper to ensure all DB timestamps are IST
def get_now_ist():
    return datetime.now(IST)

def check_campaign_completion(campaign_id):
    """
    Checks if processed messages equal tatak_number or total_numbers.
    """
    # Fetch all relevant counters and both potential 'total' fields
    now_ist = datetime.now(IST).replace(tzinfo=None)
    campaign = campaigns_col.find_one(
        {"_id": campaign_id}, 
        {
            "tatak_number": 1, 
            "total_numbers": 1, 
            "submitted_count": 1, 
            "delivered_count": 1, 
            "failed_count": 1,
            "punched_count": 1  # Add this if you use it for tracking
        }
    )
    if not campaign: return

    # Determine total audience (check both tatak_number and total_numbers)
    total_audience = int(campaign.get("tatak_number") or campaign.get("total_numbers") or 0)
    
    # Calculate processed count accurately
    # Option A: If you use individual buckets
    processed_buckets = (int(campaign.get("submitted_count", 0)) + 
                         int(campaign.get("delivered_count", 0)) + 
                         int(campaign.get("failed_count", 0)))
    
    # Option B: If you use a single punched_count field
    punched = int(campaign.get("punched_count", 0))

    # Use whichever method matches your database updates
    final_count = max(processed_buckets, punched)

    if final_count >= total_audience and total_audience > 0:
        campaigns_col.update_one(
            {"_id": campaign_id},
            {"$set": {
                "status": "completed", # Change this to 'completed'
                "completed_at": now_ist,
                "updated_at": now_ist
            }}
        )
        logger.info(f"✅ Campaign {campaign_id} marked as COMPLETED ({final_count}/{total_audience})")

def get_cached_data(campaign_id_obj, user_id_obj):
    c_id_str = str(campaign_id_obj)
    if CACHE["campaign_id"] != c_id_str:
        campaign = campaigns_col.find_one({"_id": campaign_id_obj})
        user = users_col.find_one({"_id": user_id_obj})
        template = None
        if campaign:
            template = templates_col.find_one({"_id": ObjectId(campaign["template_id"])})
        
        CACHE.update({
            "campaign_id": c_id_str, "campaign": campaign, "user": user, "template": template
        })
    return CACHE["user"], CACHE["template"], CACHE["campaign"]

def process_chunk(msg_chunk, user, template, campaign):
    now = get_now_ist()
    real_messages = []
    fake_ids = []
    
    service_type = campaign.get("provider_code", "jio")
    current_adapter = AdapterFactory.get_adapter(service_type)

    for msg in msg_chunk:
        # New campaigns receive an exact campaign-level cutting assignment in
        # the producer. Legacy campaigns keep the previous selection behavior
        # so already queued work is not changed during deployment.
        if "cutting_target" in campaign:
            should_cut = bool(msg.get("is_fake", False)) and not msg.get("is_whitelisted", False)
        else:
            cutting_percent = float(campaign.get("cutting_percent", 0.0))
            threshold = 100 - cutting_percent
            val = int(str(msg["_id"])[-4:], 16) % 100
            should_cut = not msg.get("is_whitelisted", False) and val >= threshold

        if should_cut:
            fake_ids.append(msg["_id"])
        else:
            real_messages.append(msg)

    if fake_ids:
        messages_col.bulk_write([
            UpdateOne({"_id": _id}, {"$set": {
                "status": "delivered", "is_fake": True, "vendor_dlr": "FDEL : MESSAGE SENT",
                "sent_at": now, "delivered_at": now
            }}) for _id in fake_ids
        ], ordered=False)
        campaigns_col.update_one(
            {"_id": campaign["_id"]},
            {"$inc": {"delivered_count": len(fake_ids), "fake_delivered_count": len(fake_ids)}}
        )

    if real_messages:
        mobiles = [str(m["mobile"]).strip() for m in real_messages]
        msg_ids = [str(m["_id"]) for m in real_messages]
        creds = user.get("provider_credentials", {}).get(user.get("active_provider"), {})

        try:
            status_code, resp = current_adapter.send_bulk_messages(
                credentials={"api_key": creds.get("api_key"), "agent_id": creds.get("agent_id")},
                mobiles=mobiles,
                payload=template.get("content"),
                message_ids=msg_ids
            )

            if status_code == 200:
                # 1. Dynamically determine the ID field and the message ID value
                # Some APIs use messageId, others messageID, or vendor-specific keys
                vendor_msg_id = resp.get("messageId") or resp.get("messageID") or msg_ids[0]
                
                # Use a generic field or a dynamic one like 'jio_msg_id' vs 'dovesoft_msg_id'
                id_field_name = f"{service_type.lower()}_msg_id" 
                
                messages_col.bulk_write([
                    UpdateOne({"_id": m["_id"]}, {"$set": {
                        "status": "submitted", 
                        "sent_at": now, 
                        id_field_name: vendor_msg_id, 
                        "remarks": f"API_{service_type.upper()}_ACCEPTED"
                    }}) for m in real_messages
                ], ordered=False)
                
                campaigns_col.update_one(
                    {"_id": campaign["_id"]}, 
                    {"$inc": {"submitted_count": len(real_messages)}}
                )
            
            else:
                # 2. Dynamically extract the error message
                # Jio uses 'fault', DoveSoft might return a 'message' or 'error' key
                error = (
                    resp.get("fault", {}).get("faultstring") or 
                    resp.get("message") or 
                    resp.get("error") or 
                    f"{service_type.upper()} Rejected"
                )
                
                messages_col.bulk_write([
                    UpdateOne({"_id": m["_id"]}, {"$set": {
                        "status": "failed", 
                        "error_reason": error, 
                        "remarks": f"{service_type.upper()}_REJECTED"
                    }}) for m in real_messages
                ], ordered=False)
                
                campaigns_col.update_one(
                    {"_id": campaign["_id"]}, 
                    {"$inc": {"failed_count": len(real_messages)}}
                )
        
        except Exception as e:
            logger.error(f"API Error: {e}")
            messages_col.update_many(
                {"_id": {"$in": [m["_id"] for m in real_messages]}},
                {"$set": {"status": "failed", "error_reason": str(e)}}
            )
            campaigns_col.update_one({"_id": campaign["_id"]}, {"$inc": {"failed_count": len(real_messages)}})

    check_campaign_completion(campaign["_id"])

def main_loop():
    logger.info(f"🚀 Sender ID: {WORKER_ID} | Threads: {THREAD_WORKERS} | Zone: Kolkata IST")
    
    while True:
        try:
            # 1. Fetch IDs to lock
            cursor = messages_col.find({"status": "queued"}, {"_id": 1, "campaign_id": 1, "user_id": 1}).limit(BATCH_SIZE)
            batch_initial = list(cursor)
            ids = [d["_id"] for d in batch_initial]

            if not ids:
                time.sleep(5); continue

            # 2. ATOMIC LOCKING
            lock_res = messages_col.update_many(
                {"_id": {"$in": ids}, "status": "queued"},
                {"$set": {"status": "processing", "locked_by": WORKER_ID, "updated_at": get_now_ist()}}
            )

            if lock_res.modified_count == 0:
                continue

            # 3. FETCH DATA & VALIDATE
            batch = list(messages_col.find({"locked_by": WORKER_ID, "status": "processing"}))
            if not batch: continue

            # A locked batch can contain multiple campaigns. Process each group
            # with its own user, template, provider and cutting snapshot.
            campaign_groups = {}
            for message in batch:
                campaign_groups.setdefault(
                    (message["campaign_id"], message.get("user_id")), []
                ).append(message)

            for (campaign_id, user_id), campaign_messages in campaign_groups.items():
                user, template, campaign = get_cached_data(campaign_id, user_id)

                if not campaign or not user or not template:
                    logger.error(f"Missing configuration for Campaign ID: {campaign_id}")
                    missing_ids = [message["_id"] for message in campaign_messages]
                    messages_col.update_many(
                        {"_id": {"$in": missing_ids}, "status": "processing"},
                        {"$set": {"status": "failed", "error_reason": "Missing Config"}}
                    )
                    campaigns_col.update_one(
                        {"_id": campaign_id},
                        {"$inc": {"failed_count": len(missing_ids)}}
                    )
                    continue

                campaigns_col.update_one(
                    {"_id": campaign["_id"], "status": "queued"},
                    {"$set": {"status": "processing", "updated_at": get_now_ist()}}
                )

                chunks = [
                    campaign_messages[i : i + JIO_CHUNK_SIZE]
                    for i in range(0, len(campaign_messages), JIO_CHUNK_SIZE)
                ]
                with ThreadPoolExecutor(
                    max_workers=THREAD_WORKERS,
                    thread_name_prefix=f"{WORKER_ID}_T"
                ) as executor:
                    futures = [
                        executor.submit(process_chunk, chunk, user, template, campaign)
                        for chunk in chunks
                    ]
                    for future in futures:
                        future.result()

                check_campaign_completion(campaign["_id"])
            
            # 5. FINAL CLEANUP (IMPROVED)
            # Step A: Release locks for successfully processed messages
            messages_col.update_many(
                {"locked_by": WORKER_ID, "status": {"$in": ["submitted", "delivered", "failed"]}},
                {"$set": {"locked_by": None}} 
            )

            # Step B: Catch any messages that got stuck (e.g., if a thread crashed) and mark them as failed
            stuck = list(messages_col.find(
                {"locked_by": WORKER_ID, "status": "processing"},
                {"_id": 1, "campaign_id": 1}
            ))
            stuck_by_campaign = {}
            for message in stuck:
                stuck_by_campaign.setdefault(message["campaign_id"], []).append(message["_id"])

            for campaign_id, stuck_ids in stuck_by_campaign.items():
                failed_cleanup = messages_col.update_many(
                    {"_id": {"$in": stuck_ids}, "status": "processing"},
                    {"$set": {
                        "status": "failed",
                        "locked_by": None,
                        "error_reason": "Worker thread crashed before completion"
                    }}
                )
                if failed_cleanup.modified_count > 0:
                    campaigns_col.update_one(
                        {"_id": campaign_id},
                        {"$inc": {"failed_count": failed_cleanup.modified_count}}
                    )

        except Exception as e:
            logger.exception(f"🔥 Worker {WORKER_ID} Crash: {e}")
            time.sleep(5)

if __name__ == "__main__":
    try:
        main_loop()
    except KeyboardInterrupt:
        logger.info("Worker stopped by user.")
    except Exception as e:
        logger.critical(f"Worker died unexpectedly: {e}")
