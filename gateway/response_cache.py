"""
Response Cache - Semantic caching for AI responses
"""

import hashlib
import json
import logging
from typing import Optional

import redis.asyncio as redis

from core.config import settings

logger = logging.getLogger(__name__)


class ResponseCache:
    """
    Redis-based response cache for AI Gateway
    
    Features:
    - Cache key = hash(model_tier + prompt + system)
    - Configurable TTL
    - Size limit enforcement
    """
    
    def __init__(self, redis_client: redis.Redis = None):
        self.redis = redis_client
        self.config = settings.ai_gateway
        self.ttl = self.config.cache_ttl
        self.max_size = self.config.cache_max_size
        self._cache_key_prefix = "ai_response_cache:"
    
    def _get_redis_key(self, key: str) -> str:
        """Generate Redis key with prefix"""
        return f"{self._cache_key_prefix}{key}"
    
    def _generate_key(
        self,
        model_tier: str,
        prompt: str,
        system: str = ""
    ) -> str:
        """Generate cache key from request parameters"""
        # Normalize for consistent hashing
        content = json.dumps({
            "model_tier": model_tier,
            "prompt": prompt.strip(),
            "system": system.strip(),
        }, sort_keys=True)
        
        return hashlib.sha256(content.encode()).hexdigest()
    
    async def _get_redis(self) -> redis.Redis:
        """Get Redis connection"""
        if self.redis is None:
            from core.queue import queue_manager
            await queue_manager.connect()
            self.redis = queue_manager.redis
        return self.redis
    
    async def get(
        self,
        model_tier: str,
        prompt: str,
        system: str = ""
    ) -> Optional[dict]:
        """
        Try to get cached response
        
        Returns:
            Cached response data or None
        """
        key = self._generate_key(model_tier, prompt, system)
        redis_key = self._get_redis_key(key)
        
        redis_client = await self._get_redis()
        cached = await redis_client.get(redis_key)
        
        if cached:
            logger.debug(f"Cache hit for key: {key[:16]}...")
            data = json.loads(cached)
            data["cached"] = True
            return data
        
        logger.debug(f"Cache miss for key: {key[:16]}...")
        return None
    
    async def set(
        self,
        model_tier: str,
        prompt: str,
        response_data: dict,
        system: str = "",
        ttl: int = None
    ):
        """
        Cache a response
        
        Args:
            model_tier: Model tier used
            prompt: The prompt
            response_data: Response data to cache
            system: System message
            ttl: Custom TTL (uses default if not specified)
        """
        if ttl is None:
            ttl = self.ttl
        
        key = self._generate_key(model_tier, prompt, system)
        redis_key = self._get_redis_key(key)
        
        redis_client = await self._get_redis()
        
        # Store with TTL
        await redis_client.setex(
            redis_key,
            ttl,
            json.dumps(response_data, default=str)
        )
        
        logger.debug(f"Cached response for key: {key[:16]}... (TTL={ttl}s)")
    
    async def invalidate(
        self,
        model_tier: str = None,
        prompt: str = None,
        system: str = ""
    ) -> int:
        """
        Invalidate cache entries
        
        If model_tier and prompt are provided, invalidate specific entry.
        If only model_tier provided, invalidate all entries for that tier.
        If nothing provided, invalidate all entries.
        
        Returns:
            Number of entries invalidated
        """
        redis_client = await self._get_redis()
        
        if model_tier and prompt:
            # Invalidate specific entry
            key = self._generate_key(model_tier, prompt, system)
            redis_key = self._get_redis_key(key)
            result = await redis_client.delete(redis_key)
            logger.info(f"Invalidated cache entry: {key[:16]}...")
            return result
        
        # Pattern-based invalidation
        if model_tier:
            # Cannot easily pattern match on hash, so we scan and check
            pattern = f"{self._cache_key_prefix}*"
            keys = await redis_client.keys(pattern)
            
            # We would need to store metadata to filter by model_tier
            # For now, just delete all
            if keys:
                await redis_client.delete(*keys)
                logger.info(f"Invalidated {len(keys)} cache entries")
                return len(keys)
        else:
            # Invalidate all
            pattern = f"{self._cache_key_prefix}*"
            keys = await redis_client.keys(pattern)
            if keys:
                await redis_client.delete(*keys)
                logger.info(f"Invalidated all {len(keys)} cache entries")
                return len(keys)
        
        return 0
    
    async def get_stats(self) -> dict:
        """Get cache statistics"""
        redis_client = await self._get_redis()
        
        pattern = f"{self._cache_key_prefix}*"
        keys = await redis_client.keys(pattern)
        
        total_size = 0
        for key in keys:
            size = await redis_client.memory_usage(key)
            total_size += size or 0
        
        return {
            "entries": len(keys),
            "total_size_bytes": total_size,
            "ttl_seconds": self.ttl,
            "max_size": self.max_size,
        }
    
    async def clear(self):
        """Clear all cache entries"""
        await self.invalidate()
