"""
Base Provider Interface for AI Gateway
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any


@dataclass
class AIResponse:
    """Standardized AI response format"""
    content: str
    model: str
    provider: str
    input_tokens: int
    output_tokens: int
    cost: float
    latency_ms: int
    cached: bool = False


class BaseProvider(ABC):
    """Abstract base class for AI providers"""
    
    def __init__(self, api_key: str, config: dict = None):
        self.api_key = api_key
        self.config = config or {}
    
    @abstractmethod
    async def call(
        self,
        prompt: str,
        system: str = "",
        temperature: float = 0.3,
        max_tokens: int = 4096,
        tools: list = None
    ) -> AIResponse:
        """
        Make an AI completion call
        
        Args:
            prompt: The user prompt
            system: System message/instructions
            temperature: Sampling temperature (0-1)
            max_tokens: Maximum tokens to generate
            tools: Optional list of tool definitions
            
        Returns:
            AIResponse with standardized format
        """
        pass
    
    @abstractmethod
    def calculate_cost(self, input_tokens: int, output_tokens: int, model: str) -> float:
        """
        Calculate the cost of an API call
        
        Args:
            input_tokens: Number of input tokens
            output_tokens: Number of output tokens
            model: Model name
            
        Returns:
            Cost in USD
        """
        pass
    
    @property
    @abstractmethod
    def name(self) -> str:
        """Provider name"""
        pass
    
    @property
    @abstractmethod
    def priority(self) -> int:
        """Provider priority (lower = higher priority)"""
        pass
