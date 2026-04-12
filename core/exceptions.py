"""
AMM Custom Exceptions
"""


class AMMError(Exception):
    """Base exception for AMM"""
    pass


class BudgetExceededError(AMMError):
    """Raised when AI cost budget is exceeded"""
    
    def __init__(self, message: str = "Budget limit exceeded", 
                 limit_type: str = "daily", 
                 current: float = 0.0, 
                 limit: float = 0.0):
        self.limit_type = limit_type
        self.current = current
        self.limit = limit
        super().__init__(f"{message} ({limit_type}: ${current:.2f} / ${limit:.2f})")


class RateLimitError(AMMError):
    """Raised when rate limit is exceeded"""
    
    def __init__(self, message: str = "Rate limit exceeded",
                 model_tier: str = "",
                 retry_after: int = 0):
        self.model_tier = model_tier
        self.retry_after = retry_after
        super().__init__(f"{message} for {model_tier}. Retry after {retry_after}s")


class CircuitBreakerOpenError(AMMError):
    """Raised when circuit breaker is open"""
    
    def __init__(self, message: str = "Circuit breaker is open",
                 provider: str = "",
                 model: str = "",
                 recovery_in: int = 0):
        self.provider = provider
        self.model = model
        self.recovery_in = recovery_in
        super().__init__(f"{message}: {provider}/{model}. Recovery in {recovery_in}s")


class ProviderError(AMMError):
    """Raised when AI provider API fails"""
    
    def __init__(self, message: str = "Provider API error",
                 provider: str = "",
                 status_code: int = 0,
                 response: str = ""):
        self.provider = provider
        self.status_code = status_code
        self.response = response
        super().__init__(f"{message} from {provider}: {status_code} - {response}")


class ComplianceError(AMMError):
    """Raised when operation violates compliance rules"""
    
    def __init__(self, message: str = "Compliance violation",
                 rule: str = "",
                 details: dict = None):
        self.rule = rule
        self.details = details or {}
        super().__init__(f"{message}: {rule}")


class TaskTimeoutError(AMMError):
    """Raised when task execution times out"""
    
    def __init__(self, message: str = "Task timed out",
                 task_id: str = "",
                 timeout: int = 0):
        self.task_id = task_id
        self.timeout = timeout
        super().__init__(f"{message}: {task_id} after {timeout}s")


class ValidationError(AMMError):
    """Raised when data validation fails"""
    pass


class NotFoundError(AMMError):
    """Raised when requested resource is not found"""
    pass


class AuthenticationError(AMMError):
    """Raised when authentication fails"""
    pass


class AuthorizationError(AMMError):
    """Raised when user is not authorized"""
    pass
