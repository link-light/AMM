"""
DeepSeek Provider Adapter (Phase 1 Skeleton)
"""

from gateway.providers.base import AIResponse, BaseProvider


class DeepSeekProvider(BaseProvider):
    """DeepSeek API provider - Phase 1 Skeleton"""
    
    def __init__(self, api_key: str = None, config: dict = None):
        from core.config import settings
        super().__init__(
            api_key=api_key or settings.ai_gateway.deepseek_api_key,
            config=config
        )
    
    @property
    def name(self) -> str:
        return "deepseek"
    
    @property
    def priority(self) -> int:
        return 3  # Third priority
    
    def calculate_cost(self, input_tokens: int, output_tokens: int, model: str) -> float:
        """Calculate cost in USD"""
        # Phase 1: Return dummy cost
        # TODO: Implement real pricing
        pricing = {
            "deepseek-chat": {"input": 0.5, "output": 2.0},
        }
        p = pricing.get(model, pricing["deepseek-chat"])
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
            "DeepSeek provider is not implemented in Phase 1. "
            "Use Anthropic provider instead."
        )
