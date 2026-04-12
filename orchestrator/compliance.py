"""
Compliance Gateway - Intercepts and classifies platform interactions

Operation Levels:
- L0 (安全): 纯内部处理 → auto
- L1 (低风险): 信息查询 → auto + 日志
- L2 (中风险): 账户读操作 → auto + 人工确认
- L3 (高风险): 账户写操作 → 强制 manual
- L4 (关键): 财务操作 → 强制 manual + 二次确认
"""

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import Enum
from typing import Optional

from core.config import settings
from core.database import async_session_maker
from core.models import HumanTask, HumanTaskStatus, Task
from core.queue import queue_manager

logger = logging.getLogger(__name__)


class ComplianceLevel(Enum):
    """Compliance risk levels"""
    L0_SAFE = "L0"        # Internal only
    L1_LOW = "L1"         # Info query
    L2_MEDIUM = "L2"      # Account read
    L3_HIGH = "L3"        # Account write
    L4_CRITICAL = "L4"    # Financial


# Platform rules configuration
PLATFORM_RULES = {
    "upwork": {
        "submit_proposal": ComplianceLevel.L3_HIGH,
        "send_message": ComplianceLevel.L3_HIGH,
        "deliver_work": ComplianceLevel.L3_HIGH,
        "view_job": ComplianceLevel.L1_LOW,
        "withdraw_funds": ComplianceLevel.L4_CRITICAL,
        "accept_offer": ComplianceLevel.L3_HIGH,
        "create_contract": ComplianceLevel.L3_HIGH,
    },
    "fiverr": {
        "create_gig": ComplianceLevel.L3_HIGH,
        "respond_buyer": ComplianceLevel.L3_HIGH,
        "deliver_order": ComplianceLevel.L3_HIGH,
        "view_orders": ComplianceLevel.L1_LOW,
        "withdraw_earnings": ComplianceLevel.L4_CRITICAL,
    },
    "github": {
        "create_pr": ComplianceLevel.L2_MEDIUM,
        "comment_issue": ComplianceLevel.L2_MEDIUM,
        "push_code": ComplianceLevel.L2_MEDIUM,
        "view_issues": ComplianceLevel.L0_SAFE,
        "fork_repo": ComplianceLevel.L2_MEDIUM,
        "create_issue": ComplianceLevel.L2_MEDIUM,
    },
    "twitter": {
        "post_tweet": ComplianceLevel.L2_MEDIUM,
        "reply_tweet": ComplianceLevel.L2_MEDIUM,
        "dm_user": ComplianceLevel.L2_MEDIUM,
        "read_timeline": ComplianceLevel.L0_SAFE,
    },
    "linkedin": {
        "send_connection": ComplianceLevel.L2_MEDIUM,
        "send_message": ComplianceLevel.L2_MEDIUM,
        "post_update": ComplianceLevel.L2_MEDIUM,
        "view_profile": ComplianceLevel.L1_LOW,
    },
}

# Execution type mapping
LEVEL_EXECUTION_MAP = {
    ComplianceLevel.L0_SAFE: ("auto", False),
    ComplianceLevel.L1_LOW: ("auto", False),
    ComplianceLevel.L2_MEDIUM: ("semi", False),
    ComplianceLevel.L3_HIGH: ("manual", True),
    ComplianceLevel.L4_CRITICAL: ("manual", True),
}


@dataclass
class ComplianceCheckResult:
    """Result of compliance check"""
    level: ComplianceLevel
    execution_type: str  # auto / semi / manual
    requires_human: bool
    compliance_notes: str
    requires_second_confirmation: bool = False


class ComplianceGateway:
    """
    Compliance Gateway for platform interactions
    
    Intercepts all platform operations and enforces compliance rules.
    """
    
    def __init__(self):
        self.logger = logging.getLogger(self.__class__.__name__)
        self.rules = PLATFORM_RULES
    
    def classify_operation(
        self,
        task_type: str,
        platform: str,
        action: str
    ) -> ComplianceLevel:
        """
        Classify an operation by compliance level
        
        Args:
            task_type: Type of task
            platform: Platform name
            action: Specific action
            
        Returns:
            ComplianceLevel
        """
        platform = platform.lower()
        action = action.lower()
        
        # Check platform-specific rules
        if platform in self.rules:
            platform_rules = self.rules[platform]
            if action in platform_rules:
                return platform_rules[action]
        
        # Default classification based on action keywords
        high_risk_keywords = [
            "pay", "payment", "withdraw", "transfer", "purchase",
            "submit", "send", "deliver", "accept", "approve",
            "commit", "push", "merge", "deploy"
        ]
        
        medium_risk_keywords = [
            "create", "update", "delete", "modify", "change",
            "post", "reply", "comment", "message", "contact"
        ]
        
        low_risk_keywords = [
            "view", "read", "get", "fetch", "list", "search",
            "analyze", "monitor"
        ]
        
        action_lower = action.lower()
        
        for keyword in high_risk_keywords:
            if keyword in action_lower:
                return ComplianceLevel.L3_HIGH
        
        for keyword in medium_risk_keywords:
            if keyword in action_lower:
                return ComplianceLevel.L2_MEDIUM
        
        for keyword in low_risk_keywords:
            if keyword in action_lower:
                return ComplianceLevel.L1_LOW
        
        # Default to medium risk for unknown actions
        return ComplianceLevel.L2_MEDIUM
    
    def check_task(self, task_def) -> ComplianceCheckResult:
        """
        Check a task for compliance requirements
        
        Args:
            task_def: TaskDefinition or similar with platform/platform_action
            
        Returns:
            ComplianceCheckResult
        """
        platform = getattr(task_def, 'platform', '') or 'unknown'
        action = getattr(task_def, 'platform_action', '') or 'unknown'
        requires_platform = getattr(task_def, 'requires_platform_interaction', False)
        
        # If no platform interaction, it's safe
        if not requires_platform and not platform:
            return ComplianceCheckResult(
                level=ComplianceLevel.L0_SAFE,
                execution_type="auto",
                requires_human=False,
                compliance_notes="No platform interaction required",
            )
        
        # Classify the operation
        level = self.classify_operation(
            getattr(task_def, 'task_type', 'unknown'),
            platform,
            action
        )
        
        # Get execution requirements
        exec_type, requires_human = LEVEL_EXECUTION_MAP.get(
            level, ("manual", True)
        )
        
        # Build notes
        notes = f"Platform: {platform}, Action: {action}, Level: {level.value}"
        
        # Check for second confirmation requirement (L4)
        requires_second = level == ComplianceLevel.L4_CRITICAL
        
        return ComplianceCheckResult(
            level=level,
            execution_type=exec_type,
            requires_human=requires_human,
            compliance_notes=notes,
            requires_second_confirmation=requires_second,
        )
    
    async def create_human_task(
        self,
        task: Task,
        materials: dict = None
    ) -> HumanTask:
        """
        Create a human task for manual execution
        
        Args:
            task: The task requiring human intervention
            materials: Prepared materials for the human
            
        Returns:
            Created HumanTask
        """
        platform = task.input_data.get("platform", "unknown")
        action = task.input_data.get("platform_action", "unknown")
        
        # Generate instructions based on action
        instructions = self._generate_instructions(task, action)
        
        human_task = HumanTask(
            task_id=task.id,
            task_type=action,
            platform=platform,
            priority=task.priority,
            status=HumanTaskStatus.PENDING,
            prepared_materials=materials or {},
            instructions=instructions,
            target_url=task.input_data.get("target_url"),
            deadline=datetime.utcnow() + timedelta(days=2),  # Default 2 days
        )
        
        async with async_session_maker() as session:
            session.add(human_task)
            await session.commit()
            await session.refresh(human_task)
        
        # Enqueue for human workers
        await queue_manager.enqueue_human_task(human_task.to_dict())
        
        self.logger.info(
            f"Human task {human_task.id} created for task {task.id} "
            f"({platform}/{action})"
        )
        
        return human_task
    
    def _generate_instructions(self, task: Task, action: str) -> str:
        """Generate human-readable instructions for a task"""
        platform = task.input_data.get("platform", "unknown")
        description = task.input_data.get("description", "")
        
        instructions = f"""# Human Task: {action}

## Task
{task.title}

## Description
{description}

## Platform
{platform}

## Action Required
"""
        
        # Add specific instructions based on action
        if "proposal" in action.lower():
            instructions += """
1. Review the project requirements carefully
2. Customize the prepared proposal materials
3. Submit the proposal on the platform
4. Copy the proposal URL or ID back to this system
"""
        elif "message" in action.lower():
            instructions += """
1. Review the conversation context
2. Use the prepared response or customize as needed
3. Send the message on the platform
4. Note any important responses
"""
        elif "deliver" in action.lower():
            instructions += """
1. Review the deliverables checklist
2. Upload all required files to the platform
3. Add any necessary documentation
4. Mark the delivery as complete
5. Copy the delivery confirmation URL
"""
        elif "withdraw" in action.lower():
            instructions += """
⚠️ CRITICAL FINANCIAL OPERATION ⚠️

1. Verify the withdrawal amount and destination
2. Confirm all details are correct
3. Complete the withdrawal on the platform
4. Save the transaction confirmation
5. This action requires secondary confirmation
"""
        else:
            instructions += """
1. Review the task details carefully
2. Perform the required action on the platform
3. Document the result
4. Return to this system to complete the task
"""
        
        instructions += """
## Important Notes

- Always follow platform Terms of Service
- Do not share sensitive credentials
- Document any issues or questions
- Respond promptly to maintain good standing
"""
        
        return instructions
    
    async def complete_human_task(
        self,
        human_task_id: str,
        completed_by: str,
        notes: str = "",
        result_url: str = ""
    ):
        """
        Mark a human task as completed
        
        Args:
            human_task_id: ID of the human task
            completed_by: Who completed the task
            notes: Completion notes
            result_url: URL to the result (if applicable)
        """
        async with async_session_maker() as session:
            human_task = await session.get(HumanTask, human_task_id)
            if not human_task:
                self.logger.error(f"Human task {human_task_id} not found")
                return
            
            human_task.status = HumanTaskStatus.COMPLETED
            human_task.completed_by = completed_by
            human_task.completion_notes = notes
            human_task.completed_at = datetime.utcnow()
            
            if result_url:
                human_task.prepared_materials = {
                    **(human_task.prepared_materials or {}),
                    "result_url": result_url,
                }
            
            await session.commit()
        
        self.logger.info(f"Human task {human_task_id} completed by {completed_by}")
    
    def add_platform_rules(self, platform: str, rules: dict):
        """
        Add or update platform-specific rules
        
        Args:
            platform: Platform name
            rules: Dict of action -> ComplianceLevel
        """
        if platform not in self.rules:
            self.rules[platform] = {}
        
        for action, level in rules.items():
            if isinstance(level, str):
                level = ComplianceLevel(level)
            self.rules[platform][action] = level
        
        self.logger.info(f"Updated rules for platform: {platform}")
    
    async def get_pending_human_tasks(
        self,
        platform: str = None,
        limit: int = 50
    ) -> list:
        """Get list of pending human tasks"""
        async with async_session_maker() as session:
            from sqlalchemy import select, case
            
            # Priority weight: high=3, normal=2, low=1 (for correct sorting)
            priority_weight = case(
                (HumanTask.priority == 'high', 3),
                (HumanTask.priority == 'normal', 2),
                (HumanTask.priority == 'low', 1),
                else_=0
            )
            
            query = select(HumanTask).where(
                HumanTask.status == HumanTaskStatus.PENDING
            ).order_by(
                priority_weight.desc(),
                HumanTask.created_at.asc()
            ).limit(limit)
            
            if platform:
                query = query.where(HumanTask.platform == platform)
            
            result = await session.execute(query)
            return result.scalars().all()


# Global compliance gateway instance
compliance_gateway = ComplianceGateway()
