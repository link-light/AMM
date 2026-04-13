"""
DeepSeek Provider
API Documentation: https://platform.deepseek.com/api-docs
"""

import logging

from gateway.providers.openai_compatible import OpenAICompatibleProvider

logger = logging.getLogger(__name__)


class DeepSeekProvider(OpenAICompatibleProvider):
    """
    DeepSeek Provider
    完全兼容 OpenAI API 格式
    
    DeepSeek 特点：
    - 只有一个主力模型 deepseek-chat (V3)
    - 价格非常便宜
    - 支持缓存命中计费
    """
    
    DEFAULT_CONFIG = {
        "base_url": "https://api.deepseek.com",
        "models": {
            "opus": "deepseek-chat",      # DeepSeek-V3 最强版本
            "sonnet": "deepseek-chat",    # 同一模型
            "haiku": "deepseek-chat"      # 同一模型，靠 max_tokens 控制
        },
        "timeout": 60
    }
    
    # 定价 (美元/1M tokens)
    # deepseek-chat: input $0.27/M, output $1.10/M (缓存命中 $0.07/M)
    # deepseek-reasoner: input $0.55/M, output $2.19/M
    PRICING = {
        "deepseek-chat":     {"input": 0.27, "output": 1.10},
        "deepseek-reasoner": {"input": 0.55, "output": 2.19}
    }
    
    def __init__(self, api_key: str = None, config: dict = None):
        """
        Initialize DeepSeek Provider
        
        Args:
            api_key: DeepSeek API key (from https://platform.deepseek.com/)
            config: Additional configuration
        """
        # Load from settings if no api_key provided
        if api_key is None:
            from core.config import settings
            api_key = getattr(settings.ai_gateway, 'deepseek_api_key', '')
        
        super().__init__(api_key, config)
        
        if not self.api_key:
            logger.warning("DeepSeek API key not provided")
    
    @property
    def name(self) -> str:
        return "deepseek"
    
    @property
    def priority(self) -> int:
        return 2  # Second priority after Kimi
    
    def _get_model_name(self, model_tier: str) -> str:
        """
        Get DeepSeek model name for tier
        
        DeepSeek 只有一个主力模型 deepseek-chat，
        三个 tier 都映射到同一个模型，通过 temperature 和 max_tokens 区分行为
        """
        return self.models.get(model_tier, "deepseek-chat")
    
    def calculate_cost(self, input_tokens: int, output_tokens: int, model: str) -> float:
        """
        Calculate cost with DeepSeek pricing
        
        Note: DeepSeek has cache hit pricing ($0.07/M) but we can't
        determine cache hits from token counts alone, so we use
        standard pricing.
        """
        return super().calculate_cost(input_tokens, output_tokens, model)
