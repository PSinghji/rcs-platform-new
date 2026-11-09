from datetime import datetime
from app.database import db
from bson import ObjectId
from app.models.wallet_ledger import wallet_ledger_document

users_col = db["users"]
ledger_col = db["wallet_ledger"]

# --- NEW LEDGER HELPER (Synchronous) ---
def _save_ledger_entry(user_id, action, amount, old_balance, reason, actor_id):
    """
    Saves a ledger entry. 
    Calculates new balance and uses the standard model wrapper.
    """
    new_balance = (old_balance + amount) if action == "credit" else (old_balance - amount)
    
    # Use your existing model wrapper to ensure correct formatting
    entry = wallet_ledger_document(
        user_id=ObjectId(user_id),
        action=action,
        amount=float(amount),
        balance_before=float(old_balance),
        balance_after=float(new_balance),
        reason=reason,
        created_by=ObjectId(actor_id)
    )
    
    # Standard PyMongo insert
    ledger_col.insert_one(entry)

async def perform_wallet_transaction(target_user_id, actor_user, amount, action, reason):
    target_oid = ObjectId(target_user_id)
    actor_oid = actor_user["_id"]
    amount = float(amount)
    
    # 1. Fetch Target User
    target = users_col.find_one({"_id": target_oid})
    if not target:
        return False, "Target user not found"

    # 2. Validation Logic
    if action == "credit":
        if str(target_oid) != str(actor_oid):
            if actor_user.get("wallet_balance", 0) < amount:
                return False, f"Insufficient funds. Balance: {actor_user.get('wallet_balance', 0)}"
    elif action == "debit":
        if target.get("wallet_balance", 0) < amount:
            return False, "Target user has insufficient funds."

    # 3. Execution with double-ledger entry
    try:
        if action == "credit" and str(target_oid) != str(actor_oid):
            # Atomic Updates
            users_col.update_one({"_id": actor_oid}, {"$inc": {"wallet_balance": -amount}})
            users_col.update_one({"_id": target_oid}, {"$inc": {"wallet_balance": amount}})
            
            # Save Ledger for both parties
            _save_ledger_entry(actor_oid, "debit", amount, actor_user.get("wallet_balance"), 
                             f"Transfer to {target.get('name')}: {reason}", actor_oid)
            _save_ledger_entry(target_oid, "credit", amount, target.get("wallet_balance"), 
                             f"Received from {actor_user.get('name')}: {reason}", actor_oid)
            
        elif action == "debit" and str(target_oid) != str(actor_oid):
            users_col.update_one({"_id": target_oid}, {"$inc": {"wallet_balance": -amount}})
            users_col.update_one({"_id": actor_oid}, {"$inc": {"wallet_balance": amount}})
            
            _save_ledger_entry(target_oid, "debit", amount, target.get("wallet_balance"), 
                             f"Returned to {actor_user.get('name')}: {reason}", actor_oid)
            _save_ledger_entry(actor_oid, "credit", amount, actor_user.get("wallet_balance"), 
                             f"Refund from {target.get('name')}: {reason}", actor_oid)
        
        else:
            # Self-transaction (Admin loading own wallet)
            users_col.update_one({"_id": target_oid}, {"$inc": {"wallet_balance": amount if action == "credit" else -amount}})
            _save_ledger_entry(target_oid, action, amount, target.get("wallet_balance"), reason, actor_oid)

        return True, "Transaction successful"
    except Exception as e:
        print(f"WALLET ERROR: {str(e)}")
        return False, f"Database error: {str(e)}"

# --- Legacy Wrappers ---
async def credit_wallet(target_user_id, actor_user, amount, reason="Initial Credit"):
    return await perform_wallet_transaction(target_user_id, actor_user, amount, "credit", reason)

async def debit_wallet(target_user_id, actor_user, amount, reason="Campaign Usage"):
    return await perform_wallet_transaction(target_user_id, actor_user, amount, "debit", reason)

async def campaign_debit_transaction(current_user, amount, campaign_name, debit_reason):
    try:
        user_id = current_user["_id"]
        debit_amount = float(amount)

        result = users_col.update_one(
            {"_id": user_id, "wallet_balance": {"$gte": debit_amount}},
            {"$inc": {"wallet_balance": -debit_amount}}
        )

        if result.modified_count == 0:
            return False, "Insufficient balance."

        updated_user = users_col.find_one({"_id": user_id})
        
        ledger_entry = wallet_ledger_document(
            user_id=user_id,
            action="debit",
            amount=debit_amount,
            balance_before=updated_user["wallet_balance"] + debit_amount,
            balance_after=updated_user["wallet_balance"],
            reason=f"Campaign: {debit_reason}",
            created_by=user_id
        )
        ledger_col.insert_one(ledger_entry)
        return True, "Success"
    except Exception as e:
        return False, str(e)