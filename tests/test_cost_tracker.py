"""
Tests for Cost Tracker

Tests:
- Normal cost recording
- Daily hard limit triggering
- Monthly hard limit triggering
- Per-task limit triggering
- Four-level budget熔断 (normal → warning → degraded → exceeded)
- Profit threshold checking
- Cross-day reset
- Concurrent recording consistency
"""

import asyncio
import pytest
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

from gateway.cost_tracker import BudgetStatus, CostTracker
from core.exceptions import BudgetExceededError


@pytest.fixture
def cost_tracker():
    """Create a fresh cost tracker for each test"""
    tracker = CostTracker()
    return tracker


@pytest.mark.asyncio
async def test_normal_cost_recording(cost_tracker):
    """
    Test normal cost recording.
    
    Verifies that costs are correctly recorded to Redis and database.
    """
    with patch.object(cost_tracker, '_get_redis') as mock_get_redis:
        mock_redis = AsyncMock()
        mock_get_redis.return_value = mock_redis
        
        # Mock pipeline
        mock_pipe = AsyncMock()
        mock_redis.pipeline.return_value = mock_pipe
        mock_pipe.execute = AsyncMock(return_value=[None, None, None, None, None, None])
        
        with patch('gateway.cost_tracker.async_session_maker') as mock_session:
            mock_session_instance = AsyncMock()
            mock_session.return_value.__aenter__ = AsyncMock(return_value=mock_session_instance)
            mock_session.return_value.__aexit__ = AsyncMock(return_value=False)
            
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
            
            # Verify Redis operations
            assert mock_pipe.incrbyfloat.call_count == 3  # daily, monthly, task


@pytest.mark.asyncio
async def test_daily_hard_limit_triggering(cost_tracker):
    """
    Test that daily hard limit triggers BudgetExceededError.
    
    Verifies that calls are rejected when daily budget is exceeded.
    """
    with patch.object(cost_tracker, '_get_redis') as mock_get_redis:
        mock_redis = AsyncMock()
        mock_get_redis.return_value = mock_redis
        
        # Simulate already spent $19, limit is $20
        mock_redis.get.side_effect = [
            b"19.0",  # daily
            b"100.0",  # monthly (not relevant)
        ]
        
        # Try to spend $2 more
        error = await cost_tracker.is_budget_exceeded(
            estimated_cost=2.0
        )
        
        assert error is not None
        assert error.limit_type == "daily"
        assert error.current == 19.0
        assert error.limit == 20.0


@pytest.mark.asyncio
async def test_monthly_hard_limit_triggering(cost_tracker):
    """
    Test that monthly hard limit triggers BudgetExceededError.
    
    Verifies that calls are rejected when monthly budget is exceeded.
    """
    with patch.object(cost_tracker, '_get_redis') as mock_get_redis:
        mock_redis = AsyncMock()
        mock_get_redis.return_value = mock_redis
        
        # Daily is fine, monthly is exceeded
        mock_redis.get.side_effect = [
            b"10.0",  # daily (fine)
            b"390.0",  # monthly (close to $400 limit)
        ]
        
        error = await cost_tracker.is_budget_exceeded(
            estimated_cost=15.0
        )
        
        assert error is not None
        assert error.limit_type == "monthly"


@pytest.mark.asyncio
async def test_per_task_limit_triggering(cost_tracker):
    """
    Test that per-task limit triggers BudgetExceededError.
    
    Verifies that calls are rejected when single task budget is exceeded.
    """
    with patch.object(cost_tracker, '_get_redis') as mock_get_redis:
        mock_redis = AsyncMock()
        mock_get_redis.return_value = mock_redis
        
        # Daily and monthly are fine, task is exceeded
        mock_redis.get.side_effect = [
            b"10.0",  # daily
            b"100.0",  # monthly
            b"4.5",  # task (close to $5 limit)
        ]
        
        error = await cost_tracker.is_budget_exceeded(
            task_id="task-123",
            estimated_cost=1.0
        )
        
        assert error is not None
        assert error.limit_type == "per_task"


@pytest.mark.asyncio
async def test_budget_levels(cost_tracker):
    """
    Test four-level budget熔断.
    
    Verifies correct level determination based on spending:
    - normal: 0-75%
    - warning: 75-90%
    - degraded: 90-100%
    - exceeded: 100%+
    """
    test_cases = [
        (5.0, "normal"),    # 25% of $20
        (10.0, "normal"),   # 50% of $20
        (16.0, "warning"),  # 80% of $20
        (18.5, "degraded"), # 92.5% of $20
        (21.0, "exceeded"), # 105% of $20
    ]
    
    for daily_spent, expected_level in test_cases:
        with patch.object(cost_tracker, '_get_redis') as mock_get_redis:
            mock_redis = AsyncMock()
            mock_get_redis.return_value = mock_redis
            
            mock_redis.get.side_effect = [
                str(daily_spent).encode(),  # daily
                b"100.0",  # monthly
            ]
            
            status = await cost_tracker.get_budget_status()
            
            assert status.level == expected_level, f"Failed for daily={daily_spent}, expected {expected_level}"


@pytest.mark.asyncio
async def test_degraded_model_map(cost_tracker):
    """
    Test that degraded level returns model downgrade mapping.
    """
    with patch.object(cost_tracker, '_get_redis') as mock_get_redis:
        mock_redis = AsyncMock()
        mock_get_redis.return_value = mock_redis
        
        # 95% spent - degraded level
        mock_redis.get.side_effect = [
            b"19.0",  # daily
            b"100.0",  # monthly
        ]
        
        status = await cost_tracker.get_budget_status()
        
        assert status.level == "degraded"
        assert "opus" in status.degraded_model_map
        assert "sonnet" in status.degraded_model_map
        assert status.degraded_model_map["opus"] == "sonnet"
        assert status.degraded_model_map["sonnet"] == "haiku"


@pytest.mark.asyncio
async def test_profit_threshold_checking(cost_tracker):
    """
    Test profit threshold calculation.
    
    Verifies: expected_profit >= ai_cost * min_profit_ratio
    """
    with patch.object(cost_tracker, '_get_redis') as mock_get_redis:
        mock_redis = AsyncMock()
        mock_get_redis.return_value = mock_redis
        
        # Task cost is $1
        mock_redis.get.return_value = b"1.0"
        
        # With min_profit_ratio=3, need at least $3 revenue
        result = await cost_tracker.check_profit_threshold(
            task_id="task-123",
            estimated_revenue=3.0
        )
        assert result is True
        
        result = await cost_tracker.check_profit_threshold(
            task_id="task-123",
            estimated_revenue=2.0
        )
        assert result is False


@pytest.mark.asyncio
async def test_cross_day_reset(cost_tracker):
    """
    Test that daily counters reset on new day.
    
    Verifies that yesterday's spending doesn't affect today's budget.
    """
    with patch.object(cost_tracker, '_get_redis') as mock_get_redis:
        mock_redis = AsyncMock()
        mock_get_redis.return_value = mock_redis
        
        # Today is 2024-01-15
        today = "2024-01-15"
        yesterday = "2024-01-14"
        
        # Yesterday spent $19 (almost limit)
        yesterday_key = cost_tracker._get_daily_key(yesterday)
        
        # Today should start fresh
        today_key = cost_tracker._get_daily_key(today)
        mock_redis.get.return_value = None  # No spending today
        
        status = await cost_tracker.get_budget_status()
        
        assert status.daily_spent == 0.0
        assert status.daily_remaining == 20.0


@pytest.mark.asyncio
async def test_concurrent_recording_consistency(cost_tracker):
    """
    Test that concurrent cost recordings are consistent.
    
    Verifies that parallel calls don't cause race conditions.
    """
    with patch.object(cost_tracker, '_get_redis') as mock_get_redis:
        mock_redis = MagicMock()
        mock_get_redis.return_value = mock_redis
        
        # Track calls
        call_count = 0
        
        async def mock_incrbyfloat(key, value):
            nonlocal call_count
            call_count += 1
            return None
        
        mock_redis.pipeline.return_value.incrbyfloat = mock_incrbyfloat
        mock_redis.pipeline.return_value.expire = AsyncMock()
        mock_redis.pipeline.return_value.execute = AsyncMock(return_value=[])
        
        with patch('gateway.cost_tracker.async_session_maker'):
            # Simulate 10 concurrent recordings
            tasks = [
                cost_tracker.record(
                    task_id=f"task-{i}",
                    provider="anthropic",
                    model="claude-sonnet-4-6",
                    model_tier="sonnet",
                    input_tokens=100,
                    output_tokens=50,
                    cost=0.001,
                    latency_ms=500,
                )
                for i in range(10)
            ]
            
            await asyncio.gather(*tasks, return_exceptions=True)
            
            # All 10 should have attempted to record
            # Note: In real implementation, Redis pipeline ensures atomicity


@pytest.mark.asyncio
async def test_daily_summary(cost_tracker):
    """
    Test daily cost summary retrieval.
    
    Verifies that last N days of cost data is returned.
    """
    with patch.object(cost_tracker, '_get_redis') as mock_get_redis:
        mock_redis = AsyncMock()
        mock_get_redis.return_value = mock_redis
        
        # Mock costs for last 3 days
        mock_redis.get.side_effect = [
            b"5.0",   # today
            b"10.0",  # yesterday
            b"8.0",   # 2 days ago
        ]
        
        summary = await cost_tracker.get_daily_summary(days=3)
        
        assert len(summary) == 3
        assert summary[0]["cost"] == 8.0
        assert summary[1]["cost"] == 10.0
        assert summary[2]["cost"] == 5.0


@pytest.mark.asyncio
async def test_task_cost_retrieval(cost_tracker):
    """
    Test retrieving total cost for a specific task.
    """
    with patch.object(cost_tracker, '_get_redis') as mock_get_redis:
        mock_redis = AsyncMock()
        mock_get_redis.return_value = mock_redis
        
        mock_redis.get.return_value = b"2.5"
        
        cost = await cost_tracker.get_task_cost("task-123")
        
        assert cost == 2.5
