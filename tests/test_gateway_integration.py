"""
Integration tests for AI Gateway using fakeredis (in-memory Redis)

Tests:
- Rate limiting (RPM, TPM, daily cost)
- Circuit breaker (CLOSED → OPEN → HALF_OPEN → CLOSED)
- Cost tracking (daily/monthly limits, budget levels)

Uses fakeredis to avoid external Redis dependency.
"""

import asyncio
import pytest
import pytest_asyncio
import os
from unittest.mock import AsyncMock, MagicMock, patch

# Set memory Redis before importing gateway
os.environ["REDIS_URL"] = "memory://"

from gateway.gateway import AIGateway
from gateway.circuit_breaker import CircuitBreaker, CircuitState
from gateway.rate_limiter import RateLimiter
from gateway.cost_tracker import CostTracker
from gateway.providers.base import AIResponse
from core.exceptions import BudgetExceededError, CircuitBreakerOpenError, RateLimitError


@pytest.fixture
def fresh_gateway():
    """Create a fresh gateway instance for each test"""
    AIGateway._instance = None
    gateway = AIGateway()
    return gateway


@pytest_asyncio.fixture
async def circuit_breaker():
    """Create a circuit breaker with in-memory Redis"""
    cb = CircuitBreaker(
        failure_threshold=3,
        recovery_timeout=1,  # 1 second for faster tests
        half_open_max_calls=2
    )
    # Clear any existing state
    redis_client = await cb._get_redis()
    await redis_client.flushall()
    return cb


@pytest_asyncio.fixture
async def rate_limiter():
    """Create a rate limiter with in-memory Redis"""
    rl = RateLimiter()
    redis_client = await rl._get_redis()
    await redis_client.flushall()
    return rl


@pytest_asyncio.fixture
async def cost_tracker():
    """Create a cost tracker with in-memory Redis"""
    ct = CostTracker()
    redis_client = await ct._get_redis()
    await redis_client.flushall()
    return ct


class TestCircuitBreaker:
    """Test circuit breaker state machine"""
    
    @pytest.mark.asyncio
    async def test_closed_state_normal_passage(self, circuit_breaker):
        """Test that calls pass through normally in CLOSED state"""
        result = await circuit_breaker.check("anthropic", "claude-sonnet-4-6")
        assert result is True
    
    @pytest.mark.asyncio
    async def test_continuous_failures_trigger_open(self, circuit_breaker):
        """Test that consecutive failures trigger OPEN state"""
        # Record 3 failures (threshold)
        for i in range(3):
            await circuit_breaker.record_failure(
                "anthropic", "claude-sonnet-4-6", "server_error"
            )
        
        # Circuit should be OPEN now
        with pytest.raises(CircuitBreakerOpenError):
            await circuit_breaker.check("anthropic", "claude-sonnet-4-6")
    
    @pytest.mark.asyncio
    async def test_open_state_rejects_calls(self, circuit_breaker):
        """Test that OPEN state rejects all calls"""
        # First trigger circuit to OPEN through failures
        for i in range(3):
            await circuit_breaker.record_failure(
                "anthropic", "claude-sonnet-4-6", "server_error"
            )
        
        # Circuit should be OPEN now
        with pytest.raises(CircuitBreakerOpenError) as exc_info:
            await circuit_breaker.check("anthropic", "claude-sonnet-4-6")
        
        assert exc_info.value.provider == "anthropic"
    
    @pytest.mark.asyncio
    async def test_recovery_to_half_open(self, circuit_breaker):
        """Test transition from OPEN to HALF_OPEN after recovery timeout"""
        redis_client = await circuit_breaker._get_redis()
        
        # Force circuit to OPEN with old failure time
        old_time = asyncio.get_event_loop().time() - 10  # 10 seconds ago
        await redis_client.set(
            "circuit:anthropic:claude-sonnet-4-6:state",
            CircuitState.OPEN.value
        )
        await redis_client.set(
            "circuit:anthropic:claude-sonnet-4-6:last_failure",
            str(old_time)
        )
        
        # Should transition to HALF_OPEN (recovery_timeout=1s, elapsed=10s)
        state, metadata = await circuit_breaker.get_state("anthropic", "claude-sonnet-4-6")
        assert state == CircuitState.HALF_OPEN
    
    @pytest.mark.asyncio
    async def test_half_open_success_recovery(self, circuit_breaker):
        """Test recovery to CLOSED after successful calls in HALF_OPEN"""
        redis_client = await circuit_breaker._get_redis()
        
        # Set HALF_OPEN state with some successful calls
        await redis_client.set(
            "circuit:anthropic:claude-sonnet-4-6:state",
            CircuitState.HALF_OPEN.value
        )
        await redis_client.set(
            "circuit:anthropic:claude-sonnet-4-6:half_open_count",
            "2"  # Reached half_open_max_calls
        )
        
        # Record success should transition to CLOSED
        await circuit_breaker.record_success("anthropic", "claude-sonnet-4-6")
        
        state, _ = await circuit_breaker.get_state("anthropic", "claude-sonnet-4-6")
        assert state == CircuitState.CLOSED
    
    @pytest.mark.asyncio
    async def test_half_open_failure_returns_to_open(self, circuit_breaker):
        """Test that any failure in HALF_OPEN returns to OPEN"""
        redis_client = await circuit_breaker._get_redis()
        
        # Set HALF_OPEN state
        await redis_client.set(
            "circuit:anthropic:claude-sonnet-4-6:state",
            CircuitState.HALF_OPEN.value
        )
        
        # Record a failure
        await circuit_breaker.record_failure(
            "anthropic", "claude-sonnet-4-6", "server_error"
        )
        
        # Should be back to OPEN
        state, _ = await circuit_breaker.get_state("anthropic", "claude-sonnet-4-6")
        assert state == CircuitState.OPEN
    
    @pytest.mark.asyncio
    async def test_independent_circuits_per_provider(self, circuit_breaker):
        """Test that each provider/model has independent circuit"""
        # Trigger anthropic circuit to OPEN through failures
        for i in range(3):
            await circuit_breaker.record_failure(
                "anthropic", "claude-sonnet-4-6", "server_error"
            )
        
        # Anthropic should reject
        with pytest.raises(CircuitBreakerOpenError):
            await circuit_breaker.check("anthropic", "claude-sonnet-4-6")
        
        # OpenAI should pass (default CLOSED)
        result = await circuit_breaker.check("openai", "gpt-4o")
        assert result is True


class TestRateLimiter:
    """Test rate limiting functionality"""
    
    @pytest.mark.asyncio
    async def test_normal_token_acquisition(self, rate_limiter):
        """Test normal token bucket acquisition"""
        allowed, retry_after = await rate_limiter.acquire(
            model_tier="sonnet",
            expected_tokens=1000,
            priority="normal"
        )
        
        assert allowed is True
        assert retry_after == 0
    
    @pytest.mark.asyncio
    async def test_rpm_limit_triggering(self, rate_limiter):
        """Test that RPM limit blocks acquisition by actually hitting the limit"""
        # Acquire tokens up to the limit
        for i in range(60):
            await rate_limiter.acquire(
                model_tier="sonnet",
                expected_tokens=10,
                priority="normal"
            )
        
        # Next acquisition should be blocked
        allowed, retry_after = await rate_limiter.acquire(
            model_tier="sonnet",
            expected_tokens=100,
            priority="normal"
        )
        
        assert allowed is False
        assert retry_after > 0
    
    @pytest.mark.asyncio
    async def test_priority_weight_effectiveness(self, rate_limiter):
        """Test that high priority tasks have higher effective limits"""
        redis_client = await rate_limiter._get_redis()
        
        # Set RPM at 50 (normal would block at 60, high priority allows up to 90)
        now = int(asyncio.get_event_loop().time())
        minute_key = now // 60
        await redis_client.set(
            f"rate_limit:sonnet:rpm:{minute_key}",
            "50"
        )
        
        # High priority should still get through (limit = 60 * 3 / 2 = 90)
        allowed, _ = await rate_limiter.acquire(
            model_tier="sonnet",
            expected_tokens=100,
            priority="high"
        )
        
        assert allowed is True
    
    @pytest.mark.asyncio
    async def test_low_priority_stricter_limits(self, rate_limiter):
        """Test that low priority has stricter effective limits"""
        # Fill up to low priority limit (60 * 1 / 2 = 30)
        for i in range(31):
            await rate_limiter.acquire(
                model_tier="sonnet",
                expected_tokens=10,
                priority="low"
            )
        
        # Low priority should be blocked
        allowed, retry_after = await rate_limiter.acquire(
            model_tier="sonnet",
            expected_tokens=100,
            priority="low"
        )
        
        assert allowed is False
    
    @pytest.mark.asyncio
    async def test_record_cost(self, rate_limiter):
        """Test recording actual cost for daily tracking"""
        await rate_limiter.record_cost("sonnet", 0.015)
        
        # Verify cost was recorded by checking status
        status = await rate_limiter.get_status("sonnet")
        
        assert status["daily_cost"]["current"] > 0


class TestCostTracker:
    """Test cost tracking functionality"""
    
    @pytest.mark.asyncio
    async def test_normal_cost_recording(self, cost_tracker):
        """Test normal cost recording"""
        await cost_tracker.record(
            task_id="task-123",
            provider="anthropic",
            model="claude-sonnet-4-6",
            model_tier="sonnet",
            input_tokens=1000,
            output_tokens=500,
            cost=0.015,
            latency_ms=1000,
            cached=False
        )
        
        # Verify Redis counters
        redis_client = await cost_tracker._get_redis()
        daily = await redis_client.get(f"cost:daily:{__import__('datetime').datetime.now().strftime('%Y-%m-%d')}")
        
        assert float(daily) == 0.015
    
    @pytest.mark.asyncio
    async def test_daily_hard_limit_triggering(self, cost_tracker):
        """Test that daily hard limit triggers BudgetExceededError"""
        redis_client = await cost_tracker._get_redis()
        
        # Simulate already spent $19, limit is $20
        today = __import__('datetime').datetime.now().strftime("%Y-%m-%d")
        await redis_client.set(f"cost:daily:{today}", "19.0")
        
        # Try to spend $2 more
        error = await cost_tracker.is_budget_exceeded(estimated_cost=2.0)
        
        assert error is not None
        assert error.limit_type == "daily"
        assert error.current == 19.0
        assert error.limit == 20.0
    
    @pytest.mark.asyncio
    async def test_budget_levels(self, cost_tracker):
        """Test four-level budget熔断"""
        redis_client = await cost_tracker._get_redis()
        today = __import__('datetime').datetime.now().strftime("%Y-%m-%d")
        
        test_cases = [
            (5.0, "normal"),    # 25% of $20
            (16.0, "warning"),  # 80% of $20
            (18.5, "degraded"), # 92.5% of $20
            (21.0, "exceeded"), # 105% of $20
        ]
        
        for daily_spent, expected_level in test_cases:
            await redis_client.set(f"cost:daily:{today}", str(daily_spent))
            await redis_client.set(f"cost:monthly:{__import__('datetime').datetime.now().strftime('%Y-%m')}", "100.0")
            
            status = await cost_tracker.get_budget_status()
            
            assert status.level == expected_level, f"Failed for daily={daily_spent}, expected {expected_level}"
    
    @pytest.mark.asyncio
    async def test_degraded_model_map(self, cost_tracker):
        """Test that degraded level returns model downgrade mapping"""
        redis_client = await cost_tracker._get_redis()
        today = __import__('datetime').datetime.now().strftime("%Y-%m-%d")
        
        # 95% spent - degraded level
        await redis_client.set(f"cost:daily:{today}", "19.0")
        await redis_client.set(f"cost:monthly:{__import__('datetime').datetime.now().strftime('%Y-%m')}", "100.0")
        
        status = await cost_tracker.get_budget_status()
        
        assert status.level == "degraded"
        assert status.degraded_model_map["opus"] == "sonnet"
        assert status.degraded_model_map["sonnet"] == "haiku"


class TestAIGateway:
    """Test AI Gateway integration"""
    
    @pytest.mark.asyncio
    async def test_budget_exceeded_rejection(self, fresh_gateway):
        """Test that calls are rejected when budget is exceeded"""
        # Mock budget exceeded
        budget_error = BudgetExceededError(
            limit_type="daily",
            current=25.0,
            limit=20.0
        )
        
        with patch.object(fresh_gateway.cost_tracker, 'is_budget_exceeded', return_value=budget_error):
            with pytest.raises(BudgetExceededError) as exc_info:
                await fresh_gateway.complete(prompt="Test prompt")
            
            assert exc_info.value.limit_type == "daily"
    
    @pytest.mark.asyncio
    async def test_rate_limit_wait_behavior(self, fresh_gateway):
        """Test rate limiting wait/rejection behavior"""
        with patch.object(fresh_gateway.cost_tracker, 'is_budget_exceeded', return_value=None):
            with patch.object(fresh_gateway.cost_tracker, 'get_budget_status') as mock_budget:
                # Mock normal budget status (no degradation)
                mock_status = MagicMock()
                mock_status.level = "normal"
                mock_status.degraded_model_map = {}
                mock_budget.return_value = mock_status
                
                with patch.object(fresh_gateway.response_cache, 'get', return_value=None):
                    with patch.object(fresh_gateway.rate_limiter, 'acquire', return_value=(False, 30)):
                        with pytest.raises(RateLimitError) as exc_info:
                            await fresh_gateway.complete(
                                prompt="Test prompt",
                                model_tier="sonnet"
                            )
                        
                        assert exc_info.value.model_tier == "sonnet"
                        assert exc_info.value.retry_after == 30
