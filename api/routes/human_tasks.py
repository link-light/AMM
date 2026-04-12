"""
Human Tasks API Routes

Endpoints:
- GET /api/human-tasks - List pending human tasks
- GET /api/human-tasks/{id} - Get task details
- POST /api/human-tasks/{id}/done - Mark as complete
- POST /api/human-tasks/{id}/skip - Skip task
"""

from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.auth import User, verify_token
from core.database import get_db
from core.models import HumanTask, HumanTaskStatus

router = APIRouter()


class HumanTaskListResponse(BaseModel):
    id: str
    task_type: str
    platform: Optional[str]
    priority: str
    status: str
    deadline: Optional[str]
    created_at: str


class HumanTaskDetailResponse(HumanTaskListResponse):
    task_id: str
    prepared_materials: dict
    instructions: Optional[str]
    target_url: Optional[str]
    completed_by: Optional[str]
    completion_notes: Optional[str]
    completed_at: Optional[str]


class CompleteTaskRequest(BaseModel):
    notes: Optional[str] = None
    result_url: Optional[str] = None


class SkipTaskRequest(BaseModel):
    reason: Optional[str] = None


class StandardResponse(BaseModel):
    success: bool
    data: Optional[dict] = None
    message: str


@router.get("", response_model=StandardResponse)
async def list_human_tasks(
    status: Optional[str] = Query("pending"),
    priority: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(verify_token),
):
    """List human tasks, sorted by priority and deadline"""
    query = select(HumanTask)
    
    if status:
        query = query.where(HumanTask.status == status)
    if priority:
        query = query.where(HumanTask.priority == priority)
    
    # Sort by priority desc, deadline asc, created_at asc
    query = query.order_by(
        HumanTask.priority.desc(),
        HumanTask.deadline.asc().nullslast(),
        HumanTask.created_at.asc()
    )
    
    offset = (page - 1) * page_size
    query = query.offset(offset).limit(page_size)
    
    result = await db.execute(query)
    tasks = result.scalars().all()
    
    return StandardResponse(
        success=True,
        data={
            "items": [
                {
                    "id": str(t.id),
                    "task_type": t.task_type,
                    "platform": t.platform,
                    "priority": t.priority,
                    "status": t.status,
                    "deadline": t.deadline.isoformat() if t.deadline else None,
                    "created_at": t.created_at.isoformat() if t.created_at else None,
                }
                for t in tasks
            ],
            "pagination": {
                "page": page,
                "page_size": page_size,
                "total": len(tasks),
            }
        },
        message="Human tasks retrieved successfully"
    )


@router.get("/{task_id}", response_model=StandardResponse)
async def get_human_task(
    task_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(verify_token),
):
    """Get human task details with materials"""
    task = await db.get(HumanTask, task_id)
    
    if not task:
        raise HTTPException(status_code=404, detail="Human task not found")
    
    return StandardResponse(
        success=True,
        data={
            "id": str(task.id),
            "task_id": str(task.task_id),
            "task_type": task.task_type,
            "platform": task.platform,
            "priority": task.priority,
            "status": task.status,
            "prepared_materials": task.prepared_materials or {},
            "instructions": task.instructions,
            "target_url": task.target_url,
            "deadline": task.deadline.isoformat() if task.deadline else None,
            "completed_by": task.completed_by,
            "completion_notes": task.completion_notes,
            "completed_at": task.completed_at.isoformat() if task.completed_at else None,
            "created_at": task.created_at.isoformat() if task.created_at else None,
        },
        message="Human task retrieved successfully"
    )


@router.post("/{task_id}/done", response_model=StandardResponse)
async def complete_human_task(
    task_id: UUID,
    complete_req: CompleteTaskRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(verify_token),
):
    """Mark human task as completed"""
    task = await db.get(HumanTask, task_id)
    
    if not task:
        raise HTTPException(status_code=404, detail="Human task not found")
    
    if task.status != HumanTaskStatus.PENDING:
        raise HTTPException(status_code=400, detail="Task is not pending")
    
    from datetime import datetime
    
    task.status = HumanTaskStatus.COMPLETED
    task.completed_by = user.username
    task.completion_notes = complete_req.notes
    task.completed_at = datetime.utcnow()
    
    if complete_req.result_url:
        task.prepared_materials = {
            **(task.prepared_materials or {}),
            "result_url": complete_req.result_url,
        }
    
    await db.commit()
    
    return StandardResponse(
        success=True,
        data={"task_id": str(task_id)},
        message="Human task marked as completed"
    )


@router.post("/{task_id}/skip", response_model=StandardResponse)
async def skip_human_task(
    task_id: UUID,
    skip_req: SkipTaskRequest = None,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(verify_token),
):
    """Skip a human task"""
    task = await db.get(HumanTask, task_id)
    
    if not task:
        raise HTTPException(status_code=404, detail="Human task not found")
    
    if task.status != HumanTaskStatus.PENDING:
        raise HTTPException(status_code=400, detail="Task is not pending")
    
    task.status = HumanTaskStatus.SKIPPED
    task.completion_notes = skip_req.reason if skip_req else "Skipped by user"
    
    await db.commit()
    
    return StandardResponse(
        success=True,
        data={"task_id": str(task_id)},
        message="Human task skipped"
    )
