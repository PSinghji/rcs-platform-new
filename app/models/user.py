from datetime import datetime
import pytz

# Define IST timezone
IST = pytz.timezone('Asia/Kolkata')
def user_document(
    name,
    email,
    password_hash,
    view_pw,
    role,
    mobile=None, # Added to match your UI
    parent_id=None,

    # Updated provider structure
    provider_credentials=None, # Dictionary: {"jio": {"api_key": "...", "agent_id": "..."}, "smartping": {...}}
    active_provider=None,     # String: "jio" (The selected radio button)

    # billing
    per_message_cost=0.0,
    wallet_balance=0.0,
    credit_expiry=None,
    refund_enabled=True,      # Added to match your UI toggle

    # flags
    active=True,
    cutting_percent=0,
    cutting_threshold=100
):
    return {
        "name": name,
        "email": email,
        "mobile": mobile,
        "password": password_hash,
        "view_pw": view_pw,
        "role": role,
        "parent_id": parent_id,

        # New Multi-Provider Binding
        "provider_credentials": provider_credentials or {},
        "active_provider": active_provider,

        # billing
        "per_message_cost": per_message_cost,
        "wallet_balance": wallet_balance,
        "credit_expiry": credit_expiry,
        "refund_enabled": refund_enabled,

        # permissions
        "cutting_percent": cutting_percent,
        "cutting_threshold": cutting_threshold,
        "active": active,

        "created_at": datetime.now(IST)
    }
