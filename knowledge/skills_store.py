"""
Skills Store - Skill management and matching

Manages Skill CRUD and matches signals to skills.
"""

import logging
from typing import List, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.database import async_session_maker
from core.models import Signal, Skill, SkillStatus

logger = logging.getLogger(__name__)


class SkillsStore:
    """
    Store and match Skills
    
    Features:
    - Create/update skills
    - Match signals to skills
    - Update skill statistics
    """
    
    def __init__(self):
        self.logger = logging.getLogger(self.__class__.__name__)
    
    async def find_matching_skill(self, signal: Signal) -> Optional[Skill]:
        """
        Find the best matching skill for a signal
        
        Matching rules:
        1. Source matches
        2. Keywords intersection >= 2
        3. Budget within range
        4. Skill status is active
        
        Returns best match by success_rate
        """
        async with async_session_maker() as session:
            # Get all active skills
            query = select(Skill).where(
                Skill.status == SkillStatus.ACTIVE
            )
            
            result = await session.execute(query)
            skills = result.scalars().all()
            
            matches = []
            signal_skills = set(s.lower() for s in (signal.required_skills or []))
            
            for skill in skills:
                triggers = skill.triggers or {}
                
                # Check source match
                if triggers.get("source") and triggers["source"] != signal.source:
                    continue
                
                # Check keywords match
                skill_keywords = set(k.lower() for k in triggers.get("keywords", []))
                common_keywords = signal_skills & skill_keywords
                
                if len(common_keywords) < 2:
                    continue
                
                # Check budget range
                min_budget = triggers.get("min_budget", 0)
                max_budget = triggers.get("max_budget", float('inf'))
                revenue = signal.estimated_revenue or 0
                
                if revenue < min_budget or revenue > max_budget:
                    continue
                
                # Calculate match score
                match_score = len(common_keywords) * 10 + skill.success_rate * 100
                
                matches.append((skill, match_score))
            
            # Sort by match score and return best
            if matches:
                matches.sort(key=lambda x: x[1], reverse=True)
                return matches[0][0]
            
            return None
    
    async def create_skill(self, skill_data: dict) -> Skill:
        """
        Create a new skill
        
        Args:
            skill_data: Skill definition dict
            
        Returns:
            Created Skill
        """
        async with async_session_maker() as session:
            skill = Skill(
                id=skill_data["id"],
                name=skill_data["name"],
                version=skill_data.get("version", "1.0"),
                category=skill_data.get("category"),
                status=SkillStatus.DRAFT,
                triggers=skill_data.get("triggers", {}),
                compliance=skill_data.get("compliance", {}),
                workflow=skill_data.get("workflow", {}),
                quality_checklist=skill_data.get("quality_checklist", []),
            )
            
            session.add(skill)
            await session.commit()
            await session.refresh(skill)
            
            self.logger.info(f"Created skill: {skill.id}")
            return skill
    
    async def update_skill_stats(self, skill_id: str, outcome: dict):
        """
        Update skill statistics from execution outcome
        
        Args:
            skill_id: Skill ID
            outcome: Dict with success, revenue, cost, time
        """
        async with async_session_maker() as session:
            skill = await session.get(Skill, skill_id)
            if not skill:
                self.logger.warning(f"Skill {skill_id} not found")
                return
            
            # Update execution count
            skill.execution_count += 1
            
            # Update success rate
            success = outcome.get("success", False)
            current_success_rate = skill.success_rate or 0
            new_success_rate = (
                (current_success_rate * (skill.execution_count - 1) + (1.0 if success else 0.0))
                / skill.execution_count
            )
            skill.success_rate = new_success_rate
            
            # Update averages
            revenue = outcome.get("revenue", 0)
            cost = outcome.get("cost", 0)
            time_hours = outcome.get("time_hours", 0)
            
            if skill.execution_count == 1:
                skill.avg_revenue = revenue
                skill.avg_ai_cost = cost
                skill.avg_time_hours = time_hours
            else:
                n = skill.execution_count
                skill.avg_revenue = (skill.avg_revenue * (n - 1) + revenue) / n
                skill.avg_ai_cost = (skill.avg_ai_cost * (n - 1) + cost) / n
                skill.avg_time_hours = (skill.avg_time_hours * (n - 1) + time_hours) / n
            
            await session.commit()
            self.logger.debug(f"Updated stats for skill {skill_id}")
    
    async def get_skill(self, skill_id: str) -> Optional[Skill]:
        """Get skill by ID"""
        async with async_session_maker() as session:
            return await session.get(Skill, skill_id)
    
    async def list_skills(
        self,
        category: str = None,
        status: str = "active"
    ) -> List[Skill]:
        """
        List skills with optional filtering
        
        Args:
            category: Filter by category
            status: Filter by status
            
        Returns:
            List of Skills
        """
        async with async_session_maker() as session:
            query = select(Skill)
            
            if category:
                query = query.where(Skill.category == category)
            if status:
                query = query.where(Skill.status == status)
            
            query = query.order_by(Skill.success_rate.desc())
            
            result = await session.execute(query)
            return result.scalars().all()
    
    async def activate_skill(self, skill_id: str):
        """Activate a draft skill"""
        async with async_session_maker() as session:
            skill = await session.get(Skill, skill_id)
            if skill:
                skill.status = SkillStatus.ACTIVE
                await session.commit()
                self.logger.info(f"Activated skill: {skill_id}")
    
    async def deprecate_skill(self, skill_id: str):
        """Deprecate a skill (no longer use for matching)"""
        async with async_session_maker() as session:
            skill = await session.get(Skill, skill_id)
            if skill:
                skill.status = SkillStatus.DEPRECATED
                await session.commit()
                self.logger.info(f"Deprecated skill: {skill_id}")
