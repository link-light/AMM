"""
Audit Logger - Record all AI calls for compliance and debugging
"""

import json
import logging
from datetime import datetime
from typing import Optional

import redis.asyncio as redis

from core.config import settings
from core.database import async_session_maker
from core.models import AuditLog

logger = logging.getLogger(__name__)


class AuditLogger:
    """
    Audit logger for AI Gateway
    
    Records:
    - Timestamp, task_id, model_tier, provider
    - Input/output tokens, cost
    - Latency
    - Success/error status
    - Prompt summary (first 100 chars)
    
    Dual write:
    - PostgreSQL for persistence
    - JSON file for easy inspection
    """
    
    def __init__(self, redis_client: redis.Redis = None):
        self.redis = redis_client
    
    def _get_redis(self) -> redis.Redis:
        """Get Redis connection"""
        if self.redis is None:
            from core.queue import queue_manager
            return queue_manager.redis
        return self.redis
    
    def _summarize_prompt(self, prompt: str, max_length: int = 100) -> str:
        """Create a summary of the prompt (not full text for privacy)"""
        if len(prompt) <= max_length:
            return prompt
        return prompt[:max_length] + "..."
    
    async def log_ai_call(
        self,
        task_id: Optional[str],
        model_tier: str,
        provider: str,
        model: str,
        prompt: str,
        input_tokens: int,
        output_tokens: int,
        cost: float,
        latency_ms: int,
        success: bool,
        error: Optional[str] = None,
        cached: bool = False,
    ):
        """
        Log an AI call
        
        Args:
            task_id: Associated task ID
            model_tier: Model tier (opus/sonnet/haiku)
            provider: Provider name
            model: Actual model name
            prompt: The prompt (will be summarized)
            input_tokens: Input token count
            output_tokens: Output token count
            cost: Cost in USD
            latency_ms: Latency in milliseconds
            success: Whether call succeeded
            error: Error message if failed
            cached: Whether response was cached
        """
        if not settings.app.enable_audit_log:
            return
        
        timestamp = datetime.utcnow().isoformat()
        
        log_entry = {
            "timestamp": timestamp,
            "task_id": task_id,
            "model_tier": model_tier,
            "provider": provider,
            "model": model,
            "prompt_summary": self._summarize_prompt(prompt),
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "cost": cost,
            "latency_ms": latency_ms,
            "success": success,
            "error": error,
            "cached": cached,
        }
        
        # Write to PostgreSQL
        try:
            async with async_session_maker() as session:
                audit_log = AuditLog(
                    event_type="ai_call",
                    actor="system",
                    details=log_entry,
                )
                session.add(audit_log)
                await session.commit()
        except Exception as e:
            logger.error(f"Failed to write audit log to database: {e}")
        
        # Write to JSON file
        try:
            with open("logs/audit.log", "a", encoding="utf-8") as f:
                f.write(json.dumps(log_entry, default=str) + "\n")
        except Exception as e:
            logger.error(f"Failed to write audit log to file: {e}")
        
        logger.debug(f"Audit log: {provider}/{model_tier} - {'success' if success else 'failed'}")
    
    async def log_evaluation(
        self,
        signal_id: str,
        score: float,
        decision: str,
        reasoning: str,
        estimated_cost: float,
    ):
        """Log an opportunity evaluation"""
        await self._log_event(
            event_type="evaluation",
            actor="opportunity_evaluator",
            details={
                "signal_id": signal_id,
                "score": score,
                "decision": decision,
                "reasoning": reasoning,
                "estimated_cost": estimated_cost,
            }
        )
    
    async def log_review(
        self,
        task_id: str,
        review_type: str,
        passed: bool,
        score: float,
        reviewer: str,
    ):
        """Log a quality review"""
        await self._log_event(
            event_type="review",
            actor=reviewer,
            details={
                "task_id": task_id,
                "review_type": review_type,
                "passed": passed,
                "score": score,
            }
        )
    
    async def log_config_change(
        self,
        setting: str,
        old_value: any,
        new_value: any,
        changed_by: str = "system",
    ):
        """Log a configuration change"""
        await self._log_event(
            event_type="config_change",
            actor=changed_by,
            details={
                "setting": setting,
                "old_value": old_value,
                "new_value": new_value,
            }
        )
    
    async def _log_event(self, event_type: str, actor: str, details: dict):
        """Generic event logging"""
        if not settings.app.enable_audit_log:
            return
        
        timestamp = datetime.utcnow().isoformat()
        
        log_entry = {
            "timestamp": timestamp,
            "event_type": event_type,
            "actor": actor,
            "details": details,
        }
        
        # Write to PostgreSQL
        try:
            async with async_session_maker() as session:
                audit_log = AuditLog(
                    event_type=event_type,
                    actor=actor,
                    details=details,
                )
                session.add(audit_log)
                await session.commit()
        except Exception as e:
            logger.error(f"Failed to write audit log: {e}")
        
        # Write to JSON file
        try:
            import os
            os.makedirs("logs", exist_ok=True)
            with open("logs/audit.log", "a", encoding="utf-8") as f:
                f.write(json.dumps(log_entry, default=str) + "\n")
        except Exception as e:
            logger.error(f"Failed to write audit log to file: {e}")
