"""
Knowledge Base - Experience data storage and retrieval

Phase 1: Simplified implementation using PostgreSQL
Phase 2: Vector retrieval with pgvector
"""

import logging
from typing import List, Optional

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from core.database import async_session_maker
from core.models import Signal, Task, TaskResult

logger = logging.getLogger(__name__)


class KnowledgeBase:
    """
    Knowledge Base for storing and retrieving experience data
    
    Features:
    - Record task outcomes
    - Query similar historical signals
    - Get category/platform statistics
    - Search lessons learned
    """
    
    def __init__(self):
        self.logger = logging.getLogger(self.__class__.__name__)
    
    async def record_outcome(
        self,
        signal_id: str,
        task_id: str,
        outcome: dict
    ):
        """
        Record the outcome of a task execution
        
        Args:
            signal_id: Associated signal ID
            task_id: Associated task ID
            outcome: Dict with success, revenue, cost, time, etc.
        """
        async with async_session_maker() as session:
            # Store in task metadata for now
            task = await session.get(Task, task_id)
            if task:
                task.metadata = {
                    **(task.metadata or {}),
                    "outcome": {
                        "success": outcome.get("success", False),
                        "revenue": outcome.get("revenue", 0),
                        "cost": outcome.get("cost", 0),
                        "time_hours": outcome.get("time_hours", 0),
                        "recorded_at": datetime.utcnow().isoformat(),
                    }
                }
                await session.commit()
                self.logger.debug(f"Recorded outcome for task {task_id}")
    
    async def get_similar_signals(
        self,
        signal: Signal,
        limit: int = 5
    ) -> List[dict]:
        """
        Find similar historical signals
        
        Phase 1: Keyword matching
        Phase 2: Vector similarity
        
        Args:
            signal: Signal to match against
            limit: Max results to return
            
        Returns:
            List of similar signals with outcome data
        """
        async with async_session_maker() as session:
            # Simple keyword matching for Phase 1
            # Get signals from same source with similar skills
            query = select(Signal).where(
                Signal.source == signal.source,
                Signal.status.in_(["accepted", "completed", "rejected"]),
            ).limit(limit)
            
            result = await session.execute(query)
            signals = result.scalars().all()
            
            return [
                {
                    "id": str(s.id),
                    "title": s.title,
                    "source": s.source,
                    "score": s.score,
                    "status": s.status,
                    "metadata": s.metadata,
                }
                for s in signals
            ]
    
    async def get_category_stats(self, category: str) -> dict:
        """
        Get statistics for a task category
        
        Args:
            category: Category name (e.g., "upwork:freelance")
            
        Returns:
            Statistics dict
        """
        async with async_session_maker() as session:
            # Parse category
            parts = category.split(":")
            source = parts[0] if parts else ""
            
            # Query signals from this source
            query = select(
                func.count(Signal.id).label("total"),
                func.avg(Signal.score).label("avg_score"),
            ).where(
                Signal.source == source
            )
            
            result = await session.execute(query)
            row = result.one()
            
            # Query completed tasks for success rate
            task_query = select(
                func.count(Task.id).label("total"),
                func.sum(Task.actual_cost).label("total_cost"),
            ).join(
                Signal, Task.signal_id == Signal.id
            ).where(
                Signal.source == source,
                Task.status == "completed"
            )
            
            task_result = await session.execute(task_query)
            task_row = task_result.one()
            
            return {
                "total_count": row.total or 0,
                "avg_score": float(row.avg_score or 0),
                "avg_revenue": 0.0,  # Would come from outcome data
                "avg_ai_cost": float(task_row.total_cost or 0) / (task_row.total or 1),
                "avg_time_hours": 0.0,
                "success_rate": 0.0,  # Calculate from completed vs failed
            }
    
    async def get_platform_stats(self, platform: str) -> dict:
        """Get statistics for a platform"""
        return await self.get_category_stats(platform)
    
    async def search_lessons(self, query: str) -> List[dict]:
        """
        Search for lessons learned
        
        Phase 1: Simple keyword search in metadata
        Phase 2: Vector search
        
        Args:
            query: Search query
            
        Returns:
            List of relevant lessons
        """
        # Phase 1: Search in task metadata
        async with async_session_maker() as session:
            # Get tasks with outcomes
            sql = select(Task).where(
                Task.metadata.isnot(None)
            ).limit(10)
            
            result = await session.execute(sql)
            tasks = result.scalars().all()
            
            lessons = []
            for task in tasks:
                outcome = task.metadata.get("outcome", {})
                if outcome:
                    lessons.append({
                        "task_id": str(task.id),
                        "task_type": task.task_type,
                        "success": outcome.get("success"),
                        "lesson": outcome.get("lesson", "No lesson recorded"),
                    })
            
            return lessons


from datetime import datetime
