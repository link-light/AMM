"""
Tests for Rate Limiter

Tests:
- Normal token acquisition
- RPM limit triggering
- TPM limit triggering
- Priority weight effectiveness
- Token recovery
"""

import pytest
import time
from unittest.mock import AsyncMock, MagicMock, patch

from gateway.rate_limiter import RateLimiter, PRIORITY_WEIGHTS
from core.exceptions import RateLimitError


@pytest.fixture
def rate_limiter():
    """Create a fresh rate limiter for each test"""
    rl = RateLimiter()
    return rl


@pytest.mark.asyncio
async def test_normal_token_acquisition(rate_limiter):
    """
    Test normal token bucket acquisition.
    
    Verifies that tokens are acquired when under limits.
    """
    with patch.object(rate_limiter, '_get_redis') as mock_get_redis:
        mock_redis = AsyncMock()
        mock_get_redis.return_value = mock_redis
        
        # No existing usage - all limits available
        mock_redis.get.return_value = None
        mock_redis.pipeline.return_value = mock_redis
        mock_redis.execute = AsyncMock(return_value=[1, 1, 1])
        
        allowed, retry_after = await rate_limiter.acquire(
            model_tier="sonnet",
            expected_tokens=1000,
            priority="normal"
        )
        
        assert allowed is True
        assert retry_after == 0


@pytest.mark.asyncio
async def test_rpm_limit_triggering(rate_limiter):
    """
    Test that RPM limit blocks acquisition.
    
    Verifies that requests are rejected when RPM limit is exceeded.
    """
    with patch.object(rate_limiter, '_get_redis') as mock_get_redis:
        mock_redis = AsyncMock()
        mock_get_redis.return_value = mock_redis
        
        # RPM already at limit (60 for sonnet)
        mock_redis.get.return_value = b"60"
        
        allowed, retry_after = await rate_limiter.acquire(
            model_tier="sonnet",
            expected_tokens=100,
            priority="normal"
        )
        
        assert allowed is False
        assert retry_after > 0  # Should suggest retry after current minute


@pytest.mark.asyncio
async def test_tpm_limit_triggering(rate_limiter):
    """
    Test that TPM limit blocks acquisition.
    
    Verifies that requests are rejected when TPM limit is exceeded.
    """
    with patch.object(rate_limiter, '_get_redis') as mock_get_redis:
        mock_redis = AsyncMock()
        mock_get_redis.return_value = mock_redis
        
        # RPM fine, TPM at limit (200000 for sonnet)
        mock_redis.get.side_effect = [
            b"10",      # RPM (fine)
            b"200000",  # TPM (at limit)
        ]
        
        allowed, retry_after = await rate_limiter.acquire(
            model_tier="sonnet",
            expected_tokens=1000,
            priority="normal"
        )
        
        assert allowed is False
        assert retry_after > 0


@pytest.mark.asyncio
async def test_daily_cost_limit_triggering(rate_limiter):
    """
    Test that daily cost limit blocks acquisition.
    
    Verifies that requests are rejected when daily cost limit is exceeded.
    """
    with patch.object(rate_limiter, '_get_redis') as mock_get_redis:
        mock_redis = AsyncMock()
        mock_get_redis.return_value = mock_redis
        
        # RPM and TPM fine, daily cost at limit ($30 for sonnet)
        mock_redis.get.side_effect = [
            b"10",       # RPM
            b"10000",    # TPM
            b"29.99",    # Daily cost (close to $30 limit)
        ]
        
        allowed, retry_after = await rate_limiter.acquire(
            model_tier="sonnet",
            expected_tokens=1000,  # Would add ~$0.003
            priority="normal"
        )
        
        assert allowed is False
        assert retry_after > 3600  # Should suggest retry next day


@pytest.mark.asyncio
async def test_priority_weight_effectiveness(rate_limiter):
    """
    Test that priority weights affect rate limiting.
    
    Verifies that high priority tasks have higher effective limits.
    """
    with patch.object(rate_limiter, '_get_redis') as mock_get_redis:
        mock_redis = AsyncMock()
        mock_get_redis.return_value = mock_redis
        
        # RPM at 50 (normal would block at 60, high priority allows up to 90)
        mock_redis.get.return_value = b"50"
        mock_redis.pipeline.return_value = mock_redis
        mock_redis.execute = AsyncMock(return_value=[1, 1, 1])
        
        # High priority should still get through (limit = 60 * 3 / 2 = 90)
        allowed, _ = await rate_limiter.acquire(
            model_tier="sonnet",
            expected_tokens=100,
            priority="high"
        )
        
        assert allowed is True


@pytest.mark.asyncio
async def test_low_priority_stricter_limits(rate_limiter):
    """
    Test that low priority has stricter effective limits.
    
    Verifies that low priority tasks are throttled more aggressively.
    """
    with patch.object(rate_limiter, '_get_redis') as mock_get_redis:
        mock_redis = AsyncMock()
        mock_get_redis.return_value = mock_redis
        
        # RPM at 50 (low priority limit = 60 * 1 / 2 = 30)
        mock_redis.get.return_value = b"50"
        
        # Low priority should be blocked
        allowed, retry_after = await rate_limiter.acquire(
            model_tier="sonnet",
            expected_tokens=100,
            priority="low"
        )
        
        assert allowed is False


@pytest.mark.asyncio
async def test_priority_weights(rate_limiter):
    """
    Test priority weight values.
    """
    assert PRIORITY_WEIGHTS["high"] == 3
    assert PRIORITY_WEIGHTS["normal"] == 2
    assert PRIORITY_WEIGHTS["low"] == 1
    
    # High should have highest weight
    assert PRIORITY_WEIGHTS["high"] > PRIORITY_WEIGHTS["normal"]
    assert PRIORITY_WEIGHTS["normal"] > PRIORITY_WEIGHTS["low"]


@pytest.mark.asyncio
async def test_record_cost(rate_limiter):
    """
    Test recording actual cost for daily tracking.
    """
    with patch.object(rate_limiter, '_get_redis') as mock_get_redis:
        mock_redis = AsyncMock()
        mock_get_redis.return_value = mock_redis
        mock_redis.pipeline.return_value = mock_redis
        mock_redis.execute = AsyncMock(return_value=[None, None])
        
        await rate_limiter.record_cost("sonnet", 0.015)
        
        mock_redis.incrbyfloat.assert_called_once()


@pytest.mark.asyncio
async def test_get_status(rate_limiter):
    """
    Test getting current rate limit status.
    """
    with patch.object(rate_limiter, '_get_redis') as mock_get_redis:
        mock_redis = AsyncMock()
        mock_get_redis.return_value = mock_redis
        
        mock_redis.get.side_effect = [
            b"30",      # RPM
            b"50000",   # TPM
            b"10.0",    # Daily cost
        ]
        
        status = await rate_limiter.get_status("sonnet")
        
        assert status["model_tier"] == "sonnet"
        assert status["rpm"]["current"] == 30
        assert status["rpm"]["limit"] == 60
        assert status["tpm"]["current"] == 50000
        assert status["tpm"]["limit"] == 200000
        assert status["daily_cost"]["current"] == 10.0
        assert status["daily_cost"]["limit"] == 30.0


@pytest.mark.asyncio
async def test_reset(rate_limiter):
    """
    Test resetting rate limit counters.
    """
    with patch.object(rate_limiter, '_get_redis') as mock_get_redis:
        mock_redis = AsyncMock()
        mock_get_redis.return_value = mock_redis
        
        mock_redis.keys.return_value = [
            "rate_limit:sonnet:rpm:1234",
            "rate_limit:sonnet:tpm:1234",
        ]
        
        await rate_limiter.reset("sonnet")
        
        mock_redis.delete.assert_called_once()


@pytest.mark.asyncio
async def test_limits_by_tier(rate_limiter):
    """
    Test that different tiers have different limits.
    """
    # Opus (highest limits)
    opus_limits = rate_limiter.limits["opus"]
    assert opus_limits["rpm"] == 30
    assert opus_limits["tpm"] == 100000
    
    # Sonnet (medium limits)
    sonnet_limits = rate_limiter.limits["sonnet"]
    assert sonnet_limits["rpm"] == 60
    assert sonnet_limits["tpm"] == 200000
    
    # Haiku (lowest limits, highest throughput)
    haiku_limits = rate_limiter.limits["haiku"]
    assert haiku_limits["rpm"] == 120
    assert haiku_limits["tpm"] == 500000
    
    # Verify ordering
    assert opus_limits["rpm"] < sonnet_limits["rpm"] < haiku_limits["rpm"]


@pytest.mark.asyncio
async def test_default_to_sonnet_for_unknown_tier(rate_limiter):
    """
    Test that unknown tiers default to sonnet limits.
    """
    with patch.object(rate_limiter, '_get_redis') as mock_get_redis:
        mock_redis = AsyncMock()
        mock_get_redis.return_value = mock_redis
        mock_redis.get.return_value = None
        mock_redis.pipeline.return_value = mock_redis
        mock_redis.execute = AsyncMock(return_value=[1, 1, 1])
        
        allowed, _ = await rate_limiter.acquire(
            model_tier="unknown_tier",
            expected_tokens=100
        )
        
        # Should use sonnet limits
        assert allowed is True


@pytest.mark.asyncio
async def test_redis_key_generation(rate_limiter):
    """
    Test Redis key generation.
    """
    key = rate_limiter._get_redis_key("sonnet", "rpm")
    assert "rate_limit" in key
    assert "sonnet" in key
    assert "rpm" in key


@pytest.mark.asyncio
async def test_concurrent_acquisitions(rate_limiter):
    """
    Test that concurrent acquisitions are handled correctly.
    
    Verifies that pipeline operations are atomic.
    """
    with patch.object(rate_limiter, '_get_redis') as mock_get_redis:
        mock_redis = AsyncMock()
        mock_get_redis.return_value = mock_redis
        mock_redis.pipeline.return_value = mock_redis
        mock_redis.execute = AsyncMock(return_value=[1, 1, 1, 1, 1, 1])
        mock_redis.get.return_value = None
        
        # Simulate multiple concurrent requests
        results = await asyncio.gather(*[
            rate_limiter.acquire("sonnet", 100)
            for _ in range(5)
        ])
        
        # All should succeed (under limit)
        assert all(r[0] for r in results)


# Import asyncio for the concurrent test
import asyncio
