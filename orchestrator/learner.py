"""
Learning Engine - Learn from execution results and improve system

Features:
1. Collect task feedback
2. Update knowledge base statistics
3. Detect patterns for Skill creation
4. Adjust evaluation weights
"""

import json
import logging
from datetime import datetime, timedelta
from typing import List, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.database import async_session_maker
from core.models import Signal, Task, TaskResult
from gateway.gateway import AIGateway
from knowledge.knowledge_base import KnowledgeBase
from knowledge.skills_store import SkillsStore

logger = logging.getLogger(__name__)


class LearningEngine:
    """
    Learning Engine - Continuous improvement
    
    Processes task feedback to:
    - Update knowledge base
    - Update skill statistics
    - Detect patterns for new skills
    - Adjust evaluation weights
    """
    
    # Threshold for skill creation: consecutive successes
    SKILL_CREATION_THRESHOLD = 3
    
    def __init__(self, gateway: AIGateway = None):
        self.gateway = gateway or AIGateway()
        self.knowledge = KnowledgeBase()
        self.skills_store = SkillsStore()
        self.logger = logging.getLogger(self.__class__.__name__)
    
    async def process_feedback(
        self,
        task: Task,
        result: TaskResult,
        human_feedback: dict = None
    ):
        """
        Process feedback from a completed task
        
        Steps:
        1. Record outcome to knowledge base
        2. Update skill statistics (if used)
        3. Update platform/category stats
        4. Check for skill creation trigger
        
        Args:
            task: Completed task
            result: Task execution result
            human_feedback: Optional human feedback
        """
        self.logger.info(f"Processing feedback for task {task.id}")
        
        # Build outcome data
        outcome = {
            "success": result.status == "completed",
            "revenue": 0,  # Would come from actual earnings
            "cost": result.total_cost,
            "time_hours": result.execution_time / 3600 if result.execution_time else 0,
            "quality_score": self._calculate_quality_score(result),
            "feedback": human_feedback,
        }
        
        # 1. Record to knowledge base
        await self.knowledge.record_outcome(
            signal_id=str(task.signal_id) if task.signal_id else None,
            task_id=str(task.id),
            outcome=outcome
        )
        
        # 2. Update skill statistics
        if task.skill_id:
            await self.skills_store.update_skill_stats(task.skill_id, outcome)
        
        # 3. Check for skill creation
        if task.signal_id and outcome["success"]:
            await self.check_skill_creation(task.signal_id, task)
    
    def _calculate_quality_score(self, result: TaskResult) -> float:
        """Calculate quality score from result"""
        score = 0.0
        
        # Check for deliverables
        output = result.output_data or {}
        
        if "code_files" in output and output["code_files"]:
            score += 30
        if "test_files" in output and output["test_files"]:
            score += 20
        if "doc_files" in output and output["doc_files"]:
            score += 20
        
        # Check cost efficiency
        if result.total_cost and result.total_cost < 1.0:
            score += 15
        
        # Check execution time
        if result.execution_time and result.execution_time < 300:  # < 5 min
            score += 15
        
        return min(score, 100)
    
    async def check_skill_creation(self, signal_id: str, task: Task):
        """
        Check if a new skill should be created
        
        Trigger: Same (source + required_skills) succeeded >= 3 times
        
        Args:
            signal_id: Signal ID
            task: The successful task
        """
        async with async_session_maker() as session:
            signal = await session.get(Signal, signal_id)
            if not signal:
                return
            
            # Find similar successful tasks
            query = select(Task).join(Signal).where(
                Signal.source == signal.source,
                Task.status == "completed",
                Task.skill_id.is_(None),  # Not already using a skill
            ).limit(10)
            
            result = await session.execute(query)
            similar_tasks = result.scalars().all()
            
            # Group by required_skills
            skill_groups = {}
            for t in similar_tasks:
                if t.signal_id:
                    s = await session.get(Signal, t.signal_id)
                    if s and s.required_skills:
                        key = tuple(sorted(s.required_skills))
                        if key not in skill_groups:
                            skill_groups[key] = []
                        skill_groups[key].append(t)
            
            # Check if any group meets threshold
            for skills_key, tasks in skill_groups.items():
                if len(tasks) >= self.SKILL_CREATION_THRESHOLD:
                    await self.draft_skill(list(skills_key), tasks)
    
    async def draft_skill(self, skills: List[str], similar_tasks: List[Task]):
        """
        Use Opus to draft a new skill from successful tasks
        
        Args:
            skills: List of required skills (the key)
            similar_tasks: List of successful similar tasks
        """
        self.logger.info(f"Drafting skill for {skills} from {len(similar_tasks)} tasks")
        
        # Build prompt
        tasks_summary = []
        for i, task in enumerate(similar_tasks[:3], 1):
            tasks_summary.append(f"""
Task {i}:
- Type: {task.task_type}
- Description: {task.input_data.get('description', 'N/A')}
- Cost: ${task.actual_cost or 0}
- Time: {task.output_data.get('execution_time', 0) / 3600:.1f}h
""")
        
        prompt = f"""You are a workflow expert. Analyze these successful tasks and extract a reusable skill definition.

Required Skills: {', '.join(skills)}

Successful Tasks:
{''.join(tasks_summary)}

Create a skill definition in YAML format:

```yaml
name: "Descriptive name for this skill"
category: "Category like web_scraping, api_integration, etc."
triggers:
  source: "platform name"
  keywords: ["keyword1", "keyword2"]
  min_budget: 100
  max_budget: 1000
workflow:
  steps:
    - name: "step_name"
      type: "auto|semi|manual"
      description: "What to do"
compliance:
  tos_compliant: true
  auto_executable: true
quality_checklist:
  - "Check 1"
  - "Check 2"
```

Extract the common workflow pattern that made these tasks successful."""
        
        try:
            response = await self.gateway.complete(
                prompt=prompt,
                model_tier="opus",
                system="You are a workflow designer. Create structured skill definitions.",
                temperature=0.3,
                max_tokens=2000,
            )
            
            # Parse YAML from response
            content = response.content
            if "```yaml" in content:
                content = content.split("```yaml")[1].split("```")[0].strip()
            elif "```" in content:
                content = content.split("```")[1].split("```")[0].strip()
            
            # In Phase 1, just log the draft
            self.logger.info(f"Skill draft generated:\n{content}")
            
            # Phase 2: Parse YAML and create skill
            # skill_data = yaml.safe_load(content)
            # await self.skills_store.create_skill(skill_data)
            
        except Exception as e:
            self.logger.error(f"Failed to draft skill: {e}")
    
    async def update_evaluation_weights(self):
        """
        Adjust evaluation weights based on historical data
        
        This would run periodically (e.g., weekly) to optimize:
        - Which dimensions correlate with success
        - Adjust weights by ±5% max
        """
        self.logger.info("Updating evaluation weights...")
        
        # Query historical evaluations
        async with async_session_maker() as session:
            # Get signals with scores and outcomes
            query = select(Signal).where(
                Signal.score.isnot(None),
                Signal.status.in_(["completed", "rejected"])
            )
            
            result = await session.execute(query)
            signals = result.scalars().all()
            
            if len(signals) < 10:
                self.logger.info("Not enough data to update weights")
                return
            
            # Analyze correlation between scores and success
            # This is a simplified version
            successful = [s for s in signals if s.status == "completed"]
            failed = [s for s in signals if s.status == "rejected"]
            
            if successful and failed:
                avg_success_score = sum(s.score for s in successful) / len(successful)
                avg_fail_score = sum(s.score for s in failed) / len(failed)
                
                self.logger.info(
                    f"Score analysis: successful={avg_success_score:.1f}, "
                    f"failed={avg_fail_score:.1f}"
                )
                
                # If scores don't discriminate well, weights may need adjustment
                if avg_success_score - avg_fail_score < 10:
                    self.logger.warning("Score discrimination is low, consider adjusting weights")
    
    async def run_periodic_learning(self):
        """
        Run periodic learning tasks
        
        Call this on a schedule (e.g., daily or weekly)
        """
        self.logger.info("Running periodic learning...")
        
        # Update evaluation weights
        await self.update_evaluation_weights()
        
        # Other periodic tasks
        # - Archive old data
        # - Generate reports
        # - etc.
        
        self.logger.info("Periodic learning complete")


# Global learner instance
learner = LearningEngine()
