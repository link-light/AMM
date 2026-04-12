"""
Task Dispatcher - Decomposes opportunities into tasks and assigns execution types

Features:
1. Decomposes opportunities into subtasks using AI
2. Assigns execution types (auto/semi/manual)
3. Handles task dependencies
4. Pushes to appropriate queues
"""

import asyncio
import json
import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.config import settings
from core.database import async_session_maker
from core.models import (
    ExecutionType,
    Priority,
    Signal,
    SignalStatus,
    Task,
    TaskStatus,
    TaskType,
)
from core.queue import queue_manager
from gateway.gateway import AIGateway
from orchestrator.compliance import ComplianceGateway, ComplianceLevel
from orchestrator.evaluator import EvaluationResult

logger = logging.getLogger(__name__)


@dataclass
class TaskDefinition:
    """Definition of a task to be created"""
    title: str
    task_type: TaskType
    description: str
    execution_type: ExecutionType
    depends_on: List[str] = field(default_factory=list)
    estimated_time: float = 0.0
    requires_platform_interaction: bool = False
    platform: str = ""
    platform_action: str = ""


class TaskDispatcher:
    """
    Dispatches evaluated opportunities as tasks
    
    Consumes: queue:signals:evaluated
    Produces: Tasks in DB + queue:tasks:pending + queue:tasks:human
    """
    
    def __init__(
        self,
        gateway: AIGateway = None,
        compliance: ComplianceGateway = None
    ):
        self.gateway = gateway or AIGateway()
        self.compliance = compliance or ComplianceGateway()
        self.logger = logging.getLogger(self.__class__.__name__)
    
    def _build_decomposition_prompt(
        self,
        signal: Signal,
        evaluation: EvaluationResult
    ) -> str:
        """
        Build prompt for AI task decomposition
        
        This is critical for proper task breakdown.
        """
        return f"""You are a project management expert. Decompose the following opportunity into actionable tasks.

## Opportunity

**Title**: {signal.title}
**Description**: {signal.description or "N/A"}
**Platform**: {signal.source}
**Budget**: ${signal.estimated_revenue or evaluation.suggested_price}
**Required Skills**: {', '.join(evaluation.recommended_skills) if evaluation.recommended_skills else 'Not specified'}
**Execution Plan**: {evaluation.execution_plan_summary or "Not provided"}

## Task Types

- **coding**: Programming tasks, scripts, applications
- **content**: Writing, documentation, copywriting
- **design**: Graphics, UI/UX, logos
- **marketing**: SEO, social media, campaigns
- **research**: Analysis, data gathering, investigation
- **human**: Tasks requiring platform interaction (proposals, messages, etc.)

## Execution Types

- **auto**: Fully automated, no human intervention needed
- **semi**: Automated with human confirmation required
- **manual**: Must be done by human

## Rules

1. Mark tasks requiring platform interaction (submitting proposals, sending messages, delivering work) as:
   - task_type: "human"
   - execution_type: "manual"
   - requires_platform_interaction: true
   - specify platform and platform_action

2. Break down complex tasks into smaller, manageable pieces
3. Identify dependencies between tasks
4. Estimate time for each task

## Output Format

Return ONLY a JSON array of tasks:

[
  {{
    "title": "Task title",
    "task_type": "coding|content|design|marketing|research|human",
    "description": "Detailed description",
    "execution_type": "auto|semi|manual",
    "depends_on": [],
    "estimated_time": 2.5,
    "requires_platform_interaction": false,
    "platform": "upwork|fiverr|github|",
    "platform_action": ""
  }}
]

Guidelines:
- Usually 3-7 tasks per opportunity
- First task should often be "human" for submitting a proposal
- Last task should be delivery (often "human")
- Coding tasks can usually be "auto"
- Any action on the freelance platform should be "human"""

    def _parse_tasks(self, response_text: str, signal: Signal) -> List[TaskDefinition]:
        """Parse AI response into TaskDefinitions"""
        try:
            # Extract JSON
            text = response_text.strip()
            if "```json" in text:
                text = text.split("```json")[1].split("```")[0].strip()
            elif "```" in text:
                text = text.split("```")[1].split("```")[0].strip()
            
            data = json.loads(text)
            
            tasks = []
            for task_data in data:
                task_def = TaskDefinition(
                    title=task_data["title"],
                    task_type=TaskType(task_data["task_type"]),
                    description=task_data["description"],
                    execution_type=ExecutionType(task_data["execution_type"]),
                    depends_on=task_data.get("depends_on", []),
                    estimated_time=task_data.get("estimated_time", 0),
                    requires_platform_interaction=task_data.get(
                        "requires_platform_interaction", False
                    ),
                    platform=task_data.get("platform", signal.source),
                    platform_action=task_data.get("platform_action", ""),
                )
                tasks.append(task_def)
            
            return tasks
            
        except json.JSONDecodeError as e:
            self.logger.error(f"Failed to parse task decomposition: {e}")
            # Return a simple fallback
            return [
                TaskDefinition(
                    title=f"Complete: {signal.title}",
                    task_type=TaskType.CODING,
                    description=signal.description or "Complete the project",
                    execution_type=ExecutionType.MANUAL,
                )
            ]
        except Exception as e:
            self.logger.error(f"Error parsing tasks: {e}")
            return []
    
    async def _decompose_signal(
        self,
        signal: Signal,
        evaluation: EvaluationResult
    ) -> List[TaskDefinition]:
        """Use AI to decompose signal into tasks"""
        prompt = self._build_decomposition_prompt(signal, evaluation)
        
        response = await self.gateway.complete(
            prompt=prompt,
            model_tier="sonnet",  # Use sonnet for decomposition
            system="You are a project management expert. Respond only with valid JSON.",
            temperature=0.3,
            max_tokens=2048,
            task_id=str(signal.id),
            priority="normal",
        )
        
        return self._parse_tasks(response.content, signal)
    
    async def _apply_compliance(
        self,
        task_def: TaskDefinition
    ) -> TaskDefinition:
        """Apply compliance rules to task"""
        # Check with compliance gateway
        result = self.compliance.check_task(task_def)
        
        # Override execution type if needed
        if result.requires_human:
            task_def.execution_type = ExecutionType.MANUAL
        elif result.execution_type:
            task_def.execution_type = ExecutionType(result.execution_type)
        
        return task_def
    
    async def dispatch(
        self,
        signal: Signal,
        evaluation: EvaluationResult
    ) -> List[Task]:
        """
        Main dispatch method
        
        1. Decompose into tasks
        2. Apply compliance rules
        3. Create task records
        4. Enqueue for execution
        
        Returns:
            List of created Task objects
        """
        self.logger.info(f"Dispatching signal {signal.id}: {signal.title[:50]}...")
        
        # Step 1: Decompose
        task_defs = await self._decompose_signal(signal, evaluation)
        
        if not task_defs:
            self.logger.error(f"Failed to decompose signal {signal.id}")
            return []
        
        self.logger.info(f"Signal {signal.id} decomposed into {len(task_defs)} tasks")
        
        # Step 2: Apply compliance
        task_defs = [await self._apply_compliance(td) for td in task_defs]
        
        # Step 3: Create tasks in database
        tasks = await self._create_tasks(signal, task_defs)
        
        # Step 4: Enqueue
        await self._enqueue_tasks(tasks)
        
        # Update signal status
        await self._update_signal_status(signal)
        
        return tasks
    
    async def _create_tasks(
        self,
        signal: Signal,
        task_defs: List[TaskDefinition]
    ) -> List[Task]:
        """Create task records in database"""
        tasks = []
        
        async with async_session_maker() as session:
            # Create a mapping from temporary index to task ID
            task_id_map = {}
            
            for i, task_def in enumerate(task_defs):
                task = Task(
                    signal_id=signal.id,
                    title=task_def.title,
                    task_type=task_def.task_type.value,
                    execution_type=task_def.execution_type.value,
                    status=TaskStatus.PENDING,
                    priority=Priority.NORMAL,
                    input_data={
                        "description": task_def.description,
                        "platform": task_def.platform,
                        "platform_action": task_def.platform_action,
                    },
                    estimated_cost=None,
                )
                
                session.add(task)
                await session.flush()  # Get ID
                
                task_id_map[i] = str(task.id)
                tasks.append(task)
            
            # Update dependencies using actual IDs
            for i, task in enumerate(tasks):
                task_def = task_defs[i]
                if task_def.depends_on:
                    # Convert temporary indices to actual IDs
                    deps = []
                    for d in task_def.depends_on:
                        try:
                            idx = int(d)
                            if idx in task_id_map:
                                deps.append(task_id_map[idx])
                        except (ValueError, TypeError):
                            pass  # Ignore non-integer dependencies
                    task.depends_on = deps
            
            await session.commit()
            
            # Refresh to get IDs
            for task in tasks:
                await session.refresh(task)
        
        return tasks
    
    async def _enqueue_tasks(self, tasks: List[Task]):
        """Enqueue tasks for execution"""
        # Separate tasks by execution type
        auto_tasks = [t for t in tasks if t.execution_type == ExecutionType.AUTO.value]
        semi_tasks = [t for t in tasks if t.execution_type == ExecutionType.SEMI.value]
        manual_tasks = [t for t in tasks if t.execution_type == ExecutionType.MANUAL.value]
        
        # Enqueue auto tasks
        for task in auto_tasks:
            if not task.depends_on:
                await queue_manager.enqueue_task(task.to_dict())
                self.logger.debug(f"Auto task {task.id} enqueued")
        
        # Semi tasks: AI executes first, then human confirms
        for task in semi_tasks:
            # TODO: Phase 2 - AI generates materials, then creates human task for confirmation
            # For now, treat as auto + notification
            if not task.depends_on:
                await queue_manager.enqueue_task(task.to_dict())
                self.logger.debug(f"Semi task {task.id} enqueued for AI execution")
        
        # Create human tasks for manual tasks
        for task in manual_tasks:
            await self.compliance.create_human_task(task)
            self.logger.debug(f"Human task {task.id} created")
    
    async def _update_signal_status(self, signal: Signal):
        """Update signal to accepted status"""
        async with async_session_maker() as session:
            db_signal = await session.get(Signal, signal.id)
            if db_signal:
                db_signal.status = SignalStatus.ACCEPTED
                await session.commit()
    
    async def process_evaluated_signal(self, signal_data: dict):
        """Process a single evaluated signal from queue"""
        signal = Signal.from_dict(signal_data)
        
        # Reconstruct evaluation result from signal metadata
        eval_meta = signal.metadata.get("evaluation", {})
        scores = eval_meta.get("scores", {})
        
        from orchestrator.evaluator import EvaluationScores, EvaluationResult
        
        evaluation = EvaluationResult(
            signal_id=str(signal.id),
            scores=EvaluationScores(
                revenue_potential=scores.get("revenue_potential", 0),
                execution_difficulty=scores.get("execution_difficulty", 0),
                time_cost=scores.get("time_cost", 0),
                success_probability=scores.get("success_probability", 0),
                strategic_value=scores.get("strategic_value", 0),
                compliance_risk=scores.get("compliance_risk", 0),
            ),
            total_score=eval_meta.get("total_score", 50),
            decision=eval_meta.get("decision", "pending"),
            reasoning=eval_meta.get("reasoning", ""),
            estimated_ai_cost=eval_meta.get("estimated_ai_cost", 0),
            suggested_price=eval_meta.get("suggested_price", 0),
            risk_factors=eval_meta.get("risk_factors", []),
            recommended_skills=eval_meta.get("recommended_skills", []),
            execution_plan_summary=eval_meta.get("execution_plan_summary", ""),
        )
        
        # Only dispatch accepted signals
        if evaluation.decision == "accepted":
            await self.dispatch(signal, evaluation)
        else:
            self.logger.info(f"Signal {signal.id} not accepted, skipping dispatch")
    
    async def run(self):
        """Main loop: continuously consume evaluated signals"""
        self.logger.info("TaskDispatcher started")
        
        await queue_manager.connect()
        
        try:
            while True:
                signal_data = await queue_manager.dequeue(
                    queue_manager.QUEUE_SIGNALS_EVALUATED,
                    timeout=5
                )
                
                if signal_data:
                    try:
                        await self.process_evaluated_signal(signal_data)
                    except Exception as e:
                        self.logger.error(f"Failed to dispatch signal: {e}")
                        
        except asyncio.CancelledError:
            self.logger.info("TaskDispatcher stopped")
            raise
        except Exception as e:
            self.logger.error(f"Dispatcher error: {e}")
            raise
        finally:
            await queue_manager.disconnect()


# Global dispatcher instance
dispatcher = TaskDispatcher()
