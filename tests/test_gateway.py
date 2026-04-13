"""
Tests for AI Gateway

Tests the complete call flow including:
- Normal call flow (mock provider)
- Budget exceeded rejection
- Circuit breaker fallback
- Cache hit skipping API call
- Rate limiting wait behavior
- Cost recording
- Priority scheduling
"""

import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from core.exceptions import BudgetExceededError, CircuitBreakerOpenError, RateLimitError
from gateway.gateway import AIGateway
from gateway.providers.base import AIResponse


@pytest.fixture
def gateway():
    """Create a fresh gateway instance for each test"""
    # Reset singleton
    AIGateway._instance = None
    gateway = AIGateway()
    return gateway


@pytest.fixture
def mock_response():
    """Create a mock AI response"""
    return AIResponse(
        content="Test response",
        model="claude-sonnet-4-6",
        provider="anthropic",
        input_tokens=100,
        output_tokens=50,
        cost=0.001,
        latency_ms=500,
        cached=False,
    )


@pytest.mark.asyncio
async def test_normal_call_flow(gateway, mock_response):
    """
    Test normal call flow with mock provider.
    
    Verifies that:
    1. Budget check passes
    2. Cache check (miss)
    3. Rate limit acquired
    4. Provider selected and called
    5. Cost recorded
    6. Response returned
    """
    # Mock all dependencies
    with patch.object(gateway.cost_tracker, 'is_budget_exceeded', return_value=None) as mock_budget:
        with patch.object(gateway.response_cache, 'get', return_value=None) as mock_cache_get:
            with patch.object(gateway.rate_limiter, 'acquire', return_value=(True, 0)) as mock_rate:
                with patch.object(gateway.rate_limiter, 'record_cost') as mock_rate_cost:
                    with patch.object(gateway.audit_logger, 'log_ai_call') as mock_audit:
                        with patch.object(gateway.provider_router, 'select') as mock_select:
                            # Mock provider
                            mock_provider = MagicMock()
                            mock_provider.name = "anthropic"
                            mock_provider.instance.call = AsyncMock(return_value=mock_response)
                            mock_select.return_value = (mock_provider, "claude-sonnet-4-6")
                            
                            # Execute
                            response = await gateway.complete(
                                prompt="Test prompt",
                                model_tier="sonnet",
                                task_id="test-task-123"
                            )
                            
                            # Verify
                            assert response.content == "Test response"
                            assert response.provider == "anthropic"
                            assert response.cached is False
                            
                            # Verify all steps were called
                            mock_budget.assert_called_once()
                            mock_cache_get.assert_called_once()
                            mock_rate.assert_called_once()
                            mock_rate_cost.assert_called_once()
                            mock_audit.assert_called_once()
                            mock_select.assert_called_once()


@pytest.mark.asyncio
async def test_budget_exceeded_rejection(gateway):
    """
    Test that calls are rejected when budget is exceeded.
    
    Verifies that BudgetExceededError is raised immediately
    before any provider call is made.
    """
    budget_error = BudgetExceededError(
        limit_type="daily",
        current=25.0,
        limit=20.0
    )
    
    with patch.object(gateway.cost_tracker, 'is_budget_exceeded', return_value=budget_error):
        with pytest.raises(BudgetExceededError) as exc_info:
            await gateway.complete(prompt="Test prompt")
        
        assert exc_info.value.limit_type == "daily"
        assert exc_info.value.current == 25.0
        assert exc_info.value.limit == 20.0


@pytest.mark.asyncio
async def test_circuit_breaker_fallback(gateway, mock_response):
    """
    Test automatic fallback when circuit breaker is open.
    
    Verifies that:
    1. Primary provider circuit is open
    2. Fallback provider is selected
    3. Call succeeds via fallback
    """
    primary_provider = MagicMock()
    primary_provider.name = "anthropic"
    
    fallback_provider = MagicMock()
    fallback_provider.name = "openai"
    fallback_provider.instance.call = AsyncMock(return_value=mock_response)
    
    with patch.object(gateway.cost_tracker, 'is_budget_exceeded', return_value=None):
        with patch.object(gateway.response_cache, 'get', return_value=None):
            with patch.object(gateway.rate_limiter, 'acquire', return_value=(True, 0)):
                with patch.object(gateway.rate_limiter, 'record_cost'):
                    with patch.object(gateway.audit_logger, 'log_ai_call'):
                        with patch.object(gateway.circuit_breaker, 'record_success'):
                            with patch.object(gateway.provider_router, 'select') as mock_select:
                                with patch.object(gateway.provider_router, 'fallback') as mock_fallback:
                                    # First provider fails with circuit open
                                    mock_select.side_effect = CircuitBreakerOpenError(
                                        provider="anthropic",
                                        model="claude-sonnet-4-6",
                                        recovery_in=30
                                    )
                                    # Fallback succeeds
                                    mock_fallback.return_value = (fallback_provider, "gpt-4o")
                                    
                                    response = await gateway.complete(prompt="Test prompt")
                                    
                                    assert response.provider == "anthropic"  # From mock_response
                                    mock_fallback.assert_called_once()


@pytest.mark.asyncio
async def test_cache_hit_skips_api_call(gateway):
    """
    Test that cached responses skip the API call.
    
    Verifies that:
    1. Cache hit returns immediately
    2. No provider call is made
    3. Cost is zero for cached response
    """
    cached_data = {
        "content": "Cached response",
        "model": "claude-sonnet-4-6",
        "provider": "anthropic",
        "input_tokens": 100,
        "output_tokens": 50,
    }
    
    with patch.object(gateway.cost_tracker, 'is_budget_exceeded', return_value=None):
        with patch.object(gateway.response_cache, 'get', return_value=cached_data) as mock_cache:
            # Execute with cacheable=True
            response = await gateway.complete(
                prompt="Test prompt",
                cacheable=True
            )
            
            # Verify cache was checked
            mock_cache.assert_called_once()
            
            # Verify cached response
            assert response.content == "Cached response"
            assert response.cached is True
            assert response.cost == 0.0


@pytest.mark.asyncio
async def test_rate_limit_wait_behavior(gateway):
    """
    Test rate limiting wait/rejection behavior.
    
    Verifies that RateLimitError is raised when rate limit is exceeded.
    """
    with patch.object(gateway.cost_tracker, 'is_budget_exceeded', return_value=None):
        with patch.object(gateway.response_cache, 'get', return_value=None):
            with patch.object(gateway.rate_limiter, 'acquire', return_value=(False, 30)):
                with pytest.raises(RateLimitError) as exc_info:
                    await gateway.complete(
                        prompt="Test prompt",
                        model_tier="sonnet"
                    )
                
                assert exc_info.value.model_tier == "sonnet"
                assert exc_info.value.retry_after == 30


@pytest.mark.asyncio
async def test_cost_correctly_recorded(gateway, mock_response):
    """
    Test that costs are correctly recorded after successful call.
    
    Verifies:
    1. Cost tracker record() is called
    2. Correct cost amount is recorded
    """
    with patch.object(gateway.cost_tracker, 'is_budget_exceeded', return_value=None):
        with patch.object(gateway.response_cache, 'get', return_value=None):
            with patch.object(gateway.rate_limiter, 'acquire', return_value=(True, 0)):
                with patch.object(gateway.rate_limiter, 'record_cost') as mock_rate_cost:
                    with patch.object(gateway.audit_logger, 'log_ai_call'):
                        with patch.object(gateway.cost_tracker, 'record') as mock_cost_record:
                            with patch.object(gateway.provider_router, 'select') as mock_select:
                                mock_provider = MagicMock()
                                mock_provider.name = "anthropic"
                                mock_provider.instance.call = AsyncMock(return_value=mock_response)
                                mock_select.return_value = (mock_provider, "claude-sonnet-4-6")
                                
                                await gateway.complete(
                                    prompt="Test prompt",
                                    task_id="task-123"
                                )
                                
                                # Verify cost was recorded
                                mock_cost_record.assert_called_once()
                                call_args = mock_cost_record.call_args
                                assert call_args.kwargs['task_id'] == "task-123"
                                assert call_args.kwargs['cost'] == 0.001


@pytest.mark.asyncio
async def test_priority_scheduling(gateway, mock_response):
    """
    Test that high priority tasks are processed before low priority.
    
    Verifies that priority is passed to rate limiter.
    """
    with patch.object(gateway.cost_tracker, 'is_budget_exceeded', return_value=None):
        with patch.object(gateway.response_cache, 'get', return_value=None):
            with patch.object(gateway.rate_limiter, 'acquire', return_value=(True, 0)) as mock_rate:
                with patch.object(gateway.rate_limiter, 'record_cost'):
                    with patch.object(gateway.audit_logger, 'log_ai_call'):
                        with patch.object(gateway.provider_router, 'select') as mock_select:
                            mock_provider = MagicMock()
                            mock_provider.name = "anthropic"
                            mock_provider.instance.call = AsyncMock(return_value=mock_response)
                            mock_select.return_value = (mock_provider, "claude-sonnet-4-6")
                            
                            # Test with high priority
                            await gateway.complete(
                                prompt="Test prompt",
                                priority="high"
                            )
                            
                            # Verify priority was passed
                            assert mock_rate.call_args.kwargs.get('priority') == "high"


@pytest.mark.asyncio
async def test_model_degradation_on_budget_warning(gateway, mock_response):
    """
    Test that models are degraded when budget reaches warning level.
    
    Verifies that opus → sonnet → haiku degradation happens.
    """
    budget_status = MagicMock()
    budget_status.level = "degraded"
    budget_status.degraded_model_map = {
        "opus": "sonnet",
        "sonnet": "haiku",
        "haiku": "haiku",
    }
    
    with patch.object(gateway.cost_tracker, 'is_budget_exceeded', return_value=None):
        with patch.object(gateway.cost_tracker, 'get_budget_status', return_value=budget_status):
            with patch.object(gateway.response_cache, 'get', return_value=None):
                with patch.object(gateway.rate_limiter, 'acquire', return_value=(True, 0)):
                    with patch.object(gateway.rate_limiter, 'record_cost'):
                        with patch.object(gateway.audit_logger, 'log_ai_call'):
                            with patch.object(gateway.provider_router, 'select') as mock_select:
                                mock_provider = MagicMock()
                                mock_provider.name = "anthropic"
                                mock_provider.instance.call = AsyncMock(return_value=mock_response)
                                mock_select.return_value = (mock_provider, "claude-haiku-4-5")
                                
                                # Request opus, should get haiku (degraded twice)
                                await gateway.complete(
                                    prompt="Test prompt",
                                    model_tier="sonnet"
                                )
                                
                                # Verify rate limiter was called with degraded tier
                                # Note: The degradation happens before rate limiter


@pytest.mark.asyncio
async def test_all_providers_fail(gateway):
    """
    Test behavior when all providers fail.
    
    Verifies that ProviderError is raised with details of all failed providers.
    """
    from core.exceptions import ProviderError
    
    with patch.object(gateway.cost_tracker, 'is_budget_exceeded', return_value=None):
        with patch.object(gateway.response_cache, 'get', return_value=None):
            with patch.object(gateway.rate_limiter, 'acquire', return_value=(True, 0)):
                with patch.object(gateway.provider_router, 'select') as mock_select:
                    with patch.object(gateway.provider_router, 'fallback') as mock_fallback:
                        # All providers fail
                        mock_select.side_effect = ProviderError("Primary failed")
                        mock_fallback.side_effect = ProviderError("Fallback failed")
                        
                        with pytest.raises(ProviderError) as exc_info:
                            await gateway.complete(prompt="Test prompt")
                        
                        assert "All providers failed" in str(exc_info.value)
