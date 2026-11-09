from datetime import datetime
import pytz

# Define IST timezone
IST = pytz.timezone('Asia/Kolkata')

def wallet_ledger_document(
    user_id,
    action,          # 'credit' | 'debit'
    amount,
    balance_before,  # Added for better tracking
    balance_after,
    reason,          # MANDATORY
    created_by,
    reference_id=None
):
    # Python will throw an error if 'reason' is missing when calling this
    return {
        "user_id": user_id,
        "action": action,
        "amount": amount,
        "balance_before": balance_before,
        "balance_after": balance_after,
        "reason": reason,
        "reference_id": reference_id,
        "created_by": created_by,
        "created_at": datetime.now(IST)
    }