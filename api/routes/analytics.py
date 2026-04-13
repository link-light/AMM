"""
Analytics API Routes

Endpoints:
- GET /api/analytics/overview - System overview
- GET /api/analytics/roi - ROI analysis
- GET /api/analytics/success-rate - Success rate trends
"""

from typing import Optional

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from api.auth import User, verify_token
from core.database import get_db
from core.models import CostRecord, Signal, Task, TaskResult

router = APIRouter()


class StandardResponse(BaseModel):
    success: bool
    data: Optional[dict] = None
    message: str


@router.get("/overview", response_model=StandardResponse)
async def get_overview(
    days: int = Query(30, ge=1, le=90),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(verify_token),
):
    """Get system overview statistics"""
    from datetime import datetime, timedelta
    
    start_date = datetime.utcnow() - timedelta(days=days)
    
    # Total signals
    signals_query = select(func.count(Signal.id)).where(
        Signal.created_at >= start_date
    )
    signals_result = await db.execute(signals_query)
    total_signals = signals_result.scalar() or 0
    
    # Signals by status
    status_query = select(
        Signal.status,
        func.count(Signal.id)
    ).where(
        Signal.created_at >= start_date
    ).group_by(Signal.status)
    status_result = await db.execute(status_query)
    signals_by_status = {row.status: row[1] for row in status_result.all()}
    
    # Total tasks
    tasks_query = select(func.count(Task.id)).where(
        Task.created_at >= start_date
    )
    tasks_result = await db.execute(tasks_query)
    total_tasks = tasks_result.scalar() or 0
    
    # Tasks by status
    task_status_query = select(
        Task.status,
        func.count(Task.id)
    ).where(
        Task.created_at >= start_date
    ).group_by(Task.status)
    task_status_result = await db.execute(task_status_query)
    tasks_by_status = {row.status: row[1] for row in task_status_result.all()}
    
    # Total cost
    cost_query = select(func.sum(CostRecord.cost)).where(
        CostRecord.created_at >= start_date
    )
    cost_result = await db.execute(cost_query)
    total_cost = cost_result.scalar() or 0.0
    
    # Estimated revenue (from accepted signals)
    revenue_query = select(func.sum(Signal.estimated_revenue)).where(
        Signal.created_at >= start_date,
        Signal.status == "accepted"
    )
    revenue_result = await db.execute(revenue_query)
    estimated_revenue = revenue_result.scalar() or 0.0
    
    return StandardResponse(
        success=True,
        data={
            "period_days": days,
            "signals": {
                "total": total_signals,
                "by_status": signals_by_status,
            },
            "tasks": {
                "total": total_tasks,
                "by_status": tasks_by_status,
            },
            "financial": {
                "total_cost": round(total_cost, 6),
                "estimated_revenue": round(estimated_revenue, 2),
                "estimated_profit": round(estimated_revenue - total_cost, 2),
                "roi_percentage": round((estimated_revenue - total_cost) / total_cost * 100, 2) if total_cost > 0 else 0,
            },
        },
        message="Overview retrieved successfully"
    )


@router.get("/roi", response_model=StandardResponse)
async def get_roi_analysis(
    days: int = Query(30, ge=1, le=90),
    group_by: str = Query("task_type", regex="^(task_type|day|week)$"),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(verify_token),
):
    """Get ROI analysis grouped by task type, day, or week"""
    from datetime import datetime, timedelta
    
    start_date = datetime.utcnow() - timedelta(days=days)
    
    if group_by == "task_type":
        # Join tasks with cost records
        query = select(
            Task.task_type,
            func.sum(CostRecord.cost).label("total_cost"),
            func.count(Task.id).label("task_count"),
        ).join(
            CostRecord, CostRecord.task_id == Task.id
        ).where(
            Task.created_at >= start_date
        ).group_by(
            Task.task_type
        )
        
        result = await db.execute(query)
        rows = result.all()
        
        data = {
            "by_task_type": [
                {
                    "task_type": row.task_type or "unknown",
                    "total_cost": round(row.total_cost or 0, 6),
                    "task_count": row.task_count,
                }
                for row in rows
            ]
        }
        
    else:
        # Daily or weekly grouping
        query = select(
            func.date(Task.created_at).label("date"),
            func.sum(CostRecord.cost).label("total_cost"),
            func.count(Task.id).label("task_count"),
        ).join(
            CostRecord, CostRecord.task_id == Task.id
        ).where(
            Task.created_at >= start_date
        ).group_by(
            func.date(Task.created_at)
        ).order_by(
            func.date(Task.created_at)
        )
        
        result = await db.execute(query)
        rows = result.all()
        
        data = {
            "timeline": [
                {
                    "date": str(row.date),
                    "total_cost": round(row.total_cost or 0, 6),
                    "task_count": row.task_count,
                }
                for row in rows
            ]
        }
    
    return StandardResponse(
        success=True,
        data=data,
        message="ROI analysis retrieved successfully"
    )


@router.get("/success-rate", response_model=StandardResponse)
async def get_success_rate(
    days: int = Query(30, ge=1, le=90),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(verify_token),
):
    """Get success rate trends"""
    from datetime import datetime, timedelta
    
    start_date = datetime.utcnow() - timedelta(days=days)
    
    # Tasks completed vs failed
    query = select(
        Task.status,
        func.count(Task.id)
    ).where(
        Task.created_at >= start_date
    ).group_by(
        Task.status
    )
    
    result = await db.execute(query)
    rows = result.all()
    
    status_counts = {row.status: row[1] for row in rows}
    
    completed = status_counts.get("completed", 0)
    failed = status_counts.get("failed", 0)
    total = completed + failed
    
    success_rate = completed / total if total > 0 else 0
    
    return StandardResponse(
        success=True,
        data={
            "period_days": days,
            "total_evaluated": total,
            "completed": completed,
            "failed": failed,
            "success_rate": round(success_rate * 100, 2),
            "by_status": status_counts,
        },
        message="Success rate retrieved successfully"
    )
