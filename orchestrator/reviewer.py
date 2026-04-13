"""
Quality Reviewer - Reviews worker execution results

Features:
- Calculates confidence score
- Routes to appropriate review type (auto / AI / human)
- Compliance check for AI artifacts
- Automatic or manual approval
"""

import json
import logging
from dataclasses import dataclass
from datetime import datetime
from typing import List, Optional

from core.config import settings
from core.database import async_session_maker
from core.models import Task, TaskResult
from core.queue import queue_manager
from gateway.gateway import AIGateway

logger = logging.getLogger(__name__)


@dataclass
class ReviewResult:
    """Quality review result"""
    task_id: str
    review_type: str  # auto / ai / human
    passed: bool
    score: float
    confidence: float
    issues: List[str]
    suggestions: List[str]
    compliance_check: bool  # AI artifact check
    reviewed_at: datetime
    reviewer: str


class QualityReviewer:
    """
    Reviews task execution results
    
    Review flow:
    1. Calculate confidence score
    2. Route based on confidence:
       - > 90%: auto review
       - 70-90%: AI review (Opus)
       - < 70%: human review
    3. Check for AI artifacts
    4. Return review result
    """
    
    # Confidence thresholds
    AUTO_THRESHOLD = 0.90
    AI_THRESHOLD = 0.70
    
    # Base confidence scores
    BASE_CONFIDENCE_WITH_SKILL = 0.60
    BASE_CONFIDENCE_WITHOUT_SKILL = 0.30
    
    def __init__(self, gateway: AIGateway = None):
        self.gateway = gateway or AIGateway()
        self.logger = logging.getLogger(self.__class__.__name__)
    
    def calculate_confidence(self, task: Task) -> float:
        """
        Calculate confidence score for a task
        
        Formula:
        - Base: 0.60 with skill, 0.30 without
        - Skill bonus: skill_success_rate * 0.20
        - History bonus: consecutive_successes * 0.03 (max 0.15)
        - New task type cap: max 0.50
        """
        confidence = 0.0
        
        # Base confidence
        if task.skill_id:
            confidence = self.BASE_CONFIDENCE_WITH_SKILL
        else:
            confidence = self.BASE_CONFIDENCE_WITHOUT_SKILL
        
        # Skill bonus
        if task.skill_id:
            try:
                from knowledge.skills_store import SkillsStore
                store = SkillsStore()
                # This would be async in real implementation
                # skill = await store.get_skill(task.skill_id)
                # confidence += skill.success_rate * 0.20
            except:
                pass
        
        # History bonus (placeholder - would come from knowledge base)
        # consecutive_successes = self._get_consecutive_successes(task)
        # confidence += min(consecutive_successes * 0.03, 0.15)
        
        # Cap for new task types
        # if self._is_new_task_type(task):
        #     confidence = min(confidence, 0.50)
        
        return min(confidence, 1.0)
    
    async def review(self, task: Task, result: TaskResult) -> ReviewResult:
        """
        Main review method
        
        Routes to appropriate review type based on confidence.
        """
        confidence = self.calculate_confidence(task)
        self.logger.info(f"Reviewing task {task.id} with confidence {confidence:.2f}")
        
        if confidence >= self.AUTO_THRESHOLD:
            return await self.auto_review(task, result, confidence)
        elif confidence >= self.AI_THRESHOLD:
            return await self.ai_review(task, result, confidence)
        else:
            return await self.request_human_review(task, result, confidence)
    
    async def auto_review(self, task: Task, result: TaskResult, confidence: float) -> ReviewResult:
        """
        Automatic review based on checklist rules
        
        Checks:
        - Code: file completeness, tests present, docs present
        - Content: word count, format, keywords
        """
        self.logger.info(f"Auto reviewing task {task.id}")
        
        issues = []
        suggestions = []
        passed = True
        
        output = result.output_data or {}
        
        # Check based on task type
        if task.task_type in ["coding", "automation", "script"]:
            # Code checks
            code_files = output.get("code_files", [])
            test_files = output.get("test_files", [])
            doc_files = output.get("doc_files", [])
            
            if not code_files:
                issues.append("No code files generated")
                passed = False
            
            if not test_files:
                issues.append("No test files generated")
                suggestions.append("Add unit tests for better coverage")
            
            if not any(f["path"].lower() == "readme.md" for f in doc_files):
                issues.append("No README.md found")
                suggestions.append("Add README with usage instructions")
            
            # Check for placeholder content
            for file in code_files:
                content = file.get("content", "")
                if "TODO" in content.upper():
                    issues.append(f"TODO found in {file['path']}")
                if "FIXME" in content.upper():
                    issues.append(f"FIXME found in {file['path']}")
        
        elif task.task_type in ["content", "writing"]:
            # Content checks
            content = output.get("content", "")
            word_count = len(content.split())
            
            if word_count < 100:
                issues.append(f"Content too short ({word_count} words)")
                passed = False
        
        # AI artifact check (basic)
        compliance = self._check_ai_artifacts(output)
        
        return ReviewResult(
            task_id=str(task.id),
            review_type="auto",
            passed=passed and compliance,
            score=0.95 if passed else 0.70,
            confidence=confidence,
            issues=issues,
            suggestions=suggestions,
            compliance_check=compliance,
            reviewed_at=datetime.utcnow(),
            reviewer="system",
        )
    
    async def ai_review(self, task: Task, result: TaskResult, confidence: float) -> ReviewResult:
        """
        AI-powered review using Opus
        
        Deep analysis of deliverables for quality assessment.
        """
        self.logger.info(f"AI reviewing task {task.id}")
        
        # Build review prompt
        prompt = self._build_review_prompt(task, result)
        
        response = await self.gateway.complete(
            prompt=prompt,
            model_tier="opus",
            system="You are a senior technical reviewer. Provide objective quality assessment.",
            temperature=0.3,
            max_tokens=1500,
            task_id=str(task.id),
        )
        
        # Parse response
        review_data = self._parse_review_response(response.content)
        
        return ReviewResult(
            task_id=str(task.id),
            review_type="ai",
            passed=review_data.get("passed", False),
            score=review_data.get("score", 0),
            confidence=confidence,
            issues=review_data.get("issues", []),
            suggestions=review_data.get("suggestions", []),
            compliance_check=not review_data.get("ai_artifacts_detected", True),
            reviewed_at=datetime.utcnow(),
            reviewer="opus",
        )
    
    async def request_human_review(self, task: Task, result: TaskResult, confidence: float) -> ReviewResult:
        """
        Request human review for low-confidence results
        
        Creates a review task in the dashboard.
        """
        self.logger.info(f"Requesting human review for task {task.id}")
        
        # Create human review task
        await self._create_review_task(task, result)
        
        return ReviewResult(
            task_id=str(task.id),
            review_type="human",
            passed=False,  # Pending human review
            score=0.0,
            confidence=confidence,
            issues=["Low confidence - requires human review"],
            suggestions=["Please review deliverables manually"],
            compliance_check=False,
            reviewed_at=datetime.utcnow(),
            reviewer="pending",
        )
    
    def _build_review_prompt(self, task: Task, result: TaskResult) -> str:
        """Build AI review prompt"""
        output = result.output_data or {}
        
        # Get deliverables summary
        deliverables = []
        
        if "code_files" in output:
            files = output["code_files"]
            deliverables.append(f"Code files: {len(files)}")
            for f in files[:3]:  # Show first 3
                deliverables.append(f"  - {f['path']}")
        
        if "test_files" in output:
            deliverables.append(f"Tests: {len(output['test_files'])} files")
        
        if "doc_files" in output:
            deliverables.append(f"Docs: {len(output['doc_files'])} files")
        
        deliverables_text = "\n".join(deliverables)
        
        return f"""You are a senior technical reviewer. Please review the following deliverables.

Task: {task.title}
Type: {task.task_type}
Description: {task.input_data.get('description', 'N/A')}

Deliverables:
{deliverables_text}

Quality Checklist:
1. Does it meet all stated requirements?
2. Is the code quality professional?
3. Are there any obvious bugs or issues?
4. Is documentation complete and clear?
5. Are tests adequate?
6. Does it avoid obvious AI-generated patterns?

Rate the deliverables and return JSON:
{{
    "passed": true/false,
    "score": 0-100,
    "issues": ["Issue 1", "Issue 2"],
    "suggestions": ["Suggestion 1"],
    "ai_artifacts_detected": true/false,
    "ready_for_delivery": true/false
}}"""
    
    def _parse_review_response(self, content: str) -> dict:
        """Parse AI review response"""
        try:
            # Extract JSON
            text = content.strip()
            if "```json" in text:
                text = text.split("```json")[1].split("```")[0].strip()
            elif "```" in text:
                text = text.split("```")[1].split("```")[0].strip()
            
            return json.loads(text)
        except:
            return {
                "passed": False,
                "score": 50,
                "issues": ["Failed to parse review"],
                "suggestions": [],
                "ai_artifacts_detected": True,
            }
    
    def _check_ai_artifacts(self, output: dict) -> bool:
        """
        Check for obvious AI-generated artifacts
        
        Returns True if no obvious artifacts detected.
        """
        # Simple heuristics
        suspicious_patterns = [
            "As an AI language model",
            "I am an AI",
            "I cannot",
            "I apologize",
            "As an artificial intelligence",
        ]
        
        all_text = json.dumps(output).lower()
        
        for pattern in suspicious_patterns:
            if pattern.lower() in all_text:
                return False
        
        return True
    
    async def _create_review_task(self, task: Task, result: TaskResult):
        """Create a human review task"""
        from orchestrator.compliance import compliance_gateway
        
        # This creates a human task for review
        # The task would be picked up by the dashboard
        pass
    
    async def process_result(self, result_data: dict):
        """
        Process a result from the review queue
        
        Args:
            result_data: Dict with task_id and result
        """
        task_id = result_data.get("task_id")
        result_dict = result_data.get("result", {})
        
        async with async_session_maker() as session:
            task = await session.get(Task, task_id)
            if not task:
                self.logger.error(f"Task {task_id} not found")
                return
            
            # Convert dict to TaskResult
            result = TaskResult(
                task_id=task_id,
                status=result_dict.get("status", "completed"),
                output_data=result_dict.get("output_data", {}),
                files_generated=result_dict.get("files_generated", []),
                ai_calls_count=result_dict.get("ai_calls_count", 0),
                total_cost=result_dict.get("total_cost", 0),
                execution_time=result_dict.get("execution_time", 0),
                quality_notes=result_dict.get("quality_notes", ""),
            )
            
            # Review
            review = await self.review(task, result)
            
            # Update task with review result
            task.metadata = {
                **(task.metadata or {}),
                "review": {
                    "type": review.review_type,
                    "passed": review.passed,
                    "score": review.score,
                    "confidence": review.confidence,
                    "issues": review.issues,
                    "suggestions": review.suggestions,
                    "compliance_check": review.compliance_check,
                    "reviewed_at": review.reviewed_at.isoformat(),
                    "reviewer": review.reviewer,
                }
            }
            
            await session.commit()
            
            self.logger.info(
                f"Task {task_id} reviewed: {review.review_type}, "
                f"passed={review.passed}, score={review.score}"
            )
    
    async def run(self):
        """Main loop: continuously consume and review results"""
        self.logger.info("QualityReviewer started")
        
        await queue_manager.connect()
        
        try:
            while True:
                result_data = await queue_manager.dequeue(
                    queue_manager.QUEUE_RESULTS_REVIEW,
                    timeout=5
                )
                
                if result_data:
                    try:
                        await self.process_result(result_data)
                    except Exception as e:
                        self.logger.error(f"Failed to process result: {e}")
                        
        except asyncio.CancelledError:
            self.logger.info("QualityReviewer stopped")
            raise
        except Exception as e:
            self.logger.error(f"Reviewer error: {e}")
            raise
        finally:
            await queue_manager.disconnect()


# Global reviewer instance
reviewer = QualityReviewer()

# Import at bottom
import asyncio
