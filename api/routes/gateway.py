"""
Gateway API Routes

Endpoints:
- GET /api/gateway/status - Gateway status
- POST /api/gateway/config - Dynamic config update
"""

from typing import Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from api.auth import User, verify_token
from gateway.gateway import AIGateway

router = APIRouter()


class GatewayConfigUpdate(BaseModel):
    daily_limit: Optional[float] = None
    monthly_limit: Optional[float] = None
    per_task_limit: Optional[float] = None


class StandardResponse(BaseModel):
    success: bool
    data: Optional[dict] = None
    message: str


@router.get("/status", response_model=StandardResponse)
async def get_gateway_status(
    user: User = Depends(verify_token),
):
    """Get full gateway status"""
    gateway = AIGateway()
    status = await gateway.get_gateway_status()
    
    return StandardResponse(
        success=True,
        data=status,
        message="Gateway status retrieved"
    )


@router.post("/config", response_model=StandardResponse)
async def update_gateway_config(
    config: GatewayConfigUpdate,
    user: User = Depends(verify_token),
):
    """
    Dynamically update gateway configuration
    
    Note: These changes are in-memory only and will reset on restart.
    For permanent changes, update environment variables.
    """
    gateway = AIGateway()
    
    updates = {}
    
    if config.daily_limit is not None:
        gateway.cost_tracker.daily_hard_limit = config.daily_limit
        updates["daily_limit"] = config.daily_limit
    
    if config.monthly_limit is not None:
        gateway.cost_tracker.monthly_hard_limit = config.monthly_limit
        updates["monthly_limit"] = config.monthly_limit
    
    if config.per_task_limit is not None:
        gateway.cost_tracker.per_task_limit = config.per_task_limit
        updates["per_task_limit"] = config.per_task_limit
    
    return StandardResponse(
        success=True,
        data={"updated": updates},
        message="Gateway configuration updated"
    )
