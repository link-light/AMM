"""
Opportunity Evaluator - Business opportunity assessment engine

Evaluates signals from scouts using Opus model to determine:
- Revenue potential
- Execution difficulty
- Time cost
- Success probability
- Strategic value
- Compliance risk

Decision rules:
- score >= 70: accepted (进入执行队列)
- 50 <= score < 70: pending (人工决策)
- score < 50: rejected (丢弃但记录)
- compliance_risk == "high": 强制人工审核
"""

import asyncio
import json
import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.config import settings
from core.database import async_session_maker
from core.models import Signal, SignalStatus
from core.queue import queue_manager
from gateway.gateway import AIGateway

logger = logging.getLogger(__name__)


@dataclass
class EvaluationScores:
    """Individual dimension scores (0-100)"""
    revenue_potential: int = 0      # 25% weight
    execution_difficulty: int = 0   # 20% weight
    time_cost: int = 0              # 15% weight
    success_probability: int = 0    # 15% weight
    strategic_value: int = 0        # 10% weight
    compliance_risk: int = 0        # 15% weight
    
    def calculate_total(self) -> float:
        """Calculate weighted total score"""
        weights = {
            "revenue_potential": 0.25,
            "execution_difficulty": 0.20,
            "time_cost": 0.15,
            "success_probability": 0.15,
            "strategic_value": 0.10,
            "compliance_risk": 0.15,
        }
        
        total = (
            self.revenue_potential * weights["revenue_potential"] +
            (100 - self.execution_difficulty) * weights["execution_difficulty"] +  # Lower difficulty = higher score
            self.time_cost * weights["time_cost"] +
            self.success_probability * weights["success_probability"] +
            self.strategic_value * weights["strategic_value"] +
            self.compliance_risk * weights["compliance_risk"]
        )
        
        return round(total, 2)


@dataclass
class EvaluationResult:
    """Complete evaluation result"""
    signal_id: str
    scores: EvaluationScores
    total_score: float
    decision: str  # accepted / pending / rejected
    reasoning: str
    estimated_ai_cost: float
    suggested_price: float
    risk_factors: list = field(default_factory=list)
    compliance_override: bool = False
    recommended_skills: list = field(default_factory=list)
    execution_plan_summary: str = ""
    evaluated_at: datetime = field(default_factory=datetime.utcnow)


class OpportunityEvaluator:
    """
    Evaluates business opportunities using AI
    
    Consumes queue:signals:raw
    Produces: evaluated signals in DB + queue:signals:evaluated
    """
    
    # Score weights for total calculation
    WEIGHTS = {
        "revenue_potential": 0.25,
        "execution_difficulty": 0.20,
        "time_cost": 0.15,
        "success_probability": 0.15,
        "strategic_value": 0.10,
        "compliance_risk": 0.15,
    }
    
    # Decision thresholds
    THRESHOLD_ACCEPT = 70
    THRESHOLD_PENDING = 50
    
    def __init__(self, gateway: AIGateway = None):
        self.gateway = gateway or AIGateway()
        self.logger = logging.getLogger(self.__class__.__name__)
    
    def _build_evaluation_prompt(
        self,
        signal: Signal,
        historical_stats: dict = None
    ) -> str:
        """
        Build the evaluation prompt for Opus
        
        This is the core prompt that determines evaluation quality.
        """
        historical_context = ""
        if historical_stats:
            historical_context = f"""
## Historical Data for Similar Opportunities

- Total similar opportunities: {historical_stats.get('total_count', 0)}
- Success rate: {historical_stats.get('success_rate', 0) * 100:.1f}%
- Average revenue: ${historical_stats.get('avg_revenue', 0):.2f}
- Average AI cost: ${historical_stats.get('avg_ai_cost', 0):.2f}
- Average time: {historical_stats.get('avg_time_hours', 0):.1f} hours
"""
        
        prompt = f"""You are an expert business opportunity evaluator for an AI-driven freelancing system.

Your task is to evaluate the following opportunity across multiple dimensions and provide a structured assessment.

## Opportunity Details

**Source Platform**: {signal.source}
**Scout Type**: {signal.scout_type}
**Title**: {signal.title}
**Description**:
{signal.description or "No description provided"}

**Estimated Budget/Revenue**: ${signal.estimated_revenue or "Unknown"}
**Estimated Effort (hours)**: {signal.estimated_effort_hours or "Unknown"}
**Urgency**: {signal.urgency or "medium"}
**Required Skills**: {', '.join(signal.required_skills) if signal.required_skills else "Not specified"}
**Source URL**: {signal.raw_url or "N/A"}

{historical_context}

## Evaluation Dimensions

Please evaluate on a scale of 0-100 for each dimension:

1. **revenue_potential** (25% weight): 
   - Is the budget/revenue attractive?
   - Consider: absolute amount, hourly rate, payment reliability of platform
   - 0 = Very low/unattractive, 100 = Excellent revenue potential

2. **execution_difficulty** (20% weight, inverted):
   - How difficult is this to execute successfully?
   - Consider: technical complexity, clarity of requirements, required skills availability
   - 0 = Extremely difficult/risky, 100 = Very easy/low risk (we invert this, so higher = easier)

3. **time_cost** (15% weight):
   - Is the time estimate reasonable and profitable?
   - Consider: estimated hours vs revenue, deadline pressure
   - 0 = Poor time investment, 100 = Excellent time ROI

4. **success_probability** (15% weight):
   - How likely are we to complete this successfully?
   - Consider: historical data, complexity, client communication risk
   - 0 = Very unlikely, 100 = Almost certain

5. **strategic_value** (10% weight):
   - Does this help build repeatable skills/capabilities?
   - Consider: reusability of solution, learning value, portfolio building
   - 0 = One-off with no strategic value, 100 = High strategic value

6. **compliance_risk** (15% weight):
   - How risky is this from a compliance/TOS perspective?
   - Consider: platform rules, IP concerns, client legitimacy
   - 0 = High risk (avoid), 100 = Very safe

## Decision Guidelines

- **accepted** (score >= 70): Good opportunity, proceed to execution
- **pending** (50 <= score < 70): Borderline, needs human review
- **rejected** (score < 50): Not worth pursuing

**IMPORTANT**: If compliance_risk < 50 (high risk), ALWAYS set decision to "pending" regardless of total score.

## Output Format

Respond with ONLY a JSON object in this exact format:

{{
  "scores": {{
    "revenue_potential": 75,
    "execution_difficulty": 60,
    "time_cost": 80,
    "success_probability": 70,
    "strategic_value": 65,
    "compliance_risk": 90
  }},
  "reasoning": "Detailed explanation of your evaluation...",
  "estimated_ai_cost": 0.15,
  "suggested_price": 650,
  "risk_factors": ["Factor 1", "Factor 2"],
  "recommended_skills": ["python", "fastapi"],
  "execution_plan_summary": "Brief plan for execution..."
}}

Be objective and data-driven in your evaluation."""
        
        return prompt
    
    async def _get_historical_stats(self, signal: Signal) -> Optional[dict]:
        """Get historical stats for similar signals"""
        try:
            # Import here to avoid circular dependency
            from knowledge.knowledge_base import KnowledgeBase
            kb = KnowledgeBase()
            return await kb.get_category_stats(f"{signal.source}:{signal.scout_type}")
        except Exception as e:
            self.logger.warning(f"Failed to get historical stats: {e}")
            return None
    
    def _parse_evaluation_response(self, response_text: str, signal_id: str) -> EvaluationResult:
        """Parse the AI response into EvaluationResult"""
        try:
            # Extract JSON from response (handle markdown code blocks)
            text = response_text.strip()
            if "```json" in text:
                text = text.split("```json")[1].split("```")[0].strip()
            elif "```" in text:
                text = text.split("```")[1].split("```")[0].strip()
            
            data = json.loads(text)
            
            scores = EvaluationScores(
                revenue_potential=data["scores"]["revenue_potential"],
                execution_difficulty=data["scores"]["execution_difficulty"],
                time_cost=data["scores"]["time_cost"],
                success_probability=data["scores"]["success_probability"],
                strategic_value=data["scores"]["strategic_value"],
                compliance_risk=data["scores"]["compliance_risk"],
            )
            
            total_score = scores.calculate_total()
            
            # Determine decision
            compliance_override = scores.compliance_risk < 50
            
            if compliance_override:
                decision = "pending"
            elif total_score >= self.THRESHOLD_ACCEPT:
                decision = "accepted"
            elif total_score >= self.THRESHOLD_PENDING:
                decision = "pending"
            else:
                decision = "rejected"
            
            return EvaluationResult(
                signal_id=signal_id,
                scores=scores,
                total_score=total_score,
                decision=decision,
                reasoning=data.get("reasoning", ""),
                estimated_ai_cost=data.get("estimated_ai_cost", 0.1),
                suggested_price=data.get("suggested_price", 0),
                risk_factors=data.get("risk_factors", []),
                compliance_override=compliance_override,
                recommended_skills=data.get("recommended_skills", []),
                execution_plan_summary=data.get("execution_plan_summary", ""),
            )
            
        except json.JSONDecodeError as e:
            self.logger.error(f"Failed to parse evaluation response: {e}")
            # Return a safe default
            return EvaluationResult(
                signal_id=signal_id,
                scores=EvaluationScores(),
                total_score=0,
                decision="pending",
                reasoning=f"Failed to parse response: {e}",
                estimated_ai_cost=0,
                suggested_price=0,
            )
        except Exception as e:
            self.logger.error(f"Unexpected error parsing response: {e}")
            return EvaluationResult(
                signal_id=signal_id,
                scores=EvaluationScores(),
                total_score=0,
                decision="pending",
                reasoning=f"Error: {e}",
                estimated_ai_cost=0,
                suggested_price=0,
            )
    
    async def evaluate(self, signal: Signal) -> EvaluationResult:
        """
        Evaluate a single opportunity signal
        
        Args:
            signal: The Signal to evaluate
            
        Returns:
            EvaluationResult with scores and decision
        """
        self.logger.info(f"Evaluating signal {signal.id}: {signal.title[:50]}...")
        
        # Get historical context
        historical_stats = await self._get_historical_stats(signal)
        
        # Build and send evaluation prompt
        prompt = self._build_evaluation_prompt(signal, historical_stats)
        
        try:
            response = await self.gateway.complete(
                prompt=prompt,
                model_tier="opus",  # Use best model for evaluation
                system="You are an expert business opportunity evaluator. Respond only with valid JSON.",
                temperature=0.3,
                max_tokens=2048,
                task_id=str(signal.id),
                priority="normal",
                cacheable=True,  # Cache similar evaluations
            )
            
            # Parse response
            result = self._parse_evaluation_response(response.content, str(signal.id))
            
            self.logger.info(
                f"Signal {signal.id} evaluated: score={result.total_score}, "
                f"decision={result.decision}"
            )
            
            return result
            
        except Exception as e:
            self.logger.error(f"Evaluation failed for signal {signal.id}: {e}")
            # Return pending on error (safe default)
            return EvaluationResult(
                signal_id=str(signal.id),
                scores=EvaluationScores(),
                total_score=0,
                decision="pending",
                reasoning=f"Evaluation failed: {e}",
                estimated_ai_cost=0,
                suggested_price=signal.estimated_revenue or 0,
            )
    
    async def _update_signal(
        self,
        session: AsyncSession,
        signal: Signal,
        result: EvaluationResult
    ):
        """Update signal record with evaluation results"""
        signal.score = result.total_score
        signal.status = SignalStatus.EVALUATED
        signal.meta_data = {
            **(signal.meta_data or {}),
            "evaluation": {
                "scores": {
                    "revenue_potential": result.scores.revenue_potential,
                    "execution_difficulty": result.scores.execution_difficulty,
                    "time_cost": result.scores.time_cost,
                    "success_probability": result.scores.success_probability,
                    "strategic_value": result.scores.strategic_value,
                    "compliance_risk": result.scores.compliance_risk,
                },
                "decision": result.decision,
                "reasoning": result.reasoning,
                "estimated_ai_cost": result.estimated_ai_cost,
                "suggested_price": result.suggested_price,
                "risk_factors": result.risk_factors,
                "compliance_override": result.compliance_override,
                "recommended_skills": result.recommended_skills,
                "execution_plan_summary": result.execution_plan_summary,
                "evaluated_at": result.evaluated_at.isoformat(),
            }
        }
        
        if result.compliance_override:
            signal.compliance_flags = list(set([
                *(signal.compliance_flags or []),
                "high_risk_requires_review"
            ]))
        
        await session.commit()
    
    async def _enqueue_for_dispatch(self, signal: Signal, result: EvaluationResult):
        """Enqueue evaluated signal for dispatch"""
        if result.decision == "accepted":
            await queue_manager.enqueue_signal_evaluated(signal.to_dict())
            self.logger.info(f"Signal {signal.id} queued for dispatch")
    
    async def process_signal(self, signal_data: dict):
        """
        Process a single signal from queue
        
        Args:
            signal_data: Raw signal data from queue
        """
        signal = Signal.from_dict(signal_data)
        
        async with async_session_maker() as session:
            # Get signal from DB
            db_signal = await session.get(Signal, signal.id)
            if not db_signal:
                self.logger.error(f"Signal {signal.id} not found in database")
                return
            
            # Evaluate
            result = await self.evaluate(db_signal)
            
            # Update signal
            await self._update_signal(session, db_signal, result)
            
            # Enqueue if accepted
            await self._enqueue_for_dispatch(db_signal, result)
    
    async def run(self):
        """
        Main loop: continuously consume and evaluate signals
        
        Runs indefinitely until interrupted.
        """
        self.logger.info("OpportunityEvaluator started")
        
        await queue_manager.connect()
        
        try:
            while True:
                # Consume from raw signals queue
                signal_data = await queue_manager.dequeue(
                    queue_manager.QUEUE_SIGNALS_RAW,
                    timeout=5
                )
                
                if signal_data:
                    try:
                        await self.process_signal(signal_data)
                    except Exception as e:
                        self.logger.error(f"Failed to process signal: {e}")
                
        except asyncio.CancelledError:
            self.logger.info("OpportunityEvaluator stopped")
            raise
        except Exception as e:
            self.logger.error(f"Evaluator error: {e}")
            raise
        finally:
            await queue_manager.disconnect()


# Global evaluator instance
evaluator = OpportunityEvaluator()
