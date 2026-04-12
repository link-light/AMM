"""
Token Bucket Rate Limiter for AI Gateway
Supports multi-dimensional limiting: RPM, TPM, daily cost
"""

import logging
import time
from typing import Optional

import redis.asyncio as redis

from core.config import settings

logger = logging.getLogger(__name__)

# Priority weights
PRIORITY_WEIGHTS = {
    "high": 3,
    "normal": 2,
    "low": 1,
}

# Model pricing per 1M tokens (output price for estimation)
MODEL_PRICING = {
    "opus": 75.0,      # $75 per 1M output tokens
    "sonnet": 15.0,    # $15 per 1M output tokens
    "haiku": 4.0,      # $4 per 1M output tokens
}


class RateLimiter:
    """
    Token bucket rate limiter using Redis
    
    Supports:
    - RPM (requests per minute)
    - TPM (tokens per minute)
    - Daily cost limit
    - Priority-based quota allocation
    """
    
    def __init__(self, redis_client: redis.Redis = None):
        self.redis = redis_client
        self.config = settings.ai_gateway
        
        # Rate limit configuration by tier
        self.limits = {
            "opus": {
                "rpm": self.config.opus_rpm,
                "tpm": self.config.opus_tpm,
                "daily_cost": self.config.opus_daily_cost,
            },
            "sonnet": {
                "rpm": self.config.sonnet_rpm,
                "tpm": self.config.sonnet_tpm,
                "daily_cost": self.config.sonnet_daily_cost,
            },
            "haiku": {
                "rpm": self.config.haiku_rpm,
                "tpm": self.config.haiku_tpm,
                "daily_cost": self.config.haiku_daily_cost,
            },
        }
    
    def _get_redis_key(self, model_tier: str, metric: str) -> str:
        """Generate Redis key for rate limit tracking"""
        return f"rate_limit:{model_tier}:{metric}"
    
    async def _get_redis(self) -> redis.Redis:
        """Get Redis connection"""
        if self.redis is None:
            from core.queue import queue_manager
            await queue_manager.connect()
            self.redis = queue_manager.redis
        return self.redis
    
    async def acquire(
        self,
        model_tier: str,
        expected_tokens: int = 1000,
        priority: str = "normal"
    ) -> tuple[bool, int]:
        """
        Try to acquire rate limit quota
        
        Args:
            model_tier: Model tier (opus/sonnet/haiku)
            expected_tokens: Expected token usage
            priority: Request priority (high/normal/low)
            
        Returns:
            Tuple of (success, retry_after_seconds)
        """
        redis_client = await self._get_redis()
        limits = self.limits.get(model_tier, self.limits["sonnet"])
        priority_weight = PRIORITY_WEIGHTS.get(priority, 2)
        
        now = int(time.time())
        minute_key = now // 60
        day_key = now // 86400
        
        # Check RPM
        rpm_key = self._get_redis_key(f"{model_tier}:rpm", str(minute_key))
        current_rpm = await redis_client.get(rpm_key)
        current_rpm = int(current_rpm) if current_rpm else 0
        
        # Priority-based RPM limit adjustment
        adjusted_rpm_limit = limits["rpm"] * priority_weight // 2
        if current_rpm >= adjusted_rpm_limit:
            retry_after = 60 - (now % 60)
            logger.warning(f"RPM limit exceeded for {model_tier} (priority={priority})")
            return False, retry_after
        
        # Check TPM
        tpm_key = self._get_redis_key(f"{model_tier}:tpm", str(minute_key))
        current_tpm = await redis_client.get(tpm_key)
        current_tpm = int(current_tpm) if current_tpm else 0
        
        adjusted_tpm_limit = limits["tpm"] * priority_weight // 2
        if current_tpm + expected_tokens > adjusted_tpm_limit:
            retry_after = 60 - (now % 60)
            logger.warning(f"TPM limit exceeded for {model_tier} (priority={priority})")
            return False, retry_after
        
        # Check daily cost
        cost_key = self._get_redis_key(f"{model_tier}:cost", str(day_key))
        current_cost = await redis_client.get(cost_key)
        current_cost = float(current_cost) if current_cost else 0.0
        
        # Estimate cost based on model tier pricing
        price_per_million = MODEL_PRICING.get(model_tier, 15.0)  # default to sonnet price
        estimated_cost = expected_tokens * price_per_million / 1_000_000
        if current_cost + estimated_cost > limits["daily_cost"]:
            retry_after = 86400 - (now % 86400)
            logger.warning(f"Daily cost limit exceeded for {model_tier}")
            return False, retry_after
        
        # All checks passed - acquire tokens
        pipe = redis_client.pipeline()
        pipe.incr(rpm_key)
        pipe.expire(rpm_key, 120)  # 2 minute TTL
        pipe.incrby(tpm_key, expected_tokens)
        pipe.expire(tpm_key, 120)
        await pipe.execute()
        
        logger.debug(f"Rate limit acquired for {model_tier} (priority={priority})")
        return True, 0
    
    async def record_cost(self, model_tier: str, cost: float):
        """Record actual cost for daily tracking"""
        redis_client = await self._get_redis()
        day_key = int(time.time()) // 86400
        cost_key = self._get_redis_key(f"{model_tier}:cost", str(day_key))
        
        pipe = redis_client.pipeline()
        pipe.incrbyfloat(cost_key, cost)
        pipe.expire(cost_key, 172800)  # 2 day TTL
        await pipe.execute()
    
    async def get_status(self, model_tier: str) -> dict:
        """Get current rate limit status"""
        redis_client = await self._get_redis()
        limits = self.limits.get(model_tier, self.limits["sonnet"])
        
        now = int(time.time())
        minute_key = now // 60
        day_key = now // 86400
        
        rpm_key = self._get_redis_key(f"{model_tier}:rpm", str(minute_key))
        tpm_key = self._get_redis_key(f"{model_tier}:tpm", str(minute_key))
        cost_key = self._get_redis_key(f"{model_tier}:cost", str(day_key))
        
        rpm_val = await redis_client.get(rpm_key)
        tpm_val = await redis_client.get(tpm_key)
        cost_val = await redis_client.get(cost_key)
        
        return {
            "model_tier": model_tier,
            "rpm": {
                "current": int(rpm_val) if rpm_val else 0,
                "limit": limits["rpm"],
                "remaining": max(0, limits["rpm"] - (int(rpm_val) if rpm_val else 0)),
            },
            "tpm": {
                "current": int(tpm_val) if tpm_val else 0,
                "limit": limits["tpm"],
                "remaining": max(0, limits["tpm"] - (int(tpm_val) if tpm_val else 0)),
            },
            "daily_cost": {
                "current": round(float(cost_val), 6) if cost_val else 0.0,
                "limit": limits["daily_cost"],
                "remaining": round(limits["daily_cost"] - (float(cost_val) if cost_val else 0.0), 6),
            },
        }
    
    async def reset(self, model_tier: str = None):
        """Reset rate limit counters (for testing)"""
        redis_client = await self._get_redis()
        
        if model_tier:
            pattern = f"rate_limit:{model_tier}:*"
        else:
            pattern = "rate_limit:*"
        
        keys = await redis_client.keys(pattern)
        if keys:
            await redis_client.delete(*keys)
            logger.info(f"Reset rate limits for {model_tier or 'all'}")
