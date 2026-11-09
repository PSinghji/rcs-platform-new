from datetime import datetime
import pytz

# Define IST timezone
IST = pytz.timezone('Asia/Kolkata')
def message_document(
    campaign_id,
    mobile,
    status,
    is_fake=False
):
    return {
        "campaign_id": campaign_id,
        "mobile": mobile,
        "status": status,
        "is_fake": is_fake,
        "jio_msg_id": None,
        "error_code": None,
        "created_at": datetime.now(IST),
        "updated_at": None
    }

