import json
import logging
import os
import sys
import time
from datetime import datetime

import pytz
from bson import ObjectId

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.database import campaigns_col, messages_col, whitelist_col
from app.redis_client import redis_client


IST = pytz.timezone("Asia/Kolkata")
logging.basicConfig(level=logging.INFO, format="%(asctime)s [PUNCHER] %(message)s")
logger = logging.getLogger("Puncher")


def process_job(data):
    recipients = data.get("recipients") or [
        {"mobile": number, "variables": {}} for number in data.get("numbers", [])
    ]
    campaign_id_text = data.get("campaign_id")
    user_id_text = data.get("user_id")

    if not recipients or not campaign_id_text:
        return

    campaign_id = ObjectId(campaign_id_text)
    user_id = ObjectId(user_id_text) if user_id_text else None

    # Multiple producer services run in production. Serialize jobs only for the
    # same campaign so threshold positions and the exact cutting quota cannot
    # be allocated twice. Different campaigns still process in parallel.
    campaign_lock = redis_client.lock(
        f"rcs:campaign_producer:{campaign_id_text}",
        timeout=600,
        blocking_timeout=None,
    )

    with campaign_lock:
        campaign = campaigns_col.find_one(
            {"_id": campaign_id},
            {
                "total_numbers": 1,
                "status": 1,
                "punched_count": 1,
                "cutting_threshold": 1,
                "cutting_target": 1,
                "cutting_assigned": 1,
            },
        )
        if not campaign:
            return

        total_required = int(campaign.get("total_numbers", 0))
        punched_before_batch = int(campaign.get("punched_count", 0))
        cutting_threshold = int(campaign.get("cutting_threshold", 100))
        cutting_target = int(campaign.get("cutting_target", 0))
        cutting_assigned = int(campaign.get("cutting_assigned", 0))
        remaining_cutting = max(0, cutting_target - cutting_assigned)

        whitelist_set = {
            str(doc["phone_number"]).strip()
            for doc in whitelist_col.find({}, {"phone_number": 1})
            if doc.get("phone_number")
        }

        now = datetime.now(IST)
        docs = []
        for recipient in recipients:
            mobile = str(recipient.get("mobile", "")).strip()
            if not mobile:
                continue

            is_whitelisted = mobile in whitelist_set
            global_position = punched_before_batch + len(docs)
            above_threshold = global_position >= cutting_threshold
            is_fake = above_threshold and not is_whitelisted and remaining_cutting > 0
            if is_fake:
                remaining_cutting -= 1

            docs.append(
                {
                    "campaign_id": campaign_id,
                    "user_id": user_id,
                    "mobile": mobile,
                    "variables": recipient.get("variables", {}),
                    "status": "queued",
                    "is_fake": is_fake,
                    "is_whitelisted": is_whitelisted,
                    "created_at": now,
                    "updated_at": now,
                }
            )

        if not docs:
            return

        messages_col.insert_many(docs, ordered=False)
        assigned_in_batch = sum(1 for doc in docs if doc["is_fake"])
        updated_campaign = campaigns_col.find_one_and_update(
            {"_id": campaign_id},
            {
                "$inc": {
                    "punched_count": len(docs),
                    "cutting_assigned": assigned_in_batch,
                }
            },
            return_document=True,
        )

        current_punched = int(updated_campaign.get("punched_count", 0))
        if current_punched >= total_required:
            campaigns_col.update_one(
                {"_id": campaign_id},
                {"$set": {"status": "queued", "updated_at": now}},
            )
            logger.info(
                "Campaign %s fully punched: queued=%s cutting=%s/%s",
                campaign_id_text,
                current_punched,
                updated_campaign.get("cutting_assigned", 0),
                cutting_target,
            )


def main_loop():
    logger.info("RCS High-Speed Producer Started (Multi-User Parallel Mode)")
    while True:
        try:
            job = redis_client.rpop("rcs:campaign_upload")
            if not job:
                time.sleep(2)
                continue

            data = json.loads(job.decode("utf-8") if isinstance(job, bytes) else job)
            process_job(data)
        except Exception as exc:
            logger.exception("Critical Puncher Error: %s", exc)
            time.sleep(5)


if __name__ == "__main__":
    main_loop()
