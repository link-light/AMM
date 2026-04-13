"""
Multi-Provider Router for AI Gateway
Routes requests to available providers with fallback support
"""

import logging
from dataclasses import dataclass
from typing import Optional

from core.config import settings
from core.exceptions import ProviderError
from gateway.circuit_breaker import CircuitBreaker
from gateway.providers.anthropic import AnthropicProvider
from gateway.providers.base import BaseProvider
from gateway.providers.deepseek import DeepSeekProvider
from gateway.providers.openai import OpenAIProvider

logger = logging.getLogger(__name__)

# Provider configuration
PROVIDER_CONFIG = {
    "anthropic": {"priority": 1, "enabled": True},
    "openai": {"priority": 2, "enabled": False},  # Phase 1: disabled
    "deepseek": {"priority": 3, "enabled": False},  # Phase 1: disabled
}

# Model mapping by tier
MODEL_MAPPING = {
    "opus": {
        "anthropic": "claude-opus-4-6",
        "openai": "gpt-4o",
        "deepseek": "deepseek-chat"
    },
    "sonnet": {
        "anthropic": "claude-sonnet-4-6",
        "openai": "gpt-4o-mini",
        "deepseek": "deepseek-chat"
    },
    "haiku": {
        "anthropic": "claude-haiku-4-5",
        "openai": "gpt-4o-mini",
        "deepseek": "deepseek-chat"
    }
}


@dataclass
class Provider:
    """Provider information"""
    name: str
    instance: BaseProvider
    priority: int
    available: bool


class ProviderRouter:
    """
    Routes AI requests to available providers
    
    Features:
    - Priority-based provider selection
    - Circuit breaker integration
    - Automatic fallback
    - Status monitoring
    """
    
    def __init__(self, circuit_breaker: CircuitBreaker = None):
        self.circuit_breaker = circuit_breaker or CircuitBreaker()
        self.providers: dict[str, Provider] = {}
        self._init_providers()
    
    def _init_providers(self):
        """Initialize provider instances"""
        config = settings.ai_gateway
        
        # Anthropic (Phase 1: primary)
        if PROVIDER_CONFIG["anthropic"]["enabled"]:
            try:
                instance = AnthropicProvider()
                self.providers["anthropic"] = Provider(
                    name="anthropic",
                    instance=instance,
                    priority=PROVIDER_CONFIG["anthropic"]["priority"],
                    available=bool(config.anthropic_api_key)
                )
                logger.info("Anthropic provider initialized")
            except Exception as e:
                logger.error(f"Failed to initialize Anthropic provider: {e}")
        
        # OpenAI (Phase 1: skeleton)
        if PROVIDER_CONFIG["openai"]["enabled"]:
            try:
                instance = OpenAIProvider()
                self.providers["openai"] = Provider(
                    name="openai",
                    instance=instance,
                    priority=PROVIDER_CONFIG["openai"]["priority"],
                    available=bool(config.openai_api_key)
                )
            except Exception as e:
                logger.error(f"Failed to initialize OpenAI provider: {e}")
        
        # DeepSeek (Phase 1: skeleton)
        if PROVIDER_CONFIG["deepseek"]["enabled"]:
            try:
                instance = DeepSeekProvider()
                self.providers["deepseek"] = Provider(
                    name="deepseek",
                    instance=instance,
                    priority=PROVIDER_CONFIG["deepseek"]["priority"],
                    available=bool(config.deepseek_api_key)
                )
            except Exception as e:
                logger.error(f"Failed to initialize DeepSeek provider: {e}")
    
    def _get_model_name(self, provider: str, model_tier: str) -> str:
        """Get actual model name for provider and tier"""
        return MODEL_MAPPING.get(model_tier, MODEL_MAPPING["sonnet"]).get(
            provider, "claude-sonnet-4-6"
        )
    
    async def select(self, model_tier: str = "sonnet") -> tuple[Provider, str]:
        """
        Select the best available provider for the model tier
        
        Returns:
            Tuple of (Provider, model_name)
        """
        # Sort providers by priority
        sorted_providers = sorted(
            self.providers.values(),
            key=lambda p: p.priority
        )
        
        for provider in sorted_providers:
            if not provider.available:
                continue
            
            model = self._get_model_name(provider.name, model_tier)
            
            # Check circuit breaker
            try:
                await self.circuit_breaker.check(provider.name, model)
                logger.debug(f"Selected provider: {provider.name}/{model}")
                return provider, model
            except Exception:
                logger.debug(f"Provider {provider.name} circuit open, trying next")
                continue
        
        raise ProviderError("No available providers for model tier", model_tier)
    
    async def fallback(self, model_tier: str, exclude_provider: str) -> tuple[Provider, str]:
        """
        Find fallback provider (different from current)
        
        Returns:
            Tuple of (Provider, model_name)
        """
        sorted_providers = sorted(
            self.providers.values(),
            key=lambda p: p.priority
        )
        
        for provider in sorted_providers:
            if not provider.available or provider.name == exclude_provider:
                continue
            
            model = self._get_model_name(provider.name, model_tier)
            
            try:
                await self.circuit_breaker.check(provider.name, model)
                logger.info(f"Fallback to provider: {provider.name}/{model}")
                return provider, model
            except Exception:
                continue
        
        raise ProviderError("No fallback provider available")
    
    async def get_status(self) -> dict:
        """Get status of all providers"""
        status = {}
        
        for name, provider in self.providers.items():
            provider_status = {
                "available": provider.available,
                "priority": provider.priority,
            }
            
            # Add circuit breaker status for each model
            provider_status["models"] = {}
            for tier in ["opus", "sonnet", "haiku"]:
                model = self._get_model_name(name, tier)
                try:
                    cb_state, cb_meta = await self.circuit_breaker.get_state(name, model)
                    provider_status["models"][model] = {
                        "tier": tier,
                        "circuit_state": cb_state.value,
                        **cb_meta
                    }
                except Exception as e:
                    provider_status["models"][model] = {
                        "tier": tier,
                        "error": str(e)
                    }
            
            status[name] = provider_status
        
        return status
    
    def get_provider(self, name: str) -> Optional[Provider]:
        """Get provider by name"""
        return self.providers.get(name)
