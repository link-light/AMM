"""
OpenAI Provider Adapter (Phase 1 Skeleton)
"""

from gateway.providers.base import AIResponse, BaseProvider


class OpenAIProvider(BaseProvider):
    """OpenAI API provider - Phase 1 Skeleton"""
    
    def __init__(self, api_key: str = None, config: dict = None):
        from core.config import settings
        super().__init__(
            api_key=api_key or settings.ai_gateway.openai_api_key,
            config=config
        )
    
    @property
    def name(self) -> str:
        return "openai"
    
    @property
    def priority(self) -> int:
        return 2  # Second priority
    
    def calculate_cost(self, input_tokens: int, output_tokens: int, model: str) -> float:
        """Calculate cost in USD"""
        # Phase 1: Return dummy cost
        # TODO: Implement real pricing
        pricing = {
            "gpt-4o": {"input": 5.0, "output": 15.0},
            "gpt-4o-mini": {"input": 0.15, "output": 0.60},
        }
        p = pricing.get(model, pricing["gpt-4o-mini"])
        input_cost = (input_tokens / 1_000_000) * p["input"]
        output_cost = (output_tokens / 1_000_000) * p["output"]
        return round(input_cost + output_cost, 6)
    
    async def call(
        self,
        prompt: str,
        system: str = "",
        temperature: float = 0.3,
        max_tokens: int = 4096,
        tools: list = None,
        model_tier: str = "sonnet"
    ) -> AIResponse:
        """Make an AI completion call - Not implemented in Phase 1"""
        raise NotImplementedError(
            "OpenAI provider is not implemented in Phase 1. "
            "Use Anthropic provider instead."
        )
