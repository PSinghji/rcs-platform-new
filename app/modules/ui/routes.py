from fastapi import APIRouter, Depends, Request, HTTPException,Body, Form
from fastapi.responses import HTMLResponse , RedirectResponse
from fastapi.templating import Jinja2Templates
from bson import ObjectId
from fastapi import Body
from datetime import datetime, timedelta
from app.dependencies_ui import get_current_user_ui
from app.utils.security import ROLE_ADMIN, ROLE_RESELLER, ROLE_USER , hash_password,decrypt_viewable_password

from app.database import (
    users_col,
    templates_col,
    campaigns_col,
    messages_col,
    service_providers_col,
    wallet_ledger_col
)
import logging

import pytz
from datetime import datetime

# Define the IST timezone
IST = pytz.timezone('Asia/Kolkata')

logging.basicConfig(level=logging.INFO)


router = APIRouter(prefix="/ui", tags=["UI"])
templates = Jinja2Templates(directory="templates")

# ======================================================
# AUTH
# ======================================================
@router.get("/login", response_class=HTMLResponse)
def login_page(request: Request):
    return templates.TemplateResponse("auth/login.html", {"request": request})


# ======================================================
# DASHBOARDS
# ======================================================
# Ensure the path starts with /ui if that's where you want the dashboard
@router.get("/admin/dashboard", response_class=HTMLResponse)
def admin_dashboard(request: Request, user=Depends(get_current_user_ui)):
    if user["role"] != "admin": # Match the role string in your token/DB
        raise HTTPException(status_code=403)
    return templates.TemplateResponse(
        "dashboards/admin.html",
        {"request": request, "user": user, "title": "Admin Dashboard"}
    )


# @router.get("/reseller/dashboard", response_class=HTMLResponse)
# def reseller_dashboard(request: Request, user=Depends(get_current_user_ui)):
#     if user["role"] != ROLE_RESELLER:
#         raise HTTPException(status_code=403)

#     # Fetch last 5 campaigns for reseller + their users
#     campaigns = list(
#         campaigns_col.find(
#             {
#                 "$or": [
#                     {"user_id": user["_id"]},
#                     {"parent_id": user["_id"]}
#                 ]
#             }
#         )
#         .sort("created_at", -1)
#         .limit(5)
#     )

#     # Convert ObjectId → str
#     for c in campaigns:
#         c["_id"] = str(c["_id"])

#     return templates.TemplateResponse(
#         "dashboards/reseller.html",
#         {
#             "request": request,
#             "user": user,
#             "campaigns": campaigns,
#             "title": "Reseller Dashboard"
#         }
#     )

@router.get("/reseller/dashboard", response_class=HTMLResponse)
async def reseller_dashboard(request: Request, user=Depends(get_current_user_ui)):
    if user["role"] != ROLE_RESELLER:
        raise HTTPException(status_code=403)

    reseller_id = user["_id"]

    # 1. Count users managed by this reseller
    total_users = users_col.count_documents({"parent_id": reseller_id})

    # 2. Define Campaign Filter (Reseller + Sub-users)
    campaign_filter = {
        "$or": [
            {"user_id": reseller_id},
            {"parent_id": reseller_id}
        ]
    }

    # 3. Get all relevant campaign IDs to query message-level stats
    # We fetch only the _id field to keep the query fast
    all_campaign_docs = list(campaigns_col.find(campaign_filter, {"_id": 1}))
    camp_ids = [doc["_id"] for doc in all_campaign_docs]

    # 4. Aggregate Message Stats for the Donut Chart
    message_stats = {
        "delivered": messages_col.count_documents({"campaign_id": {"$in": camp_ids}, "status": {"$in": ["delivered", "1"]}}),
        "read": messages_col.count_documents({"campaign_id": {"$in": camp_ids}, "status": {"$in": ["read", "3", "message_read"]}}),
        "clicked": messages_col.count_documents({"campaign_id": {"$in": camp_ids}, "status": "clicked"}),
        "failed": messages_col.count_documents({"campaign_id": {"$in": camp_ids}, "status": {"$in": ["failed", "2"]}})
    }
    
    # Total for the card count
    total_processed_messages = sum(message_stats.values())

    # 5. Fetch last 5 campaigns for the table with IST conversion
    recent_campaigns = list(
        campaigns_col.find(campaign_filter)
        .sort("created_at", -1)
        .limit(5)
    )

    for c in recent_campaigns:
        c["_id"] = str(c["_id"])
        if c.get("created_at") and isinstance(c["created_at"], datetime):
            # Convert UTC to IST
            ist_time = c["created_at"] + timedelta(hours=5, minutes=30)
            c["display_date"] = ist_time.strftime("%d-%m-%Y %H:%M")
        else:
            c["display_date"] = "-"

    # 6. Prepare Wallet Trend Data (Last 7 Days)
    # We query the wallet_ledger to find the daily balance drops
    wallet_labels = []
    wallet_data = []
    
    for i in range(6, -1, -1):
        target_date = datetime.now() - timedelta(days=i)
        date_str = target_date.strftime("%d %b")
        wallet_labels.append(date_str)
        
        # Get the last transaction of that specific day to see the balance
        start_of_day = target_date.replace(hour=0, minute=0, second=0, microsecond=0)
        end_of_day = target_date.replace(hour=23, minute=59, second=59, microsecond=999)
        
        last_tx = wallet_ledger_col.find_one(
            {"user_id": reseller_id, "created_at": {"$lte": end_of_day}},
            sort=[("created_at", -1)]
        )
        
        if last_tx:
            # If your ledger stores the balance after transaction
            wallet_data.append(float(last_tx.get("balance_after", user.get("wallet_balance", 0))))
        else:
            # Fallback to current balance if no history found for that day
            wallet_data.append(float(user.get("wallet_balance", 0)))

    return templates.TemplateResponse(
        "dashboards/reseller.html",
        {
            "request": request,
            "user": user,
            "campaigns": recent_campaigns,
            "total_users": total_users,
            "total_campaigns": len(camp_ids), # Total number of campaign sets
            "message_stats": message_stats,     # Data for Donut Chart
            "wallet_labels": wallet_labels,
            "wallet_data": wallet_data,
            "title": "Reseller Dashboard"
        }
    )
@router.get("/user/dashboard", response_class=HTMLResponse)
def user_dashboard(request: Request, user=Depends(get_current_user_ui)):
    if user["role"] not in [ROLE_USER, ROLE_ADMIN]:
        raise HTTPException(status_code=403)
    return templates.TemplateResponse(
        "dashboards/user.html",
        {"request": request, "user": user, "title": "User Dashboard"}
    )


# ======================================================
# USERS
# ======================================================
@router.get("/users/list", response_class=HTMLResponse)
def users_list(request: Request, user=Depends(get_current_user_ui)):
    if user["role"] == ROLE_ADMIN:
        users = list(users_col.find({}, {"password": 0}))
    elif user["role"] == ROLE_RESELLER:
        users = list(users_col.find({"parent_id": user["_id"]}, {"password": 0}))
    else:
        raise HTTPException(status_code=403)

    print(f"--- Debugging Users List (Found {len(users)} users) ---")

    for u in users:
        u["_id"] = str(u["_id"])
        
        # Default value
        u["upline_name"] = "System / Admin"
        u["upline_username"] = "system"
        if u.get("parent_id"):
            # Fetch parent - added 'username' and 'role' to debug projection
            parent = users_col.find_one({"_id": u["parent_id"]}, {"name": 1, "role": 1, "username": 1})
            
            if parent:
                # Explicitly setting the name
                u["upline_name"] = parent.get("name")
                u["upline_username"] = parent.get("username")
            

    return templates.TemplateResponse(
        "users/list.html",
        {"request": request, "user": user, "users": users}
    )

@router.get("/users/create", response_class=HTMLResponse)
async def create_user_page(request: Request, user=Depends(get_current_user_ui)):
    logging.info(f"User {user.get('username')} is accessing the Create User page.")

    if user["role"] not in [ROLE_ADMIN, ROLE_RESELLER]:
        logging.warning(f"Access denied for user {user.get('username')}.")
        raise HTTPException(status_code=403)
    
    # providers_list = list(service_providers_col.find())
    providers_list = list(service_providers_col.find({"status": "ACTIVE"}))

    return templates.TemplateResponse("users/create.html", {
        "request": request, 
        "user": user, 
        "providers": providers_list,
        "title": "Create User"
    })
# ======================================================

@router.get("/users/{user_id}/decrypt")
async def get_decrypted_user_pw(user_id: str, current_user=Depends(get_current_user_ui)):
    if current_user["role"] != "admin":
        raise HTTPException(status_code=403)
        
    user_data = users_col.find_one({"_id": ObjectId(user_id)})
    if not user_data or "view_pw" not in user_data:
        return {"password": "Password not stored reversibly"}
        
    plain_pw = decrypt_viewable_password(user_data["view_pw"])
    return {"password": plain_pw}
# ======================================================

# ======================================================  
# Get Users for EDIT USER  
# ======================================================
@router.get("/users/{user_id}/edit", response_class=HTMLResponse)
def edit_user(
    request: Request,
    user_id: str,
    user=Depends(get_current_user_ui)
):
    db_user = users_col.find_one({"_id": ObjectId(user_id)}, {"password": 0})
    target_oid = ObjectId(user_id)
    # Fetch the user we want to edit
    user_to_edit = users_col.find_one({"_id": target_oid})

    if not db_user:
        raise HTTPException(status_code=404, detail="User not found")

    # 🔒 HARD SECURITY CHECK
    # Ensure Resellers can only edit their own child users
    if user["role"] == ROLE_RESELLER:
        if db_user.get("parent_id") != user["_id"]:
            raise HTTPException(status_code=403, detail="Access denied")
    elif user["role"] != ROLE_ADMIN:
        raise HTTPException(status_code=403, detail="Access denied")

    # --- DATE FORMATTING FOR HTML5 INPUT ---
    # HTML5 <input type="date"> requires YYYY-MM-DD format exactly
    formatted_expiry = ""
    if db_user.get("credit_expiry"):
        expiry_val = db_user["credit_expiry"]
        if isinstance(expiry_val, datetime):
            formatted_expiry = expiry_val.strftime("%Y-%m-%d")
        elif isinstance(expiry_val, str):
            # In case it was already saved as a string
            formatted_expiry = expiry_val[:10] 

    db_user["_id"] = str(db_user["_id"])
    providers_list = list(service_providers_col.find())

    return templates.TemplateResponse(
        "users/edit.html",
        {
            "request": request,
            "user": user,                # The logged-in admin/reseller
            "providers": providers_list,
            "edit_user": db_user,        # The user being edited
            "formatted_expiry": formatted_expiry,
            "target_user": user_to_edit # Pass this to the template
        }
    )

# ====================================================
# Post USER Profile
# ====================================================
@router.get("/profile", response_class=HTMLResponse)
async def edit_profile_page(request: Request, user=Depends(get_current_user_ui)):
    # Fetch fresh user data from DB
    user_data = users_col.find_one({"_id": user["_id"]})
    return templates.TemplateResponse("users/profile.html", {
        "request": request,
        "user": user,
        "profile": user_data
    })

@router.post("/profile/update")
async def update_profile(
    request: Request,
    name: str = Form(...),
    mobile: str = Form(...),
    email: str = Form(...),
    password: str = Form(None),
    user=Depends(get_current_user_ui)
):
    update_data = {
        "name": name,
        "mobile": mobile,
        "email": email.lower()
    }

    # Only update password if a new one is provided
    if password and password.strip():
        from app.utils.security import hash_password, encrypt_viewable_password
        update_data["password"] = hash_password(password)
        update_data["view_pw"] = encrypt_viewable_password(password)

    users_col.update_one({"_id": user["_id"]}, {"$set": update_data})
    
    return RedirectResponse(url="/ui/profile?success=true", status_code=303)
# ====================================================
# Post EDIT USER (Upgraded for JSON & Multi-Provider)
# ====================================================
@router.post("/users/{user_id}/edit")
async def update_user(
    user_id: str,
    payload: dict = Body(...),
    current_user=Depends(get_current_user_ui)
):
    # 1. Fetch Target User
    target_oid = ObjectId(user_id)
    target_user = users_col.find_one({"_id": target_oid})
    
    if not target_user:
        raise HTTPException(status_code=404, detail="User not found")

    current_role = target_user.get("role")
    new_role = payload.get("role")
    
    # Role Validation Logic
    if new_role and new_role != current_role:
        if current_role == "user" and new_role == "reseller":
            pass 
        else:
            raise HTTPException(status_code=403, detail="Role change not permitted.")
    else:
        new_role = current_role

    # 2. Permission Check: Reseller can only edit their own children
    if current_user["role"] == ROLE_RESELLER:
        if str(target_user.get("parent_id")) != str(current_user["_id"]):
            raise HTTPException(status_code=403, detail="Permission denied")
    
    # 3. Handle Expiry Date Logic
    credit_expiry = target_user.get("credit_expiry")
    input_expiry = payload.get("credit_expiry")
    
    if input_expiry:
        try:
            credit_expiry = datetime.strptime(input_expiry, "%Y-%m-%d")
        except (ValueError, TypeError):
            pass 

    # 4. Prepare Update Document
    update_data = {
        "role": new_role,
        "name": payload.get("name", target_user.get("name")),
        "mobile": payload.get("mobile", target_user.get("mobile")),
        "email": payload.get("email", target_user.get("email")).lower() if payload.get("email") else target_user.get("email"),
        "active_provider": payload.get("active_provider", target_user.get("active_provider")),
        "provider_credentials": payload.get("provider_credentials", target_user.get("provider_credentials")),
        # Resellers may edit their child accounts but cannot change billing rates.
        "per_message_cost": float(target_user.get("per_message_cost") or 1.0),
        "credit_expiry": credit_expiry,
        "refund_enabled": payload.get("refund_enabled", target_user.get("refund_enabled", False)),
        "active": payload.get("active", target_user.get("active", True)),
    }

    # 5. Admin-Only Fields
    if current_user["role"] == ROLE_ADMIN:
        try:
            per_message_cost = float(payload.get("per_message_cost", target_user.get("per_message_cost", 1.0)))
        except (TypeError, ValueError):
            raise HTTPException(status_code=400, detail="Cost per message must be a valid number")
        if per_message_cost <= 0:
            raise HTTPException(status_code=400, detail="Cost per message must be greater than zero")
        update_data["per_message_cost"] = per_message_cost

        cutting_percent = float(payload.get("cutting_percent", target_user.get("cutting_percent", 0)))
        cutting_threshold = int(payload.get("cutting_threshold", target_user.get("cutting_threshold", 100)))
        if not 0 <= cutting_percent <= 100:
            raise HTTPException(status_code=400, detail="Cutting percentage must be between 0 and 100")
        if cutting_threshold < 0:
            raise HTTPException(status_code=400, detail="Cutting threshold cannot be negative")
        update_data["cutting_percent"] = cutting_percent
        update_data["cutting_threshold"] = cutting_threshold

    # 6. Password Update (Including Admin viewable field)
    if payload.get("password") and payload.get("password").strip():
        from app.utils.security import hash_password, encrypt_viewable_password
        update_data["password"] = hash_password(payload["password"])
        update_data["view_pw"] = encrypt_viewable_password(payload["password"])

    # 7. Execute Update
    try:
        users_col.update_one(
            {"_id": target_oid},
            {"$set": update_data}
        )
        
        return {
            "status": "success",
            "message": "User updated successfully"
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Update failed: {str(e)}")
# ======================================================
# TEMPLATES
# ======================================================
@router.get("/templates/list", response_class=HTMLResponse)
def my_templates(request: Request, user=Depends(get_current_user_ui)):
    tpl_list = list(
        templates_col
        .find({"owner_id": user["_id"]})
        .sort("created_at", -1)
    )

    for t in tpl_list:
        t["id"] = str(t["_id"])   # ✅ REQUIRED
        t.pop("_id", None)        # ✅ CLEAN

    return templates.TemplateResponse(
        "templates/list.html",
        {
            "request": request,
            "user": user,
            "templates": tpl_list
        }
    )


@router.get("/templates/create", response_class=HTMLResponse)
def create_template(request: Request, user=Depends(get_current_user_ui)):
    return templates.TemplateResponse(
        "templates/create.html",
        {"request": request, "user": user}
    )

@router.get("/templates/edit/{template_id}", response_class=HTMLResponse)
async def get_edit_template_page(
    request: Request, 
    template_id: str, 
    user=Depends(get_current_user_ui)
):
    # 1. Security Check: Only Admin or the Template Owner should edit
    # If this is strictly for Admin approval panel, keep ROLE_ADMIN check
    if user["role"] != "admin":
        raise HTTPException(status_code=403, detail="Not authorized")

    # 2. Fetch the template from MongoDB
    try:
        tpl = templates_col.find_one({"_id": ObjectId(template_id)})
    except:
        raise HTTPException(status_code=400, detail="Invalid Template ID format")

    if not tpl:
        raise HTTPException(status_code=404, detail="Template not found")

    # 3. Prepare data for Jinja2
    # Convert ObjectId to string so JavaScript can read it as TEMPLATE_ID
    tpl["id"] = str(tpl["_id"])

    return templates.TemplateResponse(
        "templates/edit.html", 
        {
            "request": request,
            "user": user,
            "template": tpl
        }
    )

@router.get("/admin/templates/approvals", response_class=HTMLResponse)
async def template_approvals(request: Request, user=Depends(get_current_user_ui)):
    # 1. Security Check
    if user["role"] != ROLE_ADMIN:
        raise HTTPException(status_code=403)

    # 2. Fetch ALL templates (Removed {"status": "pending"} filter)
    all_templates = list(
        templates_col.find({}) 
        .sort("created_at", -1) # Show newest first
    )

    # 3. Process each template to add Owner Name
    for t in all_templates:
        t["id"] = str(t["_id"])
        
        # Get the Owner ID
        owner_id = t.get("owner_id")
        owner_name = "Unknown User" 
        
        if owner_id:
            try:
                # Ensure we are querying with the correct ID type (ObjectId or String)
                # Depending on how you stored it, usually ObjectId:
                owner_user = users_col.find_one({"_id": ObjectId(owner_id)})
                if owner_user:
                    owner_name = owner_user.get("name") or owner_user.get("username") or "Unknown"
            except Exception:
                # Fallback if owner_id is not a valid ObjectId string
                pass
        
        # Attach details
        t["requested_by_name"] = owner_name
        
        # Clean up Mongo ID
        t.pop("_id", None)

    # 4. Return to Template
    return templates.TemplateResponse(
        "templates/approvals.html",
        {
            "request": request,
            "user": user,
            "templates": all_templates # Passing full list now
        }
    )

# ======================================================
# CAMPAIGNS
# ======================================================

# =====================================================
@router.get("/campaigns/view/{cid}", response_class=HTMLResponse)
def campaign_view(request: Request, cid: str, user=Depends(get_current_user_ui)):
    campaign = campaigns_col.find_one({"_id": ObjectId(cid)})
    if not campaign:
        raise HTTPException(status_code=404)

    messages = list(messages_col.find({"campaign_id": campaign["_id"]}))
    return templates.TemplateResponse(
        "campaigns/view.html",
        {"request": request, "user": user, "campaign": campaign, "messages": messages}
    )


@router.get("/admin/campaigns/all", response_class=HTMLResponse)
def all_campaigns(request: Request, user=Depends(get_current_user_ui)):
    if user["role"] != ROLE_ADMIN:
        raise HTTPException(status_code=403)

    campaigns = list(campaigns_col.find({}))
    return templates.TemplateResponse(
        "campaigns/list.html",
        {"request": request, "user": user, "campaigns": campaigns}
    )



# --- Wallet Management Section ---

@router.get("/wallet/manage", response_class=HTMLResponse)
async def wallet_management_page(request: Request, user=Depends(get_current_user_ui)):
    # Admins see everyone, Resellers see only their children
    if user["role"] == ROLE_ADMIN:
        all_users = list(users_col.find({}, {"name": 1, "username": 1, "wallet_balance": 1, "role": 1}))
    else:
        all_users = list(users_col.find({"parent_id": user["_id"]}, {"name": 1, "username": 1, "wallet_balance": 1, "role": 1}))
    
    return templates.TemplateResponse("wallet/manage.html", {
        "request": request, 
        "user": user, 
        "manageable_users": all_users
    })


@router.get("/wallet/history/{target_user_id}", response_class=HTMLResponse)
async def view_user_history(target_user_id: str, request: Request, user=Depends(get_current_user_ui)):
    try:
        target_oid = ObjectId(target_user_id)
        
        # Security checks remain the same...

        # 1. Fetch Transactions
        history_raw = list(wallet_ledger_col.find({"user_id": target_oid}).sort("created_at", -1))
        
        # 2. ENRICH DATA: Get usernames for 'performed_by'
        history = []
        for tx in history_raw:
            performer_id = tx.get("created_by")
            performer_name = "System"
            
            if performer_id:
                # Find the user name for the performer
                p_user = users_col.find_one({"_id": ObjectId(performer_id)}, {"name": 1})
                if p_user:
                    performer_name = p_user.get("name")
            
            # Attach the name to the transaction object
            tx["performer_name"] = performer_name
            history.append(tx)

        target_user = users_col.find_one({"_id": target_oid}, {"name": 1, "username": 1, "wallet_balance": 1})

        return templates.TemplateResponse("wallet/history.html", {
            "request": request, 
            "user": user, 
            "history": history,  # Now contains performer_name
            "target_user": target_user
        })
    except Exception as e:
        return HTMLResponse(content=f"Error: {str(e)}", status_code=500)

# @router.get("/wallet/history/{target_user_id}", response_class=HTMLResponse)

# async def view_user_history(target_user_id: str, request: Request, user=Depends(get_current_user_ui)):
#     try:
#         target_oid = ObjectId(target_user_id)
        
#         # 1. FETCH TRANSACTIONS
#         # If the reseller is looking at their own history, 
#         # they might want to see everything they did for others as well.
#         if str(user["_id"]) == target_user_id:
#             # Reseller viewing their own history: show transactions where they are the target 
#             # OR where they were the performer for someone else.
#             query = {
#                 "$or": [
#                     {"user_id": target_oid},
#                     {"created_by": user["_id"]}
#                 ]
#             }
#         else:
#             # Viewing a specific child user's history
#             query = {"user_id": target_oid}

#         history_raw = list(wallet_ledger_col.find(query).sort("created_at", -1))
        
#         # 2. ENRICH DATA: Get usernames for 'performed_by'
#         history = []
#         for tx in history_raw:
#             # Ensure target_id is string for template comparison
#             tx["_id"] = str(tx["_id"])
#             tx["user_id"] = str(tx["user_id"])
            
#             performer_id = tx.get("created_by")
#             performer_name = "System"
            
#             if performer_id:
#                 p_user = users_col.find_one({"_id": ObjectId(performer_id)}, {"name": 1})
#                 if p_user:
#                     performer_name = p_user.get("name")
            
#             tx["performer_name"] = performer_name
#             history.append(tx)

#         target_user = users_col.find_one({"_id": target_oid}, {"name": 1, "username": 1})

#         return templates.TemplateResponse("wallet/history.html", {
#             "request": request, 
#             "user": user, 
#             "history": history,
#             "target_user": target_user
#         })
#     except Exception as e:
#         return HTMLResponse(content=f"Error: {str(e)}", status_code=500)

@router.post("/admin/users/wallet/process")
async def process_wallet_transaction(
    request: Request,
    user=Depends(get_current_user_ui) # This is the Actor
):
    form = await request.form()
    target_id = form.get("target_id")
    action = form.get("action")
    amount = float(form.get("amount", 0))
    reason = form.get("reason", "Manual Adjustment")

    from app.utils.wallet import perform_wallet_transaction
    success, message = await perform_wallet_transaction(
        target_user_id=target_id,
        actor_user=user, # Full dict/object
        amount=amount,
        action=action,
        reason=reason
    )

    if not success:
        return RedirectResponse(url=f"/ui/wallet/manage?error={message}", status_code=303)
        
    return RedirectResponse(url="/ui/wallet/manage?success=Transaction+Completed", status_code=303)
# ======================================================
@router.get("/dashboard")
def dashboard_guard(user=Depends(get_current_user_ui)):
    if user["role"] == ROLE_ADMIN:
        return RedirectResponse("/ui/admin/dashboard", status_code=302)
    elif user["role"] == ROLE_RESELLER:
        return RedirectResponse("/ui/reseller/dashboard", status_code=302)
    else:
        return RedirectResponse("/ui/user/dashboard", status_code=302)
# Redirect to appropriate dashboard based on role

# =====================================================
# REPORTS
# =====================================================
@router.get("/reports/campaigns", response_class=HTMLResponse)
def campaign_reports(request: Request, user=Depends(get_current_user_ui)):

    query = {}
    if user["role"] == ROLE_USER:
        query["user_id"] = user["_id"]
    elif user["role"] == ROLE_RESELLER:
        query["$or"] = [
            {"user_id": user["_id"]},
            {"parent_id": user["_id"]}
        ]

    campaigns = list(campaigns_col.find(query).sort("created_at", -1))

    return templates.TemplateResponse(
        "reports/campaigns.html",
        {
            "request": request,
            "user": user,
            "campaigns": campaigns,
            "title": "Campaign Reports"
        }
    )

# =====================================================
# API ENDPOINTS
# =====================================================

@router.post("/templates/create")
def submit_template(
    payload: dict = Body(...),
    user=Depends(get_current_user_ui)
):
    """
    Create template for User / Reseller / Admin.
    Admin approval required for non-admin users.
    """

    doc = {
        "name": payload.get("name"),
        "template_type": payload.get("template_type"),
        "content": payload.get("content"),
        "owner_id": user["_id"],
        "owner_role": user["role"],
        "status": "approved" if user["role"] == ROLE_ADMIN else "pending",
        "created_at": datetime.now(IST)
    }

    templates_col.insert_one(doc)

    return {
        "message": "Template submitted successfully"
        if user["role"] == ROLE_ADMIN
        else "Template submitted for admin approval"
    }

# =====================================================
@router.get("/templates/preview/{template_id}") # Remove HTMLResponse
def preview_template(
    request: Request,
    template_id: str,
    user=Depends(get_current_user_ui)
):
    tpl = templates_col.find_one({"_id": ObjectId(template_id)})

    if not tpl:
        raise HTTPException(status_code=404, detail="Template not found")

    # Ownership check
    if user["role"] != "admin" and tpl["owner_id"] != user["_id"]:
        raise HTTPException(status_code=403, detail="Access denied")

    # Return only the data needed for the preview
    return {
        "status": "success",
        "template_type": tpl.get("template_type"),
        "content": tpl.get("content")
    }

@router.get("/templates/view/{template_id}", response_class=HTMLResponse)
def view_full_template(
    request: Request,
    template_id: str,
    user=Depends(get_current_user_ui)
):
    tpl = templates_col.find_one({"_id": ObjectId(template_id)})
    if not tpl:
        raise HTTPException(status_code=404, detail="Template not found")

    # Capture where the user came from
    # If there is no referer (e.g., direct link), fall back to the main list
    back_url = request.headers.get("referer", "/ui/templates")

    tpl["id"] = str(tpl["_id"])

    return templates.TemplateResponse(
        "templates/preview.html", 
        {
            "request": request, 
            "template": tpl, 
            "user": user,
            "back_url": back_url  # Pass this to the HTML
        }
    )
# =====================================================
@router.get("/admin/templates/all", response_class=HTMLResponse)
def admin_all_templates(request: Request, user=Depends(get_current_user_ui)):
    if user["role"] != ROLE_ADMIN:
        raise HTTPException(status_code=403)

    templates_list = list(
        templates_col.find({})
        .sort("created_at", -1)
    )

    for t in templates_list:
        t["id"] = str(t["_id"])
        t.pop("_id", None)

    return templates.TemplateResponse(
        "templates/admin_all.html",
        {
            "request": request,
            "user": user,
            "templates": templates_list
        }
    )

@router.post("/logout")
def logout():
    response = JSONResponse({"message": "Logged out"})
    response.delete_cookie("token", path="/")
    return response

# =====================================================
@router.get("/logout")
def logout_get():
    response = RedirectResponse("/ui/login", status_code=302)
    response.delete_cookie("token", path="/")
    return response
