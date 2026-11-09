from pydantic import BaseModel, EmailStr, Field

from typing import Optional, Dict, Any  # Add Dict and Any here
from datetime import date

class CreateUserSchema(BaseModel):
    # ================= BASIC =================
    name: str
    username: str
    email: EmailStr
    password: str
    role: str
    mobile: Optional[str] = None  # Added from previous error

    # ================= PROVIDER =================
    provider_code: Optional[str] = None   # jio / airtel
    api_key: Optional[str] = None
    agent_id: Optional[str] = None
    # Add this line to fix the current error:
    provider_credentials: Optional[Dict[str, Any]] = None
    active_provider: Optional[str] = "jio"

    # ================= BILLING =================
    per_message_cost: float = 0.0
    initial_credit: float = 0.0
    credit_expiry: Optional[date] = None
    refund_enabled: bool = False

    # ================= CONTROL =================
    cutting_percent: int = Field(default=0, ge=0, le=100)
    cutting_threshold: int = Field(default=100, ge=0)
    active: bool = True
