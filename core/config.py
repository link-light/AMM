"""
AMM Configuration - Centralized settings management using Pydantic Settings
"""

from functools import lru_cache
from typing import Optional

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class DatabaseConfig(BaseSettings):
    """Database configuration"""
    model_config = SettingsConfigDict(env_prefix="DB_")
    
    user: str = "amm"
    password: str = "ammpass"
    name: str = "amm"
    host: str = "localhost"
    port: int = 5432
    
    @property
    def url(self) -> str:
        url = f"postgresql+asyncpg://{self.user}:{self.password}@{self.host}:{self.port}/{self.name}"
        # Check if SQLite is configured
        import os
        if os.environ.get('DATABASE_URL', '').startswith('sqlite'):
            return os.environ['DATABASE_URL']
        return url


class RedisConfig(BaseSettings):
    """Redis configuration"""
    model_config = SettingsConfigDict(env_prefix="REDIS_")
    
    host: str = "localhost"
    port: int = 6379
    db: int = 0
    
    @property
    def url(self) -> str:
        return f"redis://{self.host}:{self.port}/{self.db}"


class AIGatewayConfig(BaseSettings):
    """AI Gateway configuration including budget and rate limiting"""
    
    # API Keys
    anthropic_api_key: str = Field(default="", alias="ANTHROPIC_API_KEY")
    openai_api_key: str = Field(default="", alias="OPENAI_API_KEY")
    deepseek_api_key: str = Field(default="", alias="DEEPSEEK_API_KEY")
    
    # Budget Hard Limits ($)
    daily_hard_limit: float = Field(default=20.0, alias="DAILY_HARD_LIMIT")
    monthly_hard_limit: float = Field(default=400.0, alias="MONTHLY_HARD_LIMIT")
    per_task_limit: float = Field(default=5.0, alias="PER_TASK_LIMIT")
    
    # Budget Soft Limits ($)
    daily_soft_limit: float = Field(default=15.0, alias="DAILY_SOFT_LIMIT")
    monthly_soft_limit: float = Field(default=300.0, alias="MONTHLY_SOFT_LIMIT")
    
    # Minimum profit ratio
    min_profit_ratio: float = Field(default=3.0, alias="MIN_PROFIT_RATIO")
    
    # Rate Limits - Opus tier
    opus_rpm: int = Field(default=30, alias="OPUS_RPM")
    opus_tpm: int = Field(default=100000, alias="OPUS_TPM")
    opus_daily_cost: float = Field(default=50.0, alias="OPUS_DAILY_COST")
    
    # Rate Limits - Sonnet tier
    sonnet_rpm: int = Field(default=60, alias="SONNET_RPM")
    sonnet_tpm: int = Field(default=200000, alias="SONNET_TPM")
    sonnet_daily_cost: float = Field(default=30.0, alias="SONNET_DAILY_COST")
    
    # Rate Limits - Haiku tier
    haiku_rpm: int = Field(default=120, alias="HAIKU_RPM")
    haiku_tpm: int = Field(default=500000, alias="HAIKU_TPM")
    haiku_daily_cost: float = Field(default=10.0, alias="HAIKU_DAILY_COST")
    
    # Circuit Breaker
    circuit_failure_threshold: int = Field(default=5, alias="CIRCUIT_FAILURE_THRESHOLD")
    circuit_recovery_timeout: int = Field(default=60, alias="CIRCUIT_RECOVERY_TIMEOUT")
    circuit_half_open_max_calls: int = Field(default=3, alias="CIRCUIT_HALF_OPEN_MAX_CALLS")
    
    # Cache
    cache_ttl: int = Field(default=3600, alias="CACHE_TTL")
    cache_max_size: int = Field(default=10000, alias="CACHE_MAX_SIZE")
    
    # Mock Mode
    mock_ai: bool = Field(default=True, alias="MOCK_AI")
    mock_scouts: bool = Field(default=True, alias="MOCK_SCOUTS")
    
    # Cost pricing ($ per 1M tokens) - use class variable
    model_config = SettingsConfigDict(env_prefix="", extra="ignore")
    
    @property
    def PRICING(self) -> dict:
        return {
            "anthropic": {
                "opus": {"input": 15.0, "output": 75.0},
                "sonnet": {"input": 3.0, "output": 15.0},
                "haiku": {"input": 0.80, "output": 4.0},
            },
            "openai": {
                "gpt-4o": {"input": 5.0, "output": 15.0},
                "gpt-4o-mini": {"input": 0.15, "output": 0.60},
            },
            "deepseek": {
                "deepseek-chat": {"input": 0.5, "output": 2.0},
            }
        }
    
    # Model mapping by tier
    @property
    def MODEL_MAPPING(self) -> dict:
        return {
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


class AppConfig(BaseSettings):
    """Application configuration"""
    
    environment: str = Field(default="development", alias="ENVIRONMENT")
    debug: bool = Field(default=True, alias="DEBUG")
    log_level: str = Field(default="INFO", alias="LOG_LEVEL")
    
    # JWT
    jwt_secret: str = Field(default="your-secret-key", alias="JWT_SECRET")
    jwt_algorithm: str = "HS256"
    jwt_expire_hours: int = 24
    
    # Admin
    admin_username: str = Field(default="admin", alias="ADMIN_USERNAME")
    admin_password: str = Field(default="admin123", alias="ADMIN_PASSWORD")
    
    # Feature flags
    enable_audit_log: bool = Field(default=True, alias="ENABLE_AUDIT_LOG")
    enable_cost_tracking: bool = Field(default=True, alias="ENABLE_COST_TRACKING")
    enable_circuit_breaker: bool = Field(default=True, alias="ENABLE_CIRCUIT_BREAKER")
    
    # Scout intervals (seconds)
    freelance_scout_interval: int = Field(default=1800, alias="FREELANCE_SCOUT_INTERVAL")


class Settings(BaseSettings):
    """Main settings class aggregating all configurations"""
    
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )
    
    # Sub-configurations
    database: DatabaseConfig = DatabaseConfig()
    redis: RedisConfig = RedisConfig()
    ai_gateway: AIGatewayConfig = AIGatewayConfig()
    app: AppConfig = AppConfig()
    
    # Direct database URL override
    database_url: Optional[str] = Field(default=None, alias="DATABASE_URL")
    
    # Direct Redis URL override
    redis_url: Optional[str] = Field(default=None, alias="REDIS_URL")
    
    @property
    def db_url(self) -> str:
        return self.database_url or self.database.url
    
    @property
    def redis_connection_url(self) -> str:
        return self.redis_url or self.redis.url


@lru_cache()
def get_settings() -> Settings:
    """Get cached settings instance"""
    return Settings()


# Global settings instance
settings = get_settings()
