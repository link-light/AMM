"""
Circuit Breaker Pattern Implementation
Three-state: CLOSED → OPEN → HALF_OPEN → CLOSED
"""

import logging
import time
from enum import Enum
from typing import Optional

import redis.asyncio as redis

from core.config import settings
from core.exceptions import CircuitBreakerOpenError

logger = logging.getLogger(__name__)


class CircuitState(Enum):
    CLOSED = "closed"       # Normal operation
    OPEN = "open"          # Failing, reject calls
    HALF_OPEN = "half_open"  # Testing recovery


class CircuitBreaker:
    """
    Distributed circuit breaker using Redis
    
    States:
    - CLOSED: Normal operation, requests pass through
    - OPEN: Failing, requests are rejected immediately
    - HALF_OPEN: Testing if service recovered
    
    Transitions:
    - CLOSED → OPEN: failure_threshold reached
    - OPEN → HALF_OPEN: recovery_timeout elapsed
    - HALF_OPEN → CLOSED: half_open_max_calls successful
    - HALF_OPEN → OPEN: Any failure
    """
    
    def __init__(
        self,
        redis_client: redis.Redis = None,
        failure_threshold: int = None,
        recovery_timeout: int = None,
        half_open_max_calls: int = None
    ):
        self.redis = redis_client
        self.config = settings.ai_gateway
        
        self.failure_threshold = failure_threshold or self.config.circuit_failure_threshold
        self.recovery_timeout = recovery_timeout or self.config.circuit_recovery_timeout
        self.half_open_max_calls = half_open_max_calls or self.config.circuit_half_open_max_calls
        
        # Error types that trigger circuit breaker
        self.trigger_errors = [
            "rate_limit_exceeded",
            "server_error",
            "timeout",
            "auth_error",
        ]
    
    def _get_state_key(self, provider: str, model: str) -> str:
        """Redis key for circuit state"""
        return f"circuit:{provider}:{model}:state"
    
    def _get_failures_key(self, provider: str, model: str) -> str:
        """Redis key for failure count"""
        return f"circuit:{provider}:{model}:failures"
    
    def _get_last_failure_key(self, provider: str, model: str) -> str:
        """Redis key for last failure timestamp"""
        return f"circuit:{provider}:{model}:last_failure"
    
    def _get_half_open_count_key(self, provider: str, model: str) -> str:
        """Redis key for half-open call count"""
        return f"circuit:{provider}:{model}:half_open_count"
    
    async def _get_redis(self) -> redis.Redis:
        """Get Redis connection"""
        if self.redis is None:
            from core.queue import queue_manager
            await queue_manager.connect()
            self.redis = queue_manager.redis
        return self.redis
    
    async def get_state(self, provider: str, model: str) -> tuple[CircuitState, dict]:
        """
        Get current circuit state for a provider/model
        
        Returns:
            Tuple of (state, metadata)
        """
        redis_client = await self._get_redis()
        
        state_key = self._get_state_key(provider, model)
        failures_key = self._get_failures_key(provider, model)
        last_failure_key = self._get_last_failure_key(provider, model)
        
        state_val = await redis_client.get(state_key)
        if state_val:
            # Decode bytes to string if necessary
            if isinstance(state_val, bytes):
                state_val = state_val.decode('utf-8')
            state = CircuitState(state_val)
        else:
            state = CircuitState.CLOSED
        
        failures = await redis_client.get(failures_key)
        if failures:
            if isinstance(failures, bytes):
                failures = failures.decode('utf-8')
            failures = int(failures)
        else:
            failures = 0
        
        last_failure = await redis_client.get(last_failure_key)
        if last_failure:
            if isinstance(last_failure, bytes):
                last_failure = last_failure.decode('utf-8')
            last_failure = float(last_failure)
        else:
            last_failure = 0
        
        # Check if OPEN should transition to HALF_OPEN
        if state == CircuitState.OPEN:
            elapsed = time.time() - last_failure
            if elapsed >= self.recovery_timeout:
                state = CircuitState.HALF_OPEN
                await redis_client.set(state_key, state.value)
                await redis_client.delete(self._get_half_open_count_key(provider, model))
                logger.info(f"Circuit breaker for {provider}/{model} entering HALF_OPEN")
        
        metadata = {
            "failures": failures,
            "last_failure": last_failure,
            "failure_threshold": self.failure_threshold,
            "recovery_timeout": self.recovery_timeout,
            "half_open_max_calls": self.half_open_max_calls,
        }
        
        return state, metadata
    
    async def check(self, provider: str, model: str) -> bool:
        """
        Check if call should be allowed
        
        Returns:
            True if allowed, raises CircuitBreakerOpenError if not
        """
        if not settings.app.enable_circuit_breaker:
            return True
        
        state, metadata = await self.get_state(provider, model)
        
        if state == CircuitState.OPEN:
            recovery_in = int(self.recovery_timeout - (time.time() - metadata["last_failure"]))
            raise CircuitBreakerOpenError(
                provider=provider,
                model=model,
                recovery_in=max(0, recovery_in)
            )
        
        if state == CircuitState.HALF_OPEN:
            redis_client = await self._get_redis()
            count_key = self._get_half_open_count_key(provider, model)
            count = await redis_client.incr(count_key)
            
            if count > self.half_open_max_calls:
                await redis_client.set(
                    self._get_state_key(provider, model),
                    CircuitState.OPEN.value
                )
                raise CircuitBreakerOpenError(
                    provider=provider,
                    model=model,
                    recovery_in=self.recovery_timeout
                )
        
        return True
    
    async def record_success(self, provider: str, model: str):
        """Record a successful call"""
        redis_client = await self._get_redis()
        state_key = self._get_state_key(provider, model)
        
        state, _ = await self.get_state(provider, model)
        
        if state == CircuitState.HALF_OPEN:
            # Check if we've reached success threshold
            count_key = self._get_half_open_count_key(provider, model)
            count = await redis_client.get(count_key)
            count = int(count) if count else 0
            
            if count >= self.half_open_max_calls:
                # Transition to CLOSED
                await redis_client.set(state_key, CircuitState.CLOSED.value)
                await redis_client.delete(self._get_failures_key(provider, model))
                await redis_client.delete(count_key)
                logger.info(f"Circuit breaker for {provider}/{model} CLOSED (recovered)")
        else:
            # In CLOSED state, reset failures on success
            await redis_client.delete(self._get_failures_key(provider, model))
    
    async def record_failure(
        self,
        provider: str,
        model: str,
        error_type: str = "unknown"
    ):
        """Record a failed call"""
        if error_type not in self.trigger_errors:
            return
        
        redis_client = await self._get_redis()
        
        state_key = self._get_state_key(provider, model)
        failures_key = self._get_failures_key(provider, model)
        last_failure_key = self._get_last_failure_key(provider, model)
        
        state, _ = await self.get_state(provider, model)
        
        if state == CircuitState.HALF_OPEN:
            # Any failure in HALF_OPEN goes back to OPEN
            await redis_client.set(state_key, CircuitState.OPEN.value)
            await redis_client.set(last_failure_key, str(time.time()))
            await redis_client.delete(self._get_half_open_count_key(provider, model))
            logger.warning(f"Circuit breaker for {provider}/{model} OPEN (failure in HALF_OPEN)")
        else:
            # Increment failure count
            failures = await redis_client.incr(failures_key)
            await redis_client.set(last_failure_key, str(time.time()))
            
            if failures >= self.failure_threshold:
                await redis_client.set(state_key, CircuitState.OPEN.value)
                logger.warning(
                    f"Circuit breaker for {provider}/{model} OPEN "
                    f"({failures}/{self.failure_threshold} failures)"
                )
    
    async def get_all_status(self) -> dict:
        """Get status of all circuit breakers"""
        redis_client = await self._get_redis()
        
        pattern = "circuit:*:state"
        keys = await redis_client.keys(pattern)
        
        status = {}
        for key in keys:
            # Parse key: circuit:{provider}:{model}:state
            parts = key.split(":")
            if len(parts) >= 4:
                provider = parts[1]
                model = parts[2]
                state, metadata = await self.get_state(provider, model)
                
                status[f"{provider}/{model}"] = {
                    "state": state.value,
                    **metadata
                }
        
        return status
    
    async def reset(self, provider: str = None, model: str = None):
        """Reset circuit breaker (for testing)"""
        redis_client = await self._get_redis()
        
        if provider and model:
            pattern = f"circuit:{provider}:{model}:*"
        elif provider:
            pattern = f"circuit:{provider}:*"
        else:
            pattern = "circuit:*"
        
        keys = await redis_client.keys(pattern)
        if keys:
            await redis_client.delete(*keys)
            logger.info(f"Reset circuit breaker for {provider or 'all'}/{model or 'all'}")
