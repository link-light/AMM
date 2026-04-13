"""
Base Worker Interface

All workers must inherit from BaseWorker and implement:
- execute(): Execute the specific task
- get_queue_name(): Return the queue name for this worker type
"""

import logging
from abc import ABC, abstractmethod
from typing import Optional

from core.config import settings
from core.models import Task, TaskResult, TaskStatus
from core.queue import QueueManager, queue_manager
from gateway.gateway import AIGateway

logger = logging.getLogger(__name__)


class BaseWorker(ABC):
    """
    Abstract base class for all task workers
    
    Workers consume tasks from queues and execute them.
    """
    
    def __init__(
        self,
        gateway: AIGateway = None,
        queue: QueueManager = None,
        config: dict = None
    ):
        self.gateway = gateway or AIGateway()
        self.queue = queue or queue_manager
        self.config = config or {}
        self.logger = logging.getLogger(self.__class__.__name__)
        self.max_retries = config.get("max_retries", 3)
    
    @abstractmethod
    async def execute(self, task: Task) -> TaskResult:
        """
        Execute the specific task
        
        Args:
            task: The task to execute
            
        Returns:
            TaskResult with execution results
        """
        pass
    
    @abstractmethod
    def get_queue_name(self) -> str:
        """Return the queue name for this worker type"""
        pass
    
    async def run(self):
        """
        Main loop: consume queue → execute → submit result
        
        Runs indefinitely until interrupted.
        """
        queue_name = self.get_queue_name()
        self.logger.info(f"Worker started: {self.__class__.__name__} on queue {queue_name}")
        
        await self.queue.connect()
        
        try:
            while True:
                # Dequeue task
                task_data = await self.queue.dequeue(queue_name, timeout=5)
                
                if task_data:
                    try:
                        task = Task.from_dict(task_data)
                        self.logger.info(f"Executing task {task.id}: {task.title}")
                        
                        # Execute
                        result = await self.execute(task)
                        
                        # Submit result
                        await self.submit_result(task, result)
                        
                    except Exception as e:
                        self.logger.error(f"Task execution failed: {e}")
                        await self.handle_failure(task, e)
                        
        except asyncio.CancelledError:
            self.logger.info(f"Worker stopped: {self.__class__.__name__}")
            raise
        except Exception as e:
            self.logger.error(f"Worker error: {e}")
            raise
        finally:
            await self.queue.disconnect()
    
    async def submit_result(self, task: Task, result: TaskResult):
        """
        Submit execution result to review queue
        
        Args:
            task: The executed task
            result: The execution result
        """
        from core.database import async_session_maker
        
        async with async_session_maker() as session:
            # Update task
            db_task = await session.get(Task, task.id)
            if db_task:
                db_task.status = TaskStatus.COMPLETED if result.status == "completed" else TaskStatus.FAILED
                db_task.output_data = result.output_data
                db_task.actual_cost = result.total_cost
                db_task.completed_at = datetime.utcnow()
                await session.commit()
        
        # Enqueue for review
        await self.queue.enqueue_for_review({
            "task_id": str(task.id),
            "result": result.to_dict(),
        })
        
        self.logger.info(f"Task {task.id} result submitted for review")
    
    async def handle_failure(self, task: Task, error: Exception):
        """
        Handle execution failure
        
        Implements retry logic with exponential backoff.
        """
        retry_count = task.metadata.get("retry_count", 0) + 1
        
        if retry_count < self.max_retries:
            self.logger.warning(
                f"Task {task.id} failed (attempt {retry_count}/{self.max_retries}): {error}"
            )
            
            # Update retry count
            task.metadata = {**(task.metadata or {}), "retry_count": retry_count}
            
            # Re-enqueue with delay
            await asyncio.sleep(2 ** retry_count)  # Exponential backoff
            await self.queue.enqueue_task(task.to_dict())
        else:
            self.logger.error(f"Task {task.id} failed permanently after {self.max_retries} retries")
            
            # Mark as failed
            from core.database import async_session_maker
            async with async_session_maker() as session:
                db_task = await session.get(Task, task.id)
                if db_task:
                    db_task.status = TaskStatus.FAILED
                    db_task.error_message = str(error)
                    await session.commit()


# Import at bottom to avoid circular imports
import asyncio
from datetime import datetime
