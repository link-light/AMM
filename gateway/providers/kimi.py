"""
Kimi (Moonshot AI) Provider
API Documentation: https://platform.moonshot.cn/docs
"""

import logging

from gateway.providers.openai_compatible import OpenAICompatibleProvider

logger = logging.getLogger(__name__)


class KimiProvider(OpenAICompatibleProvider):
    """
    Kimi (Moonshot AI) Provider
    完全兼容 OpenAI API 格式
    """
    
    DEFAULT_CONFIG = {
        "base_url": "https://api.moonshot.cn/v1",
        "models": {
            "opus": "moonshot-v1-128k",      # 最强模型，支持 128k 上下文
            "sonnet": "moonshot-v1-32k",     # 中等模型，支持 32k 上下文
            "haiku": "moonshot-v1-8k"        # 轻量模型，支持 8k 上下文
        },
        "timeout": 120  # Kimi 长上下文可能较慢
    }
    
    # 定价 (美元/1M tokens)
    # 汇率按 1 USD = 7.2 CNY 估算
    # moonshot-v1-8k:   input ¥12/M, output ¥12/M  → $1.67/M
    # moonshot-v1-32k:  input ¥24/M, output ¥24/M  → $3.33/M
    # moonshot-v1-128k: input ¥60/M, output ¥60/M  → $8.33/M
    PRICING = {
        "moonshot-v1-8k":   {"input": 1.67, "output": 1.67},
        "moonshot-v1-32k":  {"input": 3.33, "output": 3.33},
        "moonshot-v1-128k": {"input": 8.33, "output": 8.33}
    }
    
    def __init__(self, api_key: str = None, config: dict = None):
        """
        Initialize Kimi Provider
        
        Args:
            api_key: Kimi API key (from https://platform.moonshot.cn/)
            config: Additional configuration
        """
        # Load from settings if no api_key provided
        if api_key is None:
            from core.config import settings
            api_key = getattr(settings.ai_gateway, 'kimi_api_key', '')
        
        super().__init__(api_key, config)
        
        if not self.api_key:
            logger.warning("Kimi API key not provided")
    
    @property
    def name(self) -> str:
        return "kimi"
    
    @property
    def priority(self) -> int:
        return 1  # Highest priority for testing
    
    def _get_model_name(self, model_tier: str) -> str:
        """
        Get Kimi model name for tier
        
        Kimi model mapping:
        - opus: moonshot-v1-128k (128k context, strongest)
        - sonnet: moonshot-v1-32k (32k context, balanced)
        - haiku: moonshot-v1-8k (8k context, fastest)
        """
        return self.models.get(model_tier, "moonshot-v1-32k")
