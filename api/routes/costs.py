"""
Costs API Routes

Endpoints:
- GET /api/costs - Real-time cost data
- GET /api/costs/daily - Daily cost breakdown
- GET /api/costs/by-task - Cost by task type
- GET /api/costs/by-model - Cost by model
"""

from typing import List, Optional

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from api.auth import User, verify_token
from core.database import get_db
from core.models import CostRecord
from gateway.cost_tracker import CostTracker

router = APIRouter()


class StandardResponse(BaseModel):
    success: bool
    data: Optional[dict] = None
    message: str


@router.get("", response_model=StandardResponse)
async def get_costs(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(verify_token),
):
    """Get real-time cost data and budget status"""
    tracker = CostTracker()
    budget_status = await tracker.get_budget_status()
    
    # Get today's cost from DB
    from datetime import date
    today = date.today()
    
    today_query = select(func.sum(CostRecord.cost)).where(
        func.date(CostRecord.created_at) == today
    )
    today_result = await db.execute(today_query)
    today_cost = today_result.scalar() or 0.0
    
    # Get this month's cost
    month_start = today.replace(day=1)
    month_query = select(func.sum(CostRecord.cost)).where(
        func.date(CostRecord.created_at) >= month_start
    )
    month_result = await db.execute(month_query)
    month_cost = month_result.scalar() or 0.0
    
    return StandardResponse(
        success=True,
        data={
            "today": {
                "spent": round(today_cost, 6),
                "limit": budget_status.daily_limit,
                "remaining": round(budget_status.daily_limit - today_cost, 6),
                "percentage": round(today_cost / budget_status.daily_limit * 100, 2),
            },
            "month": {
                "spent": round(month_cost, 6),
                "limit": budget_status.monthly_limit,
                "remaining": round(budget_status.monthly_limit - month_cost, 6),
                "percentage": round(month_cost / budget_status.monthly_limit * 100, 2),
            },
            "level": budget_status.level,
            "degraded_models": budget_status.degraded_model_map if budget_status.level == "degraded" else {},
        },
        message="Cost data retrieved successfully"
    )


@router.get("/daily", response_model=StandardResponse)
async def get_daily_costs(
    days: int = Query(30, ge=1, le=90),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(verify_token),
):
    """Get daily cost breakdown for last N days"""
    from datetime import datetime, timedelta
    
    start_date = datetime.utcnow() - timedelta(days=days)
    
    query = select(
        func.date(CostRecord.created_at).label("date"),
        func.sum(CostRecord.cost).label("total_cost"),
        func.count(CostRecord.id).label("call_count"),
    ).where(
        CostRecord.created_at >= start_date
    ).group_by(
        func.date(CostRecord.created_at)
    ).order_by(
        func.date(CostRecord.created_at)
    )
    
    result = await db.execute(query)
    rows = result.all()
    
    return StandardResponse(
        success=True,
        data={
            "days": [
                {
                    "date": str(row.date),
                    "cost": round(row.total_cost or 0, 6),
                    "calls": row.call_count,
                }
                for row in rows
            ]
        },
        message="Daily costs retrieved successfully"
    )


@router.get("/by-task", response_model=StandardResponse)
async def get_costs_by_task(
    days: int = Query(30, ge=1, le=90),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(verify_token),
):
    """Get cost breakdown by task type"""
    from datetime import datetime, timedelta
    
    start_date = datetime.utcnow() - timedelta(days=days)
    
    # Join with tasks to get task types
    from core.models import Task
    
    query = select(
        Task.task_type,
        func.sum(CostRecord.cost).label("total_cost"),
        func.count(CostRecord.id).label("call_count"),
    ).join(
        Task, CostRecord.task_id == Task.id
    ).where(
        CostRecord.created_at >= start_date
    ).group_by(
        Task.task_type
    )
    
    result = await db.execute(query)
    rows = result.all()
    
    return StandardResponse(
        success=True,
        data={
            "by_task_type": [
                {
                    "task_type": row.task_type or "unknown",
                    "cost": round(row.total_cost or 0, 6),
                    "calls": row.call_count,
                }
                for row in rows
            ]
        },
        message="Costs by task type retrieved successfully"
    )


@router.get("/by-model", response_model=StandardResponse)
async def get_costs_by_model(
    days: int = Query(30, ge=1, le=90),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(verify_token),
):
    """Get cost breakdown by model tier"""
    from datetime import datetime, timedelta
    
    start_date = datetime.utcnow() - timedelta(days=days)
    
    query = select(
        CostRecord.model_tier,
        func.sum(CostRecord.cost).label("total_cost"),
        func.sum(CostRecord.input_tokens + CostRecord.output_tokens).label("total_tokens"),
        func.count(CostRecord.id).label("call_count"),
    ).where(
        CostRecord.created_at >= start_date
    ).group_by(
        CostRecord.model_tier
    )
    
    result = await db.execute(query)
    rows = result.all()
    
    return StandardResponse(
        success=True,
        data={
            "by_model": [
                {
                    "model_tier": row.model_tier,
                    "cost": round(row.total_cost or 0, 6),
                    "tokens": int(row.total_tokens or 0),
                    "calls": row.call_count,
                }
                for row in rows
            ]
        },
        message="Costs by model retrieved successfully"
    )
