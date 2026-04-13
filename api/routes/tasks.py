"""
Tasks API Routes

Endpoints:
- GET /api/tasks - List tasks with filtering
- GET /api/tasks/{id} - Get task details
- POST /api/tasks/{id}/review - Manual review
- POST /api/tasks/{id}/cancel - Cancel task
"""

from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.auth import User, verify_token
from core.database import get_db
from core.models import Task, TaskStatus

router = APIRouter()


class TaskListResponse(BaseModel):
    id: str
    title: Optional[str]
    task_type: Optional[str]
    status: str
    priority: str
    assigned_worker: Optional[str]
    actual_cost: Optional[float]
    created_at: str


class TaskDetailResponse(TaskListResponse):
    signal_id: Optional[str]
    parent_task_id: Optional[str]
    execution_type: str
    skill_id: Optional[str]
    input_data: dict
    output_data: Optional[dict]
    error_message: Optional[str]
    estimated_cost: Optional[float]
    depends_on: List[str]
    started_at: Optional[str]
    completed_at: Optional[str]


class TaskReviewRequest(BaseModel):
    passed: bool
    notes: Optional[str] = None


class TaskCancelRequest(BaseModel):
    reason: Optional[str] = None


class StandardResponse(BaseModel):
    success: bool
    data: Optional[dict] = None
    message: str


@router.get("", response_model=StandardResponse)
async def list_tasks(
    status: Optional[str] = Query(None),
    task_type: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(verify_token),
):
    """List tasks with filtering"""
    query = select(Task)
    
    if status:
        query = query.where(Task.status == status)
    if task_type:
        query = query.where(Task.task_type == task_type)
    
    query = query.order_by(Task.created_at.desc())
    
    offset = (page - 1) * page_size
    query = query.offset(offset).limit(page_size)
    
    result = await db.execute(query)
    tasks = result.scalars().all()
    
    # Count
    count_query = select(Task)
    if status:
        count_query = count_query.where(Task.status == status)
    if task_type:
        count_query = count_query.where(Task.task_type == task_type)
    count_result = await db.execute(count_query)
    total = len(count_result.scalars().all())
    
    return StandardResponse(
        success=True,
        data={
            "items": [
                {
                    "id": str(t.id),
                    "title": t.title,
                    "task_type": t.task_type,
                    "status": t.status,
                    "priority": t.priority,
                    "assigned_worker": t.assigned_worker,
                    "actual_cost": t.actual_cost,
                    "created_at": t.created_at.isoformat() if t.created_at else None,
                }
                for t in tasks
            ],
            "pagination": {
                "page": page,
                "page_size": page_size,
                "total": total,
            }
        },
        message="Tasks retrieved successfully"
    )


@router.get("/{task_id}", response_model=StandardResponse)
async def get_task(
    task_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(verify_token),
):
    """Get task details with subtasks and dependencies"""
    task = await db.get(Task, task_id)
    
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    
    # Get subtasks
    subtasks_query = select(Task).where(Task.parent_task_id == task_id)
    subtasks_result = await db.execute(subtasks_query)
    subtasks = subtasks_result.scalars().all()
    
    return StandardResponse(
        success=True,
        data={
            "id": str(task.id),
            "signal_id": str(task.signal_id) if task.signal_id else None,
            "parent_task_id": str(task.parent_task_id) if task.parent_task_id else None,
            "title": task.title,
            "task_type": task.task_type,
            "execution_type": task.execution_type,
            "status": task.status,
            "priority": task.priority,
            "assigned_worker": task.assigned_worker,
            "skill_id": task.skill_id,
            "input_data": task.input_data or {},
            "output_data": task.output_data,
            "error_message": task.error_message,
            "estimated_cost": task.estimated_cost,
            "actual_cost": task.actual_cost,
            "depends_on": task.depends_on or [],
            "started_at": task.started_at.isoformat() if task.started_at else None,
            "completed_at": task.completed_at.isoformat() if task.completed_at else None,
            "created_at": task.created_at.isoformat() if task.created_at else None,
            "subtasks": [
                {"id": str(st.id), "title": st.title, "status": st.status}
                for st in subtasks
            ],
        },
        message="Task retrieved successfully"
    )


@router.post("/{task_id}/review", response_model=StandardResponse)
async def review_task(
    task_id: UUID,
    review_req: TaskReviewRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(verify_token),
):
    """Manually review a task"""
    task = await db.get(Task, task_id)
    
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    
    task.metadata = {
        **(task.metadata or {}),
        "manual_review": {
            "reviewer": user.username,
            "passed": review_req.passed,
            "notes": review_req.notes,
            "reviewed_at": datetime.utcnow().isoformat(),
        }
    }
    
    if review_req.passed:
        task.status = TaskStatus.COMPLETED
    else:
        task.status = TaskStatus.FAILED
    
    await db.commit()
    
    return StandardResponse(
        success=True,
        data={"task_id": str(task_id), "passed": review_req.passed},
        message="Task review recorded"
    )


@router.post("/{task_id}/cancel", response_model=StandardResponse)
async def cancel_task(
    task_id: UUID,
    cancel_req: TaskCancelRequest = None,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(verify_token),
):
    """Cancel a task"""
    task = await db.get(Task, task_id)
    
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    
    if task.status in [TaskStatus.COMPLETED, TaskStatus.FAILED]:
        raise HTTPException(status_code=400, detail="Cannot cancel completed/failed task")
    
    task.status = TaskStatus.CANCELLED
    task.metadata = {
        **(task.metadata or {}),
        "cancellation": {
            "cancelled_by": user.username,
            "reason": cancel_req.reason if cancel_req else None,
            "cancelled_at": datetime.utcnow().isoformat(),
        }
    }
    
    await db.commit()
    
    return StandardResponse(
        success=True,
        data={"task_id": str(task_id)},
        message="Task cancelled"
    )


from datetime import datetime
