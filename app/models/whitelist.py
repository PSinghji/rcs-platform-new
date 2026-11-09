from datetime import datetime
import pytz

# Define IST timezone
IST = pytz.timezone('Asia/Kolkata')
def whitelist_document(phone_number, user_id, reason="Campaign <= 20"):
    """
    Schema for the global whitelist collection.
    Numbers here always bypass the 'cutting' logic.
    """
    return {
        "phone_number": str(phone_number).strip(),
        "added_by": user_id,
        "reason": reason,
        "created_at": datetime.now(IST)
    }