from fastapi import APIRouter, Request, BackgroundTasks
from app.redis_client import redis_client
import json
import logging

logger = logging.getLogger("webhooks")
router = APIRouter(prefix="/webhooks", tags=["DLR"])
# 2. Add this NEW router for top-level routes (No prefix)
root_router = APIRouter(tags=["DLR-Root"])
DLR_QUEUE = "rcs:dlr_queue"

# ================= HEALTH CHECK =================
@router.post("/dlr/{provider}")
async def rcs_dlr(provider: str, request: Request):
    try:
        # 1. Capture the raw data
        data = await request.json()
        
        # 2. Print for debugging - This shows up in 'journalctl'
        print(f"DEBUG: Webhook hit! Provider: {provider}")
        print(f"DATA: {json.dumps(data, indent=2)}")
        # LOG THE DATA - This will appear in journalctl immediately
        logger.info(f"RECEIVED DLR [{provider}]: {json.dumps(data)}")
        # Existing logic: add provider and push to Redis
        data["_provider"] = provider
        redis_client.lpush(DLR_QUEUE, json.dumps(data))
        
        return {"ok": True}
    except Exception as e:
        print(f"ERROR in Webhook: {str(e)}")
        return {"ok": False, "detail": "Payload error"}



@root_router.post("/getDLR")
async def rcs_dlr_root(request: Request):
    try:
        data = await request.json()
        logger.info(f"ROOT DLR HIT: {json.dumps(data)}")
        
        # Identify this came from the root endpoint
        data["_provider"] = "jio"
        redis_client.lpush(DLR_QUEUE, json.dumps(data))
        
        return {"ok": True}
    except Exception as e:
        logger.error(f"Root Webhook Error: {str(e)}")
        return {"ok": False, "detail": str(e)}