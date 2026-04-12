"""
Signals API Routes

Endpoints:
- GET /api/signals - List signals with filtering
- GET /api/signals/{id} - Get signal details
- POST /api/signals/{id}/act - Take action on signal
"""

from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.auth import User, verify_token
from core.database import get_db
from core.models import Signal, SignalStatus
from core.queue import queue_manager

router = APIRouter()


# Pydantic schemas
class SignalListResponse(BaseModel):
    id: str
    source: str
    scout_type: str
    title: str
    estimated_revenue: Optional[float]
    score: Optional[float]
    status: str
    created_at: str
    
    class Config:
        from_attributes = True


class SignalDetailResponse(SignalListResponse):
    description: Optional[str]
    estimated_effort_hours: Optional[float]
    urgency: str
    required_skills: List[str]
    raw_url: Optional[str]
    requires_human_interaction: bool
    compliance_flags: List[str]
    metadata: dict
    updated_at: Optional[str]


class SignalActionRequest(BaseModel):
    action: str  # accept, reject, modify
    notes: Optional[str] = None
    modified_score: Optional[float] = None


class StandardResponse(BaseModel):
    success: bool
    data: Optional[dict] = None
    message: str


@router.get("", response_model=StandardResponse)
async def list_signals(
    status: Optional[str] = Query(None, description="Filter by status"),
    source: Optional[str] = Query(None, description="Filter by source"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(verify_token),
):
    """
    List signals with optional filtering and pagination
    """
    query = select(Signal)
    
    # Apply filters
    if status:
        query = query.where(Signal.status == status)
    if source:
        query = query.where(Signal.source == source)
    
    # Order by created_at desc
    query = query.order_by(Signal.created_at.desc())
    
    # Pagination
    offset = (page - 1) * page_size
    query = query.offset(offset).limit(page_size)
    
    result = await db.execute(query)
    signals = result.scalars().all()
    
    # Get total count
    count_query = select(Signal)
    if status:
        count_query = count_query.where(Signal.status == status)
    if source:
        count_query = count_query.where(Signal.source == source)
    count_result = await db.execute(count_query)
    total = len(count_result.scalars().all())
    
    return StandardResponse(
        success=True,
        data={
            "items": [
                {
                    "id": str(s.id),
                    "source": s.source,
                    "scout_type": s.scout_type,
                    "title": s.title,
                    "estimated_revenue": s.estimated_revenue,
                    "score": s.score,
                    "status": s.status,
                    "created_at": s.created_at.isoformat() if s.created_at else None,
                }
                for s in signals
            ],
            "pagination": {
                "page": page,
                "page_size": page_size,
                "total": total,
                "pages": (total + page_size - 1) // page_size,
            }
        },
        message="Signals retrieved successfully"
    )


@router.get("/{signal_id}", response_model=StandardResponse)
async def get_signal(
    signal_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(verify_token),
):
    """
    Get detailed information about a specific signal
    """
    signal = await db.get(Signal, signal_id)
    
    if not signal:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Signal not found"
        )
    
    return StandardResponse(
        success=True,
        data={
            "id": str(signal.id),
            "source": signal.source,
            "scout_type": signal.scout_type,
            "title": signal.title,
            "description": signal.description,
            "estimated_revenue": signal.estimated_revenue,
            "estimated_effort_hours": signal.estimated_effort_hours,
            "urgency": signal.urgency,
            "required_skills": signal.required_skills or [],
            "raw_url": signal.raw_url,
            "score": signal.score,
            "status": signal.status,
            "requires_human_interaction": signal.requires_human_interaction,
            "compliance_flags": signal.compliance_flags or [],
            "metadata": signal.metadata or {},
            "created_at": signal.created_at.isoformat() if signal.created_at else None,
            "updated_at": signal.updated_at.isoformat() if signal.updated_at else None,
        },
        message="Signal retrieved successfully"
    )


@router.post("/{signal_id}/act", response_model=StandardResponse)
async def act_on_signal(
    signal_id: UUID,
    action_req: SignalActionRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(verify_token),
):
    """
    Take action on a signal:
    - accept: Manually accept a pending signal
    - reject: Reject and discard
    - modify: Modify evaluation parameters
    """
    signal = await db.get(Signal, signal_id)
    
    if not signal:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Signal not found"
        )
    
    if action_req.action == "accept":
        signal.status = SignalStatus.ACCEPTED
        signal.score = action_req.modified_score or signal.score or 75.0
        
        # Enqueue for dispatch
        await queue_manager.connect()
        await queue_manager.enqueue_signal_evaluated(signal.to_dict())
        
        message = "Signal accepted and queued for execution"
        
    elif action_req.action == "reject":
        signal.status = SignalStatus.REJECTED
        message = "Signal rejected"
        
    elif action_req.action == "modify":
        if action_req.modified_score is not None:
            signal.score = action_req.modified_score
        signal.metadata = {
            **(signal.metadata or {}),
            "manual_modification": {
                "modified_by": user.username,
                "notes": action_req.notes,
            }
        }
        message = "Signal modified"
        
    else:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid action: {action_req.action}"
        )
    
    await db.commit()
    
    return StandardResponse(
        success=True,
        data={"signal_id": str(signal_id), "action": action_req.action},
        message=message
    )
