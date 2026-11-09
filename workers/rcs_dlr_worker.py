import json
import sys
import logging
import re
import time
import pytz
from datetime import datetime
from collections import defaultdict
from pymongo import UpdateOne
from app.redis_client import redis_client
from app.database import messages_col, campaigns_col

# --- LOGGING SETUP ---
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] (DLR-WORKER) %(message)s',
    handlers=[logging.StreamHandler(sys.stdout), logging.FileHandler("/var/log/rcs_dlr_highspeed.log")]
)
logger = logging.getLogger("RCS_DLR")

# --- CONFIGURATION ---
IST = pytz.timezone('Asia/Kolkata')
QUEUE = "rcs:dlr_queue"
BATCH_SIZE = 1000       
BATCH_TIMEOUT = 0.5     

# Priority logic: Status can only move UP (e.g., Read cannot revert to Delivered)
STATUS_PRIORITY = {
    "submitted": 1,
    "delivered": 2,
    "read": 3,
    "clicked": 4, 
    "replied": 5, 
    "failed": 6,   
}

# Mapping Jio Events to Internal Status
EVENT_MAP = {
    "SEND_MESSAGE_SUCCESS": "submitted",
    "MESSAGE_DELIVERED": "delivered",
    "MESSAGE_READ": "read",
    "SEND_MESSAGE_FAILURE": "failed",
    "TTL_EXPIRATION_REVOKED": "failed"
}

# Map internal status to Campaign Collection field names
BUCKET_MAP = {
    "submitted": "submitted_count",
    "delivered": "delivered_count",
    "read": "read_count",
    "clicked": "clicked_count",
    "replied": "replied_count",
    "failed": "failed_count"
}

def get_now_ist():
    return datetime.now(IST)

def clean_mobile_exact(phone):
    if not phone: return None
    digits = re.sub(r'\D', '', str(phone))
    return digits[-10:] if len(digits) >= 10 else digits

def parse_dlr_packet(raw_json_str):
    parsed_updates = []
    try:
        raw_data = json.loads(raw_json_str)
        
        # 1. Handle Batch Reachability (Jio specific)
        if "reachableUsers" in raw_data or "unReachableUsers" in raw_data:
            batch_id = raw_data.get("messageId")
            for mob in raw_data.get("reachableUsers") or []:
                parsed_updates.append({"msg_id": batch_id, "mobile": clean_mobile_exact(mob), "status": "submitted", "remark": "REACHABLE"})
            for mob in raw_data.get("unReachableUsers") or []:
                parsed_updates.append({"msg_id": batch_id, "mobile": clean_mobile_exact(mob), "status": "failed", "remark": "UNREACHABLE"})
            return parsed_updates

        entity = raw_data.get("entity", {})
        batch_id = entity.get("messageId") or raw_data.get("messageId")
        phone = clean_mobile_exact(raw_data.get("userPhoneNumber"))
        
        # 2. Handle USER INTERACTIONS (Clicks & Replies)
        if raw_data.get("entityType") == "USER_MESSAGE":
            sugg = entity.get("suggestionResponse")
            if sugg:
                s_type = sugg.get("type") # ACTION or REPLY
                btn_text = sugg.get("plainText") or "Interacted"
                # If it's a URL/Call action, we call it 'clicked'
                # If it's a suggested reply button, we call it 'replied'
                status = "clicked" if s_type == "ACTION" else "replied"
                parsed_updates.append({"msg_id": batch_id, "mobile": phone, "status": status, "remark": f"{s_type}: {btn_text}"})
            elif entity.get("text"):
                # Captures direct typed text from user
                parsed_updates.append({"msg_id": batch_id, "mobile": phone, "status": "replied", "remark": f"TEXT: {entity.get('text')[:30]}"})

        # 3. Handle Standard Delivery Events
        else:
            event_type = entity.get("eventType")
            status = EVENT_MAP.get(event_type)
            if status:
                remark = event_type
                if status == "failed":
                    err = entity.get("error", {})
                    remark = f"FAIL: {err.get('message') or 'Provider Error'}"
                parsed_updates.append({"msg_id": batch_id, "mobile": phone, "status": status, "remark": remark})
                
    except Exception as e:
        logger.error(f"Parse Error: {e}")
    return parsed_updates

def flush_batch(updates_list):
    if not updates_list: return
    try:
        bulk_msg_ops = []
        camp_adj = defaultdict(lambda: defaultdict(int))
        now = get_now_ist()
        
        # Pre-fetch existing records to determine the "From" bucket
        lookup_filters = [{"jio_msg_id": u['msg_id'], "mobile": u['mobile']} for u in updates_list if u['msg_id']]
        if not lookup_filters: return

        current_map = {}
        # Optimization: Only fetch status and campaign_id
        for doc in messages_col.find({"$or": lookup_filters}, {"jio_msg_id": 1, "mobile": 1, "status": 1, "campaign_id": 1, "is_fake": 1}):
            current_map[f"{doc['jio_msg_id']}_{doc['mobile']}"] = doc

        for item in updates_list:
            key = f"{item['msg_id']}_{item['mobile']}"
            existing = current_map.get(key)
            if not existing: continue
            # Artificial deliveries must remain controlled by the cutting/report
            # adjustment logic and must not be changed by late provider DLRs.
            if existing.get("is_fake", False):
                continue

            old_st = existing.get("status", "submitted")
            new_st = item['status']
            c_id = existing['campaign_id']

            # 1. PRIORITY CHECK: Prevent status downgrading
            if STATUS_PRIORITY.get(new_st, 0) <= STATUS_PRIORITY.get(old_st, 0):
                continue
            
            existing["status"] = new_st
            
            # 2. UPDATE MESSAGE RECORD
            bulk_msg_ops.append(UpdateOne(
                {"_id": existing["_id"]},
                {"$set": {
                    "status": new_st, 
                    "updated_at": now, 
                    "vendor_dlr": item['remark'],
                    # Log specific interaction times for reporting
                    **( {"clicked_at": now} if new_st == "clicked" else {} ),
                    **( {"replied_at": now} if new_st == "replied" else {} )
                }}
            ))

            # 3. PROGRESSIVE BUCKET SHIFTING (The "Movement" Logic)
            # Remove -1 from the current bucket
            if old_st in BUCKET_MAP:
                camp_adj[c_id][BUCKET_MAP[old_st]] -= 1
            
            # Add +1 to the new bucket
            if new_st in BUCKET_MAP:
                camp_adj[c_id][BUCKET_MAP[new_st]] += 1

        # Execute Multi-User Safe Atomic Updates
        if bulk_msg_ops:
            messages_col.bulk_write(bulk_msg_ops, ordered=False)
        
        if camp_adj:
            # We use $inc to shift counts between buckets in one atomic operation
            camp_ops = [
                UpdateOne({"_id": cid}, {"$inc": adj, "$set": {"updated_at": now}}) 
                for cid, adj in camp_adj.items()
            ]
            campaigns_col.bulk_write(camp_ops, ordered=False)
            logger.info(f"📊 Processed {len(bulk_msg_ops)} DLRs across {len(camp_adj)} Campaigns.")

    except Exception as e:
        logger.error(f"Flush Error: {e}")

def process_worker():
    logger.info("🚀 High-Speed DLR & Interaction Worker Started | Zone: Kolkata IST")
    buffer = []
    last_flush = time.time()
    while True:
        try:
            # Batch fetch from Redis for high throughput
            pipe = redis_client.pipeline()
            pipe.lrange(QUEUE, 0, BATCH_SIZE - 1)
            pipe.ltrim(QUEUE, BATCH_SIZE, -1)
            results = pipe.execute()
            
            for raw in results[0]:
                buffer.extend(parse_dlr_packet(raw))

            # Flush based on batch size or time timeout
            if buffer and (len(buffer) >= BATCH_SIZE or (time.time() - last_flush) > BATCH_TIMEOUT):
                flush_batch(buffer)
                buffer = []
                last_flush = time.time()
            
            if not results[0]: time.sleep(0.5) 
        except Exception as e:
            logger.error(f"Worker Loop Error: {e}"); time.sleep(2)

if __name__ == "__main__":
    process_worker()
