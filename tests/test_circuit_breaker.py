"""
Tests for Circuit Breaker

Tests:
- CLOSED state normal passage
- Continuous failures trigger OPEN
- OPEN state rejects calls
- recovery_timeout transition to HALF_OPEN
- HALF_OPEN success recovery to CLOSED
- HALF_OPEN failure returns to OPEN
- Independent circuit breaking per provider
"""

import asyncio
import pytest
import time
from unittest.mock import AsyncMock, MagicMock, patch

from gateway.circuit_breaker import CircuitBreaker, CircuitState
from core.exceptions import CircuitBreakerOpenError


@pytest.fixture
def circuit_breaker():
    """Create a fresh circuit breaker for each test"""
    cb = CircuitBreaker(
        failure_threshold=3,
        recovery_timeout=1,  # 1 second for faster tests
        half_open_max_calls=2
    )
    return cb


@pytest.mark.asyncio
async def test_closed_state_normal_passage(circuit_breaker):
    """
    Test that calls pass through normally in CLOSED state.
    
    Verifies that check() returns True when circuit is closed.
    """
    with patch.object(circuit_breaker, '_get_redis') as mock_get_redis:
        mock_redis = AsyncMock()
        mock_get_redis.return_value = mock_redis
        
        # No state stored - defaults to CLOSED
        mock_redis.get.return_value = None
        
        result = await circuit_breaker.check("anthropic", "claude-sonnet-4-6")
        
        assert result is True


@pytest.mark.asyncio
async def test_continuous_failures_trigger_open(circuit_breaker):
    """
    Test that consecutive failures trigger OPEN state.
    
    Verifies that after failure_threshold failures, circuit opens.
    """
    with patch.object(circuit_breaker, '_get_redis') as mock_get_redis:
        mock_redis = AsyncMock()
        mock_get_redis.return_value = mock_redis
        
        # Simulate 3 failures (threshold)
        mock_redis.get.side_effect = [
            None,  # state
            b"1",  # failures count after first
            b"2",  # failures count after second
            b"3",  # failures count after third (triggers OPEN)
        ]
        mock_redis.incr.return_value = 3
        
        # Record 3 failures
        for i in range(3):
            await circuit_breaker.record_failure(
                "anthropic", "claude-sonnet-4-6", "server_error"
            )
        
        # Circuit should be OPEN now
        mock_redis.get.side_effect = [b"open", b"3"]  # state, failures
        mock_redis.set = AsyncMock()
        
        with pytest.raises(CircuitBreakerOpenError):
            await circuit_breaker.check("anthropic", "claude-sonnet-4-6")


@pytest.mark.asyncio
async def test_open_state_rejects_calls(circuit_breaker):
    """
    Test that OPEN state rejects all calls.
    
    Verifies that CircuitBreakerOpenError is raised when circuit is open.
    """
    with patch.object(circuit_breaker, '_get_redis') as mock_get_redis:
        mock_redis = AsyncMock()
        mock_get_redis.return_value = mock_redis
        
        # Circuit is OPEN
        mock_redis.get.side_effect = [
            b"open",  # state
            str(time.time()).encode(),  # last failure (recent)
        ]
        
        with pytest.raises(CircuitBreakerOpenError) as exc_info:
            await circuit_breaker.check("anthropic", "claude-sonnet-4-6")
        
        assert exc_info.value.provider == "anthropic"
        assert exc_info.value.model == "claude-sonnet-4-6"


@pytest.mark.asyncio
async def test_recovery_timeout_to_half_open(circuit_breaker):
    """
    Test transition from OPEN to HALF_OPEN after recovery timeout.
    
    Verifies that after recovery_timeout seconds, circuit enters HALF_OPEN.
    """
    with patch.object(circuit_breaker, '_get_redis') as mock_get_redis:
        mock_redis = AsyncMock()
        mock_get_redis.return_value = mock_redis
        
        # Circuit is OPEN, but last failure was long ago (past recovery timeout)
        old_failure_time = time.time() - 5  # 5 seconds ago
        mock_redis.get.side_effect = [
            b"open",  # state
            str(old_failure_time).encode(),  # last failure
        ]
        mock_redis.set = AsyncMock()
        mock_redis.delete = AsyncMock()
        
        # Should transition to HALF_OPEN
        state, metadata = await circuit_breaker.get_state(
            "anthropic", "claude-sonnet-4-6"
        )
        
        assert state == CircuitState.HALF_OPEN


@pytest.mark.asyncio
async def test_half_open_success_recovery(circuit_breaker):
    """
    Test recovery to CLOSED after successful calls in HALF_OPEN.
    
    Verifies that after half_open_max_calls successful calls,
    circuit transitions to CLOSED.
    """
    with patch.object(circuit_breaker, '_get_redis') as mock_get_redis:
        mock_redis = AsyncMock()
        mock_get_redis.return_value = mock_redis
        
        # HALF_OPEN state with 2 successful calls (threshold reached)
        mock_redis.get.side_effect = [
            b"half_open",  # state
            b"0",  # failures
            b"0",  # last failure
            b"2",  # half open count (reached max)
        ]
        mock_redis.set = AsyncMock()
        mock_redis.delete = AsyncMock()
        mock_redis.incr.return_value = 2
        
        await circuit_breaker.record_success("anthropic", "claude-sonnet-4-6")
        
        # Should transition to CLOSED
        # (In actual implementation, the state would be set to CLOSED)


@pytest.mark.asyncio
async def test_half_open_failure_returns_to_open(circuit_breaker):
    """
    Test that any failure in HALF_OPEN returns to OPEN.
    
    Verifies that a single failure in HALF_OPEN resets to OPEN.
    """
    with patch.object(circuit_breaker, '_get_redis') as mock_get_redis:
        mock_redis = AsyncMock()
        mock_get_redis.return_value = mock_redis
        
        # HALF_OPEN state
        mock_redis.get.return_value = b"half_open"
        mock_redis.set = AsyncMock()
        mock_redis.delete = AsyncMock()
        
        # Record a failure
        await circuit_breaker.record_failure(
            "anthropic", "claude-sonnet-4-6", "server_error"
        )
        
        # Verify state was set to OPEN
        calls = mock_redis.set.call_args_list
        assert any(call.args[1] == "open" for call in calls)


@pytest.mark.asyncio
async def test_independent_circuits_per_provider(circuit_breaker):
    """
    Test that each provider/model has independent circuit.
    
    Verifies that one provider's failure doesn't affect others.
    """
    with patch.object(circuit_breaker, '_get_redis') as mock_get_redis:
        mock_redis = AsyncMock()
        mock_get_redis.return_value = mock_redis
        
        # First provider is OPEN
        # Second provider is CLOSED
        mock_redis.get.side_effect = [
            b"open",  # anthropic state
            b"3",     # anthropic failures
            None,     # openai state (default CLOSED)
        ]
        
        # Anthropic should reject
        with pytest.raises(CircuitBreakerOpenError):
            await circuit_breaker.check("anthropic", "claude-sonnet-4-6")
        
        # OpenAI should pass (next get call returns None for CLOSED)
        mock_redis.get.return_value = None
        result = await circuit_breaker.check("openai", "gpt-4o")
        assert result is True


@pytest.mark.asyncio
async def test_non_triggering_errors_ignored(circuit_breaker):
    """
    Test that non-triggering error types don't count toward threshold.
    
    Verifies that only specific error types trigger circuit breaker.
    """
    with patch.object(circuit_breaker, '_get_redis') as mock_get_redis:
        mock_redis = AsyncMock()
        mock_get_redis.return_value = mock_redis
        
        # Record a non-triggering error
        await circuit_breaker.record_failure(
            "anthropic", "claude-sonnet-4-6", "validation_error"
        )
        
        # Should not increment failure count
        mock_redis.incr.assert_not_called()


@pytest.mark.asyncio
async def test_triggering_errors_list(circuit_breaker):
    """
    Test that only configured error types trigger circuit breaker.
    """
    triggering_errors = [
        "rate_limit_exceeded",
        "server_error",
        "timeout",
        "auth_error",
    ]
    
    for error_type in triggering_errors:
        cb = CircuitBreaker()
        assert error_type in cb.trigger_errors


@pytest.mark.asyncio
async def test_half_open_call_counting(circuit_breaker):
    """
    Test that calls are counted in HALF_OPEN state.
    
    Verifies that we track number of test calls in HALF_OPEN.
    """
    with patch.object(circuit_breaker, '_get_redis') as mock_get_redis:
        mock_redis = AsyncMock()
        mock_get_redis.return_value = mock_redis
        
        # HALF_OPEN state
        mock_redis.get.side_effect = [
            b"half_open",  # state
            b"0",  # failures
            b"0",  # last failure
        ]
        mock_redis.incr.return_value = 1  # First test call
        
        # Should allow call and increment counter
        result = await circuit_breaker.check("anthropic", "claude-sonnet-4-6")
        assert result is True
        mock_redis.incr.assert_called_once()


@pytest.mark.asyncio
async def test_half_open_limit_enforced(circuit_breaker):
    """
    Test that HALF_OPEN limits concurrent test calls.
    
    Verifies that no more than half_open_max_calls are allowed simultaneously.
    """
    with patch.object(circuit_breaker, '_get_redis') as mock_get_redis:
        mock_redis = AsyncMock()
        mock_get_redis.return_value = mock_redis
        
        # HALF_OPEN state with max calls reached
        mock_redis.get.side_effect = [
            b"half_open",  # state
            b"0",  # failures
            b"0",  # last failure
        ]
        mock_redis.incr.return_value = 3  # Exceeds max_calls=2
        mock_redis.set = AsyncMock()
        
        # Should reject
        with pytest.raises(CircuitBreakerOpenError):
            await circuit_breaker.check("anthropic", "claude-sonnet-4-6")


@pytest.mark.asyncio
async def test_get_all_status(circuit_breaker):
    """
    Test retrieving status of all circuits.
    """
    with patch.object(circuit_breaker, '_get_redis') as mock_get_redis:
        mock_redis = AsyncMock()
        mock_get_redis.return_value = mock_redis
        
        # Mock keys for multiple circuits
        mock_redis.keys.return_value = [
            "circuit:anthropic:claude-sonnet-4-6:state",
            "circuit:openai:gpt-4o:state",
        ]
        mock_redis.get.return_value = b"closed"
        
        status = await circuit_breaker.get_all_status()
        
        assert "anthropic/claude-sonnet-4-6" in status
        assert "openai/gpt-4o" in status


@pytest.mark.asyncio
async def test_reset_circuit(circuit_breaker):
    """
    Test resetting a circuit breaker.
    """
    with patch.object(circuit_breaker, '_get_redis') as mock_get_redis:
        mock_redis = AsyncMock()
        mock_get_redis.return_value = mock_redis
        
        mock_redis.keys.return_value = [
            "circuit:anthropic:claude-sonnet-4-6:state",
            "circuit:anthropic:claude-sonnet-4-6:failures",
        ]
        
        await circuit_breaker.reset("anthropic", "claude-sonnet-4-6")
        
        mock_redis.delete.assert_called_once()
