"""
Cost Tracker - Real-time AI cost tracking and budget management
"""

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Optional

import redis.asyncio as redis
from sqlalchemy import func
from sqlalchemy.future import select

from core.config import settings
from core.database import async_session_maker
from core.exceptions import BudgetExceededError
from core.models import CostRecord

logger = logging.getLogger(__name__)


@dataclass
class BudgetStatus:
    """Budget status information"""
    level: str  # normal / warning / degraded / exceeded
    daily_spent: float
    daily_limit: float
    daily_remaining: float
    monthly_spent: float
    monthly_limit: float
    monthly_remaining: float
    degraded_model_map: dict  # Model mapping when degraded


class CostTracker:
    """
    Real-time cost tracking with budget enforcement
    
    Budget levels:
    - normal: 0-75% of budget
    - warning: 75-90% of budget (alert + dashboard notification)
    - degraded: 90-100% of budget (downgrade models)
    - exceeded: 100%+ of budget (stop all calls)
    """
    
    def __init__(self, redis_client: redis.Redis = None):
        self.redis = redis_client
        self.config = settings.ai_gateway
        
        # Hard limits
        self.daily_hard_limit = self.config.daily_hard_limit
        self.monthly_hard_limit = self.config.monthly_hard_limit
        self.per_task_limit = self.config.per_task_limit
        
        # Soft limits (warning thresholds)
        self.daily_soft_limit = self.config.daily_soft_limit
        self.monthly_soft_limit = self.config.monthly_soft_limit
        
        # Budget levels
        self.WARNING_THRESHOLD = 0.75
        self.DEGRADED_THRESHOLD = 0.90
    
    def _get_daily_key(self, date: str = None) -> str:
        """Redis key for daily cost"""
        if date is None:
            date = datetime.now().strftime("%Y-%m-%d")
        return f"cost:daily:{date}"
    
    def _get_monthly_key(self, month: str = None) -> str:
        """Redis key for monthly cost"""
        if month is None:
            month = datetime.now().strftime("%Y-%m")
        return f"cost:monthly:{month}"
    
    def _get_task_key(self, task_id: str) -> str:
        """Redis key for task cost"""
        return f"cost:task:{task_id}"
    
    async def _get_redis(self) -> redis.Redis:
        """Get Redis connection"""
        if self.redis is None:
            from core.queue import queue_manager
            await queue_manager.connect()
            self.redis = queue_manager.redis
        return self.redis
    
    async def record(
        self,
        task_id: Optional[str],
        provider: str,
        model: str,
        model_tier: str,
        input_tokens: int,
        output_tokens: int,
        cost: float,
        latency_ms: int,
        cached: bool = False
    ):
        """
        Record a cost entry
        
        Args:
            task_id: Associated task ID (optional)
            provider: Provider name
            model: Model name
            model_tier: Model tier (opus/sonnet/haiku)
            input_tokens: Input token count
            output_tokens: Output token count
            cost: Cost in USD
            latency_ms: Latency in milliseconds
            cached: Whether response was cached
        """
        if not settings.app.enable_cost_tracking:
            return
        
        redis_client = await self._get_redis()
        
        # Update Redis counters
        today = datetime.now().strftime("%Y-%m-%d")
        this_month = datetime.now().strftime("%Y-%m")
        
        daily_key = self._get_daily_key(today)
        monthly_key = self._get_monthly_key(this_month)
        
        await redis_client.incrbyfloat(daily_key, cost)
        await redis_client.expire(daily_key, 2592000)  # 30 day TTL
        await redis_client.incrbyfloat(monthly_key, cost)
        await redis_client.expire(monthly_key, 2592000)  # 30 day TTL
        
        if task_id:
            task_key = self._get_task_key(task_id)
            await redis_client.incrbyfloat(task_key, cost)
            await redis_client.expire(task_key, 604800)  # 7 day TTL
        
        # Persist to database
        try:
            async with async_session_maker() as session:
                record = CostRecord(
                    task_id=task_id,
                    provider=provider,
                    model=model,
                    model_tier=model_tier,
                    input_tokens=input_tokens,
                    output_tokens=output_tokens,
                    cost=cost,
                    latency_ms=latency_ms,
                    cached=cached,
                )
                session.add(record)
                await session.commit()
        except Exception as e:
            logger.error(f"Failed to persist cost record: {e}")
        
        logger.debug(f"Cost recorded: ${cost:.6f} for {provider}/{model}")
    
    async def is_budget_exceeded(
        self,
        task_id: Optional[str] = None,
        estimated_cost: float = 0.0
    ) -> Optional[BudgetExceededError]:
        """
        Check if budget would be exceeded
        
        Returns:
            BudgetExceededError if exceeded, None otherwise
        """
        if not settings.app.enable_cost_tracking:
            return None
        
        redis_client = await self._get_redis()
        
        today = datetime.now().strftime("%Y-%m-%d")
        this_month = datetime.now().strftime("%Y-%m")
        
        daily_key = self._get_daily_key(today)
        monthly_key = self._get_monthly_key(this_month)
        
        daily_spent = float(await redis_client.get(daily_key) or 0)
        monthly_spent = float(await redis_client.get(monthly_key) or 0)
        
        # Check daily hard limit
        if daily_spent + estimated_cost > self.daily_hard_limit:
            return BudgetExceededError(
                limit_type="daily",
                current=daily_spent,
                limit=self.daily_hard_limit
            )
        
        # Check monthly hard limit
        if monthly_spent + estimated_cost > self.monthly_hard_limit:
            return BudgetExceededError(
                limit_type="monthly",
                current=monthly_spent,
                limit=self.monthly_hard_limit
            )
        
        # Check per-task limit
        if task_id:
            task_key = self._get_task_key(task_id)
            task_spent = float(await redis_client.get(task_key) or 0)
            if task_spent + estimated_cost > self.per_task_limit:
                return BudgetExceededError(
                    limit_type="per_task",
                    current=task_spent,
                    limit=self.per_task_limit
                )
        
        return None
    
    async def get_budget_status(self) -> BudgetStatus:
        """Get current budget status"""
        redis_client = await self._get_redis()
        
        today = datetime.now().strftime("%Y-%m-%d")
        this_month = datetime.now().strftime("%Y-%m")
        
        daily_key = self._get_daily_key(today)
        monthly_key = self._get_monthly_key(this_month)
        
        daily_spent = float(await redis_client.get(daily_key) or 0)
        monthly_spent = float(await redis_client.get(monthly_key) or 0)
        
        daily_ratio = daily_spent / self.daily_hard_limit
        monthly_ratio = monthly_spent / self.monthly_hard_limit
        max_ratio = max(daily_ratio, monthly_ratio)
        
        # Determine level
        if max_ratio >= 1.0:
            level = "exceeded"
        elif max_ratio >= self.DEGRADED_THRESHOLD:
            level = "degraded"
        elif max_ratio >= self.WARNING_THRESHOLD:
            level = "warning"
        else:
            level = "normal"
        
        # Model downgrade mapping for degraded mode
        degraded_map = {
            "opus": "sonnet",
            "sonnet": "haiku",
            "haiku": "haiku",
        }
        
        return BudgetStatus(
            level=level,
            daily_spent=round(daily_spent, 6),
            daily_limit=self.daily_hard_limit,
            daily_remaining=round(self.daily_hard_limit - daily_spent, 6),
            monthly_spent=round(monthly_spent, 6),
            monthly_limit=self.monthly_hard_limit,
            monthly_remaining=round(self.monthly_hard_limit - monthly_spent, 6),
            degraded_model_map=degraded_map if level == "degraded" else {},
        )
    
    async def get_daily_summary(self, days: int = 30) -> list[dict]:
        """Get daily cost summary for last N days"""
        redis_client = await self._get_redis()
        
        results = []
        for i in range(days):
            date = (datetime.now() - timedelta(days=i)).strftime("%Y-%m-%d")
            key = self._get_daily_key(date)
            cost = float(await redis_client.get(key) or 0)
            results.append({
                "date": date,
                "cost": round(cost, 6),
            })
        
        return list(reversed(results))
    
    async def get_task_cost(self, task_id: str) -> float:
        """Get total cost for a specific task"""
        redis_client = await self._get_redis()
        task_key = self._get_task_key(task_id)
        return float(await redis_client.get(task_key) or 0)
    
    async def check_profit_threshold(
        self,
        task_id: str,
        estimated_revenue: float
    ) -> bool:
        """
        Check if expected profit meets threshold
        
        Profit threshold: expected_profit >= ai_cost * min_profit_ratio
        """
        task_cost = await self.get_task_cost(task_id)
        min_profit = task_cost * self.config.min_profit_ratio
        
        return estimated_revenue >= min_profit
    
    async def get_costs_by_model(self, days: int = 30) -> dict:
        """Get cost breakdown by model tier"""
        try:
            async with async_session_maker() as session:
                from_date = datetime.now() - timedelta(days=days)
                
                result = await session.execute(
                    select(
                        CostRecord.model_tier,
                        func.sum(CostRecord.cost).label("total_cost"),
                        func.sum(CostRecord.input_tokens + CostRecord.output_tokens).label("total_tokens"),
                    )
                    .where(CostRecord.created_at >= from_date)
                    .group_by(CostRecord.model_tier)
                )
                
                return {
                    row.model_tier: {
                        "cost": round(row.total_cost or 0, 6),
                        "tokens": int(row.total_tokens or 0),
                    }
                    for row in result.all()
                }
        except Exception as e:
            logger.error(f"Failed to get costs by model: {e}")
            return {}
    
    async def reset(self):
        """Reset all cost counters (for testing)"""
        redis_client = await self._get_redis()
        
        keys = await redis_client.keys("cost:*")
        if keys:
            await redis_client.delete(*keys)
            logger.info("Reset all cost counters")
