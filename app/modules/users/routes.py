from fastapi import APIRouter, Depends, HTTPException
from datetime import datetime, timedelta
from bson import ObjectId

from app.database import users_col
from app.dependencies_ui import get_current_user_ui
from app.utils.security import (
    hash_password,
    ROLE_ADMIN,
    ROLE_RESELLER,
    ROLE_USER,
    encrypt_viewable_password
)
from app.utils.validators import admin_only, admin_or_reseller
from app.schemas.user import CreateUserSchema
from app.utils.wallet import perform_wallet_transaction
import pytz

# Define IST timezone
IST = pytz.timezone('Asia/Kolkata') 
router = APIRouter(prefix="/ui/admin/users", tags=["Users"])


# ================= CREATE USER =================
@router.post("/create")
async def create_user(
    payload: CreateUserSchema, 
    current_user=Depends(get_current_user_ui)
):
    # ================= 1. ROLE VALIDATION =================
    if payload.role == ROLE_RESELLER:
        admin_or_reseller(current_user)

    if payload.role == ROLE_USER:
        admin_or_reseller(current_user)

    if payload.cutting_percent > 0 and current_user["role"] != ROLE_ADMIN:
        raise HTTPException(
            status_code=403,
            detail="Cutting % configuration is restricted to Admin only"
        )

    # ================= 2. UNIQUE CHECKS =================
    if users_col.find_one({"username": payload.username.lower()}):
        raise HTTPException(400, "Username already exists")

    if users_col.find_one({"email": payload.email.lower()}):
        raise HTTPException(400, "Email already exists")

    # ================= 3. RESELLER BALANCE CHECK =================
    # Critical check: Ensure reseller has enough balance to give initial credit
    if current_user["role"] == ROLE_RESELLER and payload.initial_credit > 0:
        if current_user.get("wallet_balance", 0) < payload.initial_credit:
            raise HTTPException(400, "Insufficient balance in your reseller wallet")

    # ================= 4. DATE PARSING & DEFAULT EXPIRY =================
    if payload.credit_expiry:
        if isinstance(payload.credit_expiry, str):
            credit_expiry = datetime.strptime(payload.credit_expiry, "%Y-%m-%d")
        else:
            credit_expiry = datetime.combine(payload.credit_expiry, datetime.min.time())
    else:
        credit_expiry = datetime.now(IST) + timedelta(days=365)

    # ================= 5. CREATE USER DOCUMENT =================
    encrypted_pw = encrypt_viewable_password(payload.password)
    user_doc = {
        "name": payload.name,
        "mobile": payload.mobile,
        "username": payload.username.lower(),
        "email": payload.email.lower(),
        "password": hash_password(payload.password),
        "view_pw": encrypted_pw,
        "role": payload.role,
        "parent_id": current_user["_id"],
        "provider_credentials": payload.provider_credentials or {}, 
        "active_provider": payload.active_provider,
        "per_message_cost": payload.per_message_cost,
        "wallet_balance": 0.0, 
        "credit_expiry": credit_expiry,
        "refund_enabled": payload.refund_enabled,
        "cutting_percent": payload.cutting_percent,
        "cutting_threshold": payload.cutting_threshold,
        "active": payload.active,
        "created_at": datetime.now(IST)
    }

    # ================= 6. EXECUTION BLOCK =================
    # ================= 6. EXECUTION BLOCK =================
    try:
        # Insert New User/Reseller
        result = users_col.insert_one(user_doc)
        new_user_id = str(result.inserted_id)
        
        # IMPORTANT: We must pass the full current_user object to the wallet function, 
        # as it likely needs to check the actor's own balance (reseller logic).
        if payload.initial_credit > 0:
            from app.utils.wallet import perform_wallet_transaction
            
            # We use current_user (the dict) instead of just the ID 
            # to ensure the perform_wallet_transaction has all the context it needs.
            success, message = await perform_wallet_transaction(
                target_user_id=new_user_id,
                actor_user=current_user, # Passing the full dict/object
                amount=payload.initial_credit,
                action="credit",
                reason=f"Initial wallet load for account: {payload.username}"
            )
            
            if not success:
                # ROLLBACK: If wallet funding fails, remove the created user
                users_col.delete_one({"_id": ObjectId(new_user_id)})
                raise HTTPException(status_code=400, detail=f"Wallet Error: {message}")
        
        return {
            "status": "success",
            "message": "User created and wallet funded successfully",
            "user_id": new_user_id
        }
    
    except HTTPException as he:
        # Re-raise HTTP exceptions so FastAPI handles them correctly
        raise he
    except Exception as e:
        # If a database error happens, ensure the user isn't created partially
        if 'new_user_id' in locals():
            users_col.delete_one({"_id": ObjectId(new_user_id)})
        
        print(f"CRITICAL ERROR: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Internal Server Error: {str(e)}")
