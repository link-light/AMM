"""
Redis Queue Manager - Unified interface for queue operations
"""

import json
import logging
from typing import Optional

import redis.asyncio as redis

from core.config import settings

logger = logging.getLogger(__name__)

# Queue name constants
QUEUE_SIGNALS_RAW = "queue:signals:raw"
QUEUE_SIGNALS_EVALUATED = "queue:signals:evaluated"
QUEUE_TASKS_PENDING = "queue:tasks:pending"
QUEUE_TASKS_HUMAN = "queue:tasks:human"
QUEUE_TASKS_REVIEW = "queue:tasks:review"
QUEUE_RESULTS_REVIEW = "queue:results:review"
QUEUE_AUDIT_LOGS = "queue:audit:logs"

# All queue names
ALL_QUEUES = [
    QUEUE_SIGNALS_RAW,
    QUEUE_SIGNALS_EVALUATED,
    QUEUE_TASKS_PENDING,
    QUEUE_TASKS_HUMAN,
    QUEUE_TASKS_REVIEW,
    QUEUE_RESULTS_REVIEW,
    QUEUE_AUDIT_LOGS,
]


class QueueManager:
    """Redis queue manager for distributed task processing"""
    
    def __init__(self, redis_url: Optional[str] = None):
        self.redis_url = redis_url or settings.redis_connection_url
        self._redis: Optional[redis.Redis] = None
    
    async def connect(self):
        """Establish Redis connection"""
        if self._redis is None:
            # Check if using fake Redis (memory://)
            if self.redis_url == 'memory://' or self.redis_url.startswith('memory'):
                import fakeredis.aioredis
                self._redis = fakeredis.aioredis.FakeRedis(
                    decode_responses=True,
                    encoding="utf-8"
                )
                logger.info("Connected to FakeRedis (in-memory)")
            else:
                self._redis = redis.from_url(
                    self.redis_url,
                    decode_responses=True,
                    encoding="utf-8"
                )
                logger.info("Connected to Redis")
    
    async def disconnect(self):
        """Close Redis connection"""
        if self._redis:
            await self._redis.close()
            self._redis = None
            logger.info("Disconnected from Redis")
    
    @property
    def redis(self) -> redis.Redis:
        """Get Redis client"""
        if self._redis is None:
            raise RuntimeError("Redis not connected. Call connect() first.")
        return self._redis
    
    async def enqueue(self, queue_name: str, data: dict) -> int:
        """
        Add item to queue
        
        Args:
            queue_name: Name of the queue
            data: Data to enqueue (will be JSON serialized)
            
        Returns:
            Length of queue after enqueue
        """
        await self.connect()
        serialized = json.dumps(data, default=str)
        result = await self.redis.lpush(queue_name, serialized)
        logger.debug(f"Enqueued to {queue_name}: {len(serialized)} bytes")
        return result
    
    async def dequeue(self, queue_name: str, timeout: int = 5) -> Optional[dict]:
        """
        Get item from queue (blocking)
        
        Args:
            queue_name: Name of the queue
            timeout: Timeout in seconds (0 = non-blocking)
            
        Returns:
            Dequeued data or None if timeout
        """
        await self.connect()
        result = await self.redis.brpop(queue_name, timeout=timeout)
        if result:
            _, serialized = result
            data = json.loads(serialized)
            logger.debug(f"Dequeued from {queue_name}")
            return data
        return None
    
    async def peek(self, queue_name: str) -> Optional[dict]:
        """
        Peek at the last item in queue without removing
        
        Args:
            queue_name: Name of the queue
            
        Returns:
            Last item in queue or None if empty
        """
        await self.connect()
        serialized = await self.redis.lindex(queue_name, -1)
        if serialized:
            return json.loads(serialized)
        return None
    
    async def length(self, queue_name: str) -> int:
        """
        Get queue length
        
        Args:
            queue_name: Name of the queue
            
        Returns:
            Number of items in queue
        """
        await self.connect()
        return await self.redis.llen(queue_name)
    
    async def clear(self, queue_name: str) -> int:
        """
        Clear all items from queue
        
        Args:
            queue_name: Name of the queue
            
        Returns:
            Number of items removed
        """
        await self.connect()
        count = await self.redis.llen(queue_name)
        await self.redis.delete(queue_name)
        logger.info(f"Cleared {count} items from {queue_name}")
        return count
    
    async def get_all(self, queue_name: str) -> list[dict]:
        """
        Get all items from queue without removing (for inspection)
        
        Args:
            queue_name: Name of the queue
            
        Returns:
            List of all items in queue
        """
        await self.connect()
        items = await self.redis.lrange(queue_name, 0, -1)
        return [json.loads(item) for item in items]
    
    async def remove(self, queue_name: str, data: dict) -> int:
        """
        Remove specific item from queue
        
        Args:
            queue_name: Name of the queue
            data: Data to remove (will be JSON serialized for comparison)
            
        Returns:
            Number of items removed
        """
        await self.connect()
        serialized = json.dumps(data, default=str)
        return await self.redis.lrem(queue_name, 0, serialized)
    
    # Helper methods for specific queues
    
    async def enqueue_signal_raw(self, signal_data: dict) -> int:
        """Enqueue raw signal for evaluation"""
        return await self.enqueue(QUEUE_SIGNALS_RAW, signal_data)
    
    async def enqueue_signal_evaluated(self, signal_data: dict) -> int:
        """Enqueue evaluated signal for dispatch"""
        return await self.enqueue(QUEUE_SIGNALS_EVALUATED, signal_data)
    
    async def enqueue_task(self, task_data: dict) -> int:
        """Enqueue task for execution"""
        return await self.enqueue(QUEUE_TASKS_PENDING, task_data)
    
    async def enqueue_human_task(self, task_data: dict) -> int:
        """Enqueue human task"""
        return await self.enqueue(QUEUE_TASKS_HUMAN, task_data)
    
    async def enqueue_for_review(self, result_data: dict) -> int:
        """Enqueue result for review"""
        return await self.enqueue(QUEUE_RESULTS_REVIEW, result_data)


# Global queue manager instance
queue_manager = QueueManager()


async def get_queue() -> QueueManager:
    """Dependency to get queue manager"""
    await queue_manager.connect()
    return queue_manager
