"""
Anthropic Provider Adapter
"""

import asyncio
import logging
import random
from datetime import datetime

import httpx

from core.config import settings
from core.exceptions import ProviderError
from gateway.providers.base import AIResponse, BaseProvider

logger = logging.getLogger(__name__)

# Pricing per 1M tokens
PRICING = {
    "claude-opus-4-6": {"input": 15.0, "output": 75.0},
    "claude-sonnet-4-6": {"input": 3.0, "output": 15.0},
    "claude-haiku-4-5": {"input": 0.80, "output": 4.0},
}

# Model mapping from tier to actual model name
MODEL_MAPPING = {
    "opus": "claude-opus-4-6",
    "sonnet": "claude-sonnet-4-6",
    "haiku": "claude-haiku-4-5",
}


class AnthropicProvider(BaseProvider):
    """Anthropic Claude API provider"""
    
    API_BASE = "https://api.anthropic.com/v1"
    
    def __init__(self, api_key: str = None, config: dict = None):
        super().__init__(
            api_key=api_key or settings.ai_gateway.anthropic_api_key,
            config=config
        )
        self.mock_mode = settings.ai_gateway.mock_ai
        self.client = httpx.AsyncClient(
            base_url=self.API_BASE,
            headers={
                "x-api-key": self.api_key,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            },
            timeout=60.0,
        )
    
    @property
    def name(self) -> str:
        return "anthropic"
    
    @property
    def priority(self) -> int:
        return 1  # Highest priority
    
    def _get_model_name(self, model_tier: str) -> str:
        """Get actual model name from tier"""
        return MODEL_MAPPING.get(model_tier, "claude-sonnet-4-6")
    
    def calculate_cost(self, input_tokens: int, output_tokens: int, model: str) -> float:
        """Calculate cost in USD"""
        pricing = PRICING.get(model, PRICING["claude-sonnet-4-6"])
        input_cost = (input_tokens / 1_000_000) * pricing["input"]
        output_cost = (output_tokens / 1_000_000) * pricing["output"]
        return round(input_cost + output_cost, 6)
    
    def _estimate_tokens(self, text: str) -> int:
        """Rough token estimation (1 token ≈ 4 chars for English)"""
        return len(text) // 4
    
    def _generate_mock_response(self, prompt: str, model: str) -> AIResponse:
        """Generate mock response for testing"""
        import time
        
        start_time = time.time()
        
        # Simulate latency (0.5-2 seconds)
        latency_ms = random.randint(500, 2000)
        
        # Estimate tokens
        input_tokens = self._estimate_tokens(prompt) + self._estimate_tokens("")
        output_tokens = random.randint(100, 500)
        
        # Generate context-aware mock response
        prompt_lower = prompt.lower()
        
        if "evaluate" in prompt_lower or "评估" in prompt:
            content = '''{
  "scores": {
    "revenue_potential": 75,
    "execution_difficulty": 60,
    "time_cost": 80,
    "success_probability": 70,
    "strategic_value": 65,
    "compliance_risk": 90
  },
  "total_score": 73,
  "decision": "accepted",
  "reasoning": "This is a moderate opportunity with good revenue potential and manageable complexity.",
  "estimated_ai_cost": 0.15,
  "suggested_price": 600,
  "risk_factors": ["Client has no payment history", "Requirements may expand"],
  "recommended_skills": ["python", "automation"],
  "execution_plan_summary": "Build a Python CLI tool with data processing capabilities"
}'''
        elif "code" in prompt_lower or "生成" in prompt_lower:
            content = '''Here is the generated code:

```python
# main.py
def main():
    print("Hello, World!")
    
if __name__ == "__main__":
    main()
```

This code provides a basic structure that can be expanded based on requirements.'''
        elif "analyze" in prompt_lower:
            content = '''## Analysis Summary

Based on the provided requirements:

1. **Complexity**: Medium
2. **Estimated Time**: 3-5 days
3. **Key Challenges**: Data validation, error handling
4. **Recommended Approach**: Agile iteration with client feedback

The project is feasible within the proposed timeline.'''
        else:
            content = f'''This is a mock response from {model}.

The prompt was received and processed successfully. In production mode, this would be a real response from the Anthropic API.

Mock responses are useful for:
- Development and testing
- Cost estimation
- Integration testing
- Workflow validation'''
        
        output_tokens = self._estimate_tokens(content)
        cost = self.calculate_cost(input_tokens, output_tokens, model)
        
        return AIResponse(
            content=content,
            model=model,
            provider="anthropic",
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cost=cost,
            latency_ms=latency_ms,
            cached=False,
        )
    
    async def call(
        self,
        prompt: str,
        system: str = "",
        temperature: float = 0.3,
        max_tokens: int = 4096,
        tools: list = None,
        model_tier: str = "sonnet"
    ) -> AIResponse:
        """Make an AI completion call to Anthropic"""
        
        if self.mock_mode:
            logger.info(f"[MOCK] Anthropic call with tier={model_tier}")
            model = self._get_model_name(model_tier)
            return self._generate_mock_response(prompt, model)
        
        model = self._get_model_name(model_tier)
        
        # Build messages
        messages = [{"role": "user", "content": prompt}]
        
        payload = {
            "model": model,
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
        }
        
        if system:
            payload["system"] = system
        
        if tools:
            payload["tools"] = tools
        
        import time
        start_time = time.time()
        
        try:
            response = await self.client.post("/messages", json=payload)
            response.raise_for_status()
            data = response.json()
            
            latency_ms = int((time.time() - start_time) * 1000)
            
            # Extract usage
            usage = data.get("usage", {})
            input_tokens = usage.get("input_tokens", 0)
            output_tokens = usage.get("output_tokens", 0)
            
            # Extract content
            content_blocks = data.get("content", [])
            content = ""
            for block in content_blocks:
                if block.get("type") == "text":
                    content += block.get("text", "")
            
            cost = self.calculate_cost(input_tokens, output_tokens, model)
            
            logger.debug(f"Anthropic call completed: {input_tokens} in, {output_tokens} out, ${cost:.6f}")
            
            return AIResponse(
                content=content,
                model=model,
                provider="anthropic",
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                cost=cost,
                latency_ms=latency_ms,
                cached=False,
            )
            
        except httpx.HTTPStatusError as e:
            logger.error(f"Anthropic API error: {e.response.status_code} - {e.response.text}")
            raise ProviderError(
                message="Anthropic API error",
                provider="anthropic",
                status_code=e.response.status_code,
                response=e.response.text
            )
        except Exception as e:
            logger.error(f"Unexpected error calling Anthropic: {e}")
            raise ProviderError(
                message=f"Unexpected error: {str(e)}",
                provider="anthropic"
            )
    
    async def close(self):
        """Close HTTP client"""
        await self.client.aclose()
