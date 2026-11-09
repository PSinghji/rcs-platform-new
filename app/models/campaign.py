from datetime import datetime
import pytz

# Define IST timezone
IST = pytz.timezone('Asia/Kolkata')
def campaign_document(
    user_id,
    campaign_name,
    template_id,
    template_name,
    template_type,
    total_numbers,
    valid_numbers,

    # 🔥 Provider snapshot
    provider_code,
    provider_name,
    agent_id,

    # 🔥 Cutting & Whitelist Fields (NEW)
    cutting_percent=0.0,
    cutting_threshold=100,
    
    created_by=None
):
   # Calculate IST time once
    now_ist = datetime.now(IST).replace(tzinfo=None) # 🔥 THIS STRIPS THE UTC CONVERSION
    """
    Upgraded Campaign Model with Cutting Logic Support.
    """
    return {
        "user_id": user_id,
        "campaign_name": campaign_name,

        "template_id": template_id,
        "template_name": template_name,
        "template_type": template_type,

        "provider_code": provider_code,
        "provider_name": provider_name,
        "agent_id": agent_id,

        "total_numbers": total_numbers,
        "valid_numbers": valid_numbers,
        
        # Stats tracking
        "queued_count": 0,
        "sent_count": 0,             # Real API attempts
        "delivered_count": 0,        # Combined Real + Fake delivered
        "failed_count": 0,           # Real failures
        "fake_delivered_count": 0,   # Specifically track Fdel for internal audit
        
        # Cutting configuration snapshot at time of creation. Cutting applies
        # only to the audience above the protected threshold.
        "cutting_percent": float(cutting_percent),
        "cutting_threshold": int(cutting_threshold),
        "cutting_target": int((((max(0, int(total_numbers) - int(cutting_threshold))) * float(cutting_percent)) / 100.0) + 0.5),
        "cutting_assigned": 0,

        "status": "queued",

        "created_by": created_by or user_id,
        "created_at": now_ist,
        "updated_at": now_ist
    }
