"""
Skills API Routes

Endpoints:
- GET /api/skills - List skills
- GET /api/skills/{id} - Get skill details
- POST /api/skills - Create skill
- PUT /api/skills/{id} - Update skill
"""

from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.auth import User, verify_token
from core.database import get_db
from core.models import Skill, SkillStatus

router = APIRouter()


class SkillListResponse(BaseModel):
    id: str
    name: str
    version: str
    category: Optional[str]
    status: str
    success_rate: float
    execution_count: int
    created_at: str


class SkillDetailResponse(SkillListResponse):
    avg_revenue: float
    avg_ai_cost: float
    avg_time_hours: float
    triggers: dict
    compliance: dict
    workflow: dict
    quality_checklist: List[str]
    updated_at: Optional[str]


class CreateSkillRequest(BaseModel):
    id: str
    name: str
    category: Optional[str] = None
    triggers: dict = {}
    compliance: dict = {}
    workflow: dict = {}
    quality_checklist: List[str] = []


class UpdateSkillRequest(BaseModel):
    name: Optional[str] = None
    category: Optional[str] = None
    status: Optional[str] = None
    triggers: Optional[dict] = None
    compliance: Optional[dict] = None
    workflow: Optional[dict] = None
    quality_checklist: Optional[List[str]] = None


class StandardResponse(BaseModel):
    success: bool
    data: Optional[dict] = None
    message: str


@router.get("", response_model=StandardResponse)
async def list_skills(
    category: Optional[str] = Query(None),
    status: Optional[str] = Query("active"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(verify_token),
):
    """List skills with filtering"""
    query = select(Skill)
    
    if category:
        query = query.where(Skill.category == category)
    if status:
        query = query.where(Skill.status == status)
    
    query = query.order_by(Skill.success_rate.desc())
    
    offset = (page - 1) * page_size
    query = query.offset(offset).limit(page_size)
    
    result = await db.execute(query)
    skills = result.scalars().all()
    
    return StandardResponse(
        success=True,
        data={
            "items": [
                {
                    "id": s.id,
                    "name": s.name,
                    "version": s.version,
                    "category": s.category,
                    "status": s.status,
                    "success_rate": s.success_rate,
                    "execution_count": s.execution_count,
                    "created_at": s.created_at.isoformat() if s.created_at else None,
                }
                for s in skills
            ],
            "pagination": {
                "page": page,
                "page_size": page_size,
                "total": len(skills),
            }
        },
        message="Skills retrieved successfully"
    )


@router.get("/{skill_id}", response_model=StandardResponse)
async def get_skill(
    skill_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(verify_token),
):
    """Get skill details with execution statistics"""
    skill = await db.get(Skill, skill_id)
    
    if not skill:
        raise HTTPException(status_code=404, detail="Skill not found")
    
    return StandardResponse(
        success=True,
        data={
            "id": skill.id,
            "name": skill.name,
            "version": skill.version,
            "category": skill.category,
            "status": skill.status,
            "success_rate": skill.success_rate,
            "avg_revenue": skill.avg_revenue,
            "avg_ai_cost": skill.avg_ai_cost,
            "avg_time_hours": skill.avg_time_hours,
            "execution_count": skill.execution_count,
            "triggers": skill.triggers or {},
            "compliance": skill.compliance or {},
            "workflow": skill.workflow or {},
            "quality_checklist": skill.quality_checklist or [],
            "created_at": skill.created_at.isoformat() if skill.created_at else None,
            "updated_at": skill.updated_at.isoformat() if skill.updated_at else None,
        },
        message="Skill retrieved successfully"
    )


@router.post("", response_model=StandardResponse, status_code=status.HTTP_201_CREATED)
async def create_skill(
    req: CreateSkillRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(verify_token),
):
    """Create a new skill"""
    # Check if skill exists
    existing = await db.get(Skill, req.id)
    if existing:
        raise HTTPException(status_code=400, detail="Skill with this ID already exists")
    
    skill = Skill(
        id=req.id,
        name=req.name,
        category=req.category,
        triggers=req.triggers,
        compliance=req.compliance,
        workflow=req.workflow,
        quality_checklist=req.quality_checklist,
        status=SkillStatus.DRAFT,
    )
    
    db.add(skill)
    await db.commit()
    await db.refresh(skill)
    
    return StandardResponse(
        success=True,
        data={"id": skill.id},
        message="Skill created successfully"
    )


@router.put("/{skill_id}", response_model=StandardResponse)
async def update_skill(
    skill_id: str,
    req: UpdateSkillRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(verify_token),
):
    """Update an existing skill"""
    skill = await db.get(Skill, skill_id)
    
    if not skill:
        raise HTTPException(status_code=404, detail="Skill not found")
    
    if req.name is not None:
        skill.name = req.name
    if req.category is not None:
        skill.category = req.category
    if req.status is not None:
        skill.status = req.status
    if req.triggers is not None:
        skill.triggers = req.triggers
    if req.compliance is not None:
        skill.compliance = req.compliance
    if req.workflow is not None:
        skill.workflow = req.workflow
    if req.quality_checklist is not None:
        skill.quality_checklist = req.quality_checklist
    
    await db.commit()
    await db.refresh(skill)
    
    return StandardResponse(
        success=True,
        data={"id": skill.id},
        message="Skill updated successfully"
    )
