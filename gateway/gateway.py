"""
AI Gateway - Main Entry Point for all AI calls

This is the core component of the system. All AI model calls must go through this gateway.
Features:
- Budget control (hard/soft limits)
- Response caching
- Rate limiting
- Circuit breaker with fallback
- Multi-provider routing
- Cost tracking
- Audit logging
"""

import logging
import time
from dataclasses import dataclass
from typing import Optional

from core.config import settings
from core.exceptions import (
    BudgetExceededError,
    CircuitBreakerOpenError,
    ProviderError,
    RateLimitError,
)
from gateway.audit_logger import AuditLogger
from gateway.circuit_breaker import CircuitBreaker
from gateway.cost_tracker import BudgetStatus, CostTracker
from gateway.provider_router import ProviderRouter
from gateway.providers.base import AIResponse
from gateway.rate_limiter import RateLimiter
from gateway.response_cache import ResponseCache

logger = logging.getLogger(__name__)


@dataclass
class AICompletionRequest:
    """AI completion request parameters"""
    prompt: str
    model_tier: str = "sonnet"
    system: str = ""
    temperature: float = 0.3
    max_tokens: int = 4096
    tools: list = None
    context: dict = None
    task_id: Optional[str] = None
    priority: str = "normal"
    cacheable: bool = False


class AIGateway:
    """
    AI Gateway - Singleton pattern
    
    All AI calls must use this gateway to ensure:
    - Cost control
    - Fault tolerance
    - Provider switching
    - Audit trail
    
    Call flow:
    1. Budget check → BudgetExceededError
    2. Cache check (if cacheable=True)
    3. Rate limit check → wait or reject
    4. Circuit breaker check → fallback if open
    5. Provider routing → select best provider
    6. Execute call (with retry)
    7. Record cost
    8. Audit log
    9. Cache response
    10. Return result
    """
    
    _instance = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        if self._initialized:
            return
        
        self.config = settings.ai_gateway
        
        # Initialize components
        self.rate_limiter = RateLimiter()
        self.circuit_breaker = CircuitBreaker()
        self.cost_tracker = CostTracker()
        self.provider_router = ProviderRouter(self.circuit_breaker)
        self.response_cache = ResponseCache()
        self.audit_logger = AuditLogger()
        
        self._initialized = True
        logger.info("AI Gateway initialized")
    
    async def complete(
        self,
        prompt: str,
        model_tier: str = "sonnet",
        system: str = "",
        temperature: float = 0.3,
        max_tokens: int = 4096,
        tools: list = None,
        context: dict = None,
        task_id: str = None,
        priority: str = "normal",
        cacheable: bool = False
    ) -> AIResponse:
        """
        Main entry point for AI completion
        
        Args:
            prompt: The user prompt
            model_tier: Model tier (opus/sonnet/haiku)
            system: System message
            temperature: Sampling temperature (0-1)
            max_tokens: Maximum tokens to generate
            tools: Optional tool definitions
            context: Additional context
            task_id: Task ID for cost attribution
            priority: Request priority (high/normal/low)
            cacheable: Whether to cache response
            
        Returns:
            AIResponse with standardized format
            
        Raises:
            BudgetExceededError: If budget limit would be exceeded
            RateLimitError: If rate limit is hit
            CircuitBreakerOpenError: If circuit is open and no fallback
            ProviderError: If all providers fail
        """
        start_time = time.time()
        
        # Step 1: Budget check
        budget_error = await self.cost_tracker.is_budget_exceeded(task_id)
        if budget_error:
            logger.error(f"Budget exceeded: {budget_error}")
            raise budget_error
        
        # Check if we should downgrade model due to budget
        budget_status = await self.cost_tracker.get_budget_status()
        if budget_status.level == "degraded":
            original_tier = model_tier
            model_tier = budget_status.degraded_model_map.get(model_tier, model_tier)
            if original_tier != model_tier:
                logger.warning(f"Budget degraded: downgrading {original_tier} → {model_tier}")
        elif budget_status.level == "exceeded":
            raise BudgetExceededError(
                limit_type="budget",
                current=budget_status.daily_spent,
                limit=budget_status.daily_limit
            )
        
        # Step 2: Cache check
        if cacheable:
            cached = await self.response_cache.get(model_tier, prompt, system)
            if cached:
                logger.info(f"Cache hit for task {task_id}")
                # Convert cached dict to AIResponse
                return AIResponse(
                    content=cached["content"],
                    model=cached["model"],
                    provider=cached["provider"],
                    input_tokens=cached["input_tokens"],
                    output_tokens=cached["output_tokens"],
                    cost=0.0,  # No cost for cached response
                    latency_ms=int((time.time() - start_time) * 1000),
                    cached=True,
                )
        
        # Step 3: Rate limit check
        expected_tokens = len(prompt) // 4 + max_tokens  # Rough estimate
        allowed, retry_after = await self.rate_limiter.acquire(
            model_tier, expected_tokens, priority
        )
        if not allowed:
            raise RateLimitError(
                model_tier=model_tier,
                retry_after=retry_after
            )
        
        # Step 4-6: Execute with circuit breaker and fallback
        response = await self._execute_with_fallback(
            prompt=prompt,
            model_tier=model_tier,
            system=system,
            temperature=temperature,
            max_tokens=max_tokens,
            tools=tools,
        )
        
        # Step 7: Record cost
        await self.cost_tracker.record(
            task_id=task_id,
            provider=response.provider,
            model=response.model,
            model_tier=model_tier,
            input_tokens=response.input_tokens,
            output_tokens=response.output_tokens,
            cost=response.cost,
            latency_ms=response.latency_ms,
            cached=False,
        )
        
        # Also record for rate limiter cost tracking
        await self.rate_limiter.record_cost(model_tier, response.cost)
        
        # Step 8: Audit log
        await self.audit_logger.log_ai_call(
            task_id=task_id,
            model_tier=model_tier,
            provider=response.provider,
            model=response.model,
            prompt=prompt,
            input_tokens=response.input_tokens,
            output_tokens=response.output_tokens,
            cost=response.cost,
            latency_ms=response.latency_ms,
            success=True,
            cached=False,
        )
        
        # Step 9: Cache response
        if cacheable:
            await self.response_cache.set(
                model_tier=model_tier,
                prompt=prompt,
                system=system,
                response_data={
                    "content": response.content,
                    "model": response.model,
                    "provider": response.provider,
                    "input_tokens": response.input_tokens,
                    "output_tokens": response.output_tokens,
                }
            )
        
        # Step 10: Return
        total_latency_ms = int((time.time() - start_time) * 1000)
        return AIResponse(
            content=response.content,
            model=response.model,
            provider=response.provider,
            input_tokens=response.input_tokens,
            output_tokens=response.output_tokens,
            cost=response.cost,
            latency_ms=total_latency_ms,
            cached=False,
        )
    
    async def _execute_with_fallback(
        self,
        prompt: str,
        model_tier: str,
        system: str,
        temperature: float,
        max_tokens: int,
        tools: list = None,
    ) -> AIResponse:
        """
        Execute AI call with circuit breaker and fallback
        """
        last_error = None
        providers_tried = []
        
        # Try primary provider
        try:
            provider, model = await self.provider_router.select(model_tier)
            providers_tried.append(provider.name)
            
            # Check circuit breaker
            await self.circuit_breaker.check(provider.name, model)
            
            # Execute
            response = await provider.instance.call(
                prompt=prompt,
                system=system,
                temperature=temperature,
                max_tokens=max_tokens,
                tools=tools,
                model_tier=model_tier,
            )
            
            # Record success
            await self.circuit_breaker.record_success(provider.name, model)
            
            return response
            
        except CircuitBreakerOpenError:
            logger.warning(f"Circuit open for primary provider, trying fallback")
            last_error = CircuitBreakerOpenError()
        except ProviderError as e:
            logger.error(f"Primary provider error: {e}")
            await self.circuit_breaker.record_failure(
                e.provider, model_tier, "server_error"
            )
            last_error = e
        except Exception as e:
            logger.error(f"Unexpected error with primary provider: {e}")
            last_error = e
        
        # Try fallback providers
        for fallback_attempt in range(2):  # Try up to 2 fallbacks
            try:
                provider, model = await self.provider_router.fallback(
                    model_tier,
                    exclude_provider=providers_tried[-1] if providers_tried else None
                )
                providers_tried.append(provider.name)
                
                await self.circuit_breaker.check(provider.name, model)
                
                response = await provider.instance.call(
                    prompt=prompt,
                    system=system,
                    temperature=temperature,
                    max_tokens=max_tokens,
                    tools=tools,
                    model_tier=model_tier,
                )
                
                await self.circuit_breaker.record_success(provider.name, model)
                
                logger.info(f"Fallback to {provider.name} succeeded")
                return response
                
            except CircuitBreakerOpenError:
                logger.warning(f"Circuit open for fallback, trying next")
                continue
            except ProviderError as e:
                logger.error(f"Fallback provider error: {e}")
                await self.circuit_breaker.record_failure(
                    e.provider, model_tier, "server_error"
                )
                last_error = e
            except Exception as e:
                logger.error(f"Unexpected error with fallback: {e}")
                last_error = e
        
        # All providers failed
        raise ProviderError(
            message=f"All providers failed. Tried: {providers_tried}",
            provider="all",
            response=str(last_error) if last_error else "Unknown error"
        )
    
    async def get_budget_status(self) -> BudgetStatus:
        """Get current budget status"""
        return await self.cost_tracker.get_budget_status()
    
    async def get_rate_limit_status(self, model_tier: str = "sonnet") -> dict:
        """Get rate limit status for a model tier"""
        return await self.rate_limiter.get_status(model_tier)
    
    async def get_circuit_breaker_status(self) -> dict:
        """Get circuit breaker status"""
        return await self.circuit_breaker.get_all_status()
    
    async def get_provider_status(self) -> dict:
        """Get provider status"""
        return await self.provider_router.get_status()
    
    async def get_gateway_status(self) -> dict:
        """Get full gateway status"""
        return {
            "budget": (await self.get_budget_status()).__dict__,
            "rate_limits": {
                "opus": await self.get_rate_limit_status("opus"),
                "sonnet": await self.get_rate_limit_status("sonnet"),
                "haiku": await self.get_rate_limit_status("haiku"),
            },
            "circuit_breakers": await self.get_circuit_breaker_status(),
            "providers": await self.get_provider_status(),
        }


# Global gateway instance
gateway = AIGateway()
