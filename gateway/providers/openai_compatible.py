"""
OpenAI Compatible Provider Base Class
Supports all providers using OpenAI chat/completions API format
"""

import time
import logging
from typing import Any

import httpx

from gateway.providers.base import AIResponse, BaseProvider
from core.exceptions import ProviderError, RateLimitError, BudgetExceededError

logger = logging.getLogger(__name__)


class OpenAICompatibleProvider(BaseProvider):
    """
    OpenAI 兼容 API 的通用 Provider
    支持所有使用 OpenAI chat/completions 格式的供应商
    """
    
    # Provider-specific configuration
    DEFAULT_CONFIG = {}
    PRICING = {}
    
    def __init__(self, api_key: str = None, config: dict = None):
        """
        Initialize OpenAI compatible provider
        
        Args:
            api_key: API key for the provider
            config: Additional configuration dict
        """
        super().__init__(api_key or "", config)
        
        # Merge default config with provided config
        merged_config = self.DEFAULT_CONFIG.copy()
        if config:
            merged_config.update(config)
        
        self.base_url = merged_config.get("base_url", "")
        self.timeout = merged_config.get("timeout", 60)
        self.models = merged_config.get("models", {})
        
        # Initialize HTTP client
        self.client = httpx.AsyncClient(
            timeout=self.timeout,
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json"
            }
        )
    
    def _get_model_name(self, model_tier: str) -> str:
        """Get actual model name for tier"""
        return self.models.get(model_tier, self.models.get("sonnet", "unknown"))
    
    async def call(
        self,
        prompt: str,
        system: str = "",
        temperature: float = 0.3,
        max_tokens: int = 4096,
        tools: list = None,
        model_tier: str = "sonnet"
    ) -> AIResponse:
        """
        调用 OpenAI 兼容的 chat/completions 端点
        
        Args:
            prompt: User prompt
            system: System message
            temperature: Sampling temperature (0-1)
            max_tokens: Maximum tokens to generate
            tools: Optional tool definitions for function calling
            model_tier: Model tier (opus/sonnet/haiku)
            
        Returns:
            AIResponse with standardized format
            
        Raises:
            ProviderError: For provider-related errors
            RateLimitError: For rate limit errors (429)
        """
        start_time = time.time()
        
        # Get model name for tier
        model = self._get_model_name(model_tier)
        
        # Build request body
        body = {
            "model": model,
            "messages": [
                {"role": "system", "content": system} if system else None,
                {"role": "user", "content": prompt}
            ],
            "temperature": temperature,
            "max_tokens": max_tokens
        }
        
        # Remove None from messages
        body["messages"] = [m for m in body["messages"] if m is not None]
        
        # Add tools if provided
        if tools:
            body["tools"] = tools
            body["tool_choice"] = "auto"
        
        try:
            response = await self.client.post(
                f"{self.base_url}/chat/completions",
                json=body
            )
            
            # Handle errors
            if response.status_code == 429:
                raise RateLimitError(f"{self.name} rate limit exceeded")
            elif response.status_code in (401, 403):
                raise ProviderError(f"{self.name} authentication failed", self.name)
            elif response.status_code >= 500:
                raise ProviderError(f"{self.name} server error: {response.status_code}", self.name)
            elif response.status_code != 200:
                raise ProviderError(
                    f"{self.name} API error: {response.status_code} - {response.text}", 
                    self.name
                )
            
            # Parse response
            data = response.json()
            
            # Extract content
            choice = data["choices"][0]
            message = choice["message"]
            
            # Handle tool calls or content
            if "tool_calls" in message and message["tool_calls"]:
                # Return tool calls as JSON string
                import json
                content = json.dumps(message["tool_calls"])
            else:
                content = message.get("content", "")
            
            # Extract usage
            usage = data.get("usage", {})
            input_tokens = usage.get("prompt_tokens", 0)
            output_tokens = usage.get("completion_tokens", 0)
            
            # Calculate cost
            cost = self.calculate_cost(input_tokens, output_tokens, model)
            
            # Calculate latency
            latency_ms = int((time.time() - start_time) * 1000)
            
            return AIResponse(
                content=content,
                model=model,
                provider=self.name,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                cost=cost,
                latency_ms=latency_ms,
                cached=False
            )
            
        except httpx.TimeoutException as e:
            raise ProviderError(f"{self.name} request timeout", self.name) from e
        except httpx.NetworkError as e:
            raise ProviderError(f"{self.name} network error", self.name) from e
        except (KeyError, IndexError) as e:
            raise ProviderError(f"{self.name} invalid response format", self.name) from e
        except Exception as e:
            if isinstance(e, (ProviderError, RateLimitError)):
                raise
            raise ProviderError(f"{self.name} unexpected error: {str(e)}", self.name) from e
    
    def calculate_cost(self, input_tokens: int, output_tokens: int, model: str) -> float:
        """
        根据定价表计算成本
        
        Args:
            input_tokens: Number of input tokens
            output_tokens: Number of output tokens
            model: Model name
            
        Returns:
            Cost in USD
        """
        pricing = self.PRICING.get(model, {"input": 1.0, "output": 2.0})
        
        input_cost = (input_tokens / 1_000_000) * pricing["input"]
        output_cost = (output_tokens / 1_000_000) * pricing["output"]
        
        return round(input_cost + output_cost, 6)
    
    async def close(self):
        """Close HTTP client"""
        await self.client.aclose()
