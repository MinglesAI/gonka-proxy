import time
import logging
from enum import Enum
from typing import Callable, Any, Optional
from functools import wraps

logger = logging.getLogger(__name__)

class CircuitState(Enum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"

class CircuitBreakerOpenError(Exception):
    pass

class CircuitBreaker:
    def __init__(self, name: str, failure_threshold: int = 5, recovery_timeout: float = 60.0, success_threshold: int = 2, expected_exception: type = Exception):
        self.name = name
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.success_threshold = success_threshold
        self.expected_exception = expected_exception
        self.failure_count = 0
        self.success_count = 0
        self.last_failure_time: Optional[float] = None
        self.state = CircuitState.CLOSED

    async def call(self, func: Callable, *args, **kwargs) -> Any:
        if self.state == CircuitState.OPEN:
            if self.last_failure_time and time.time() - self.last_failure_time > self.recovery_timeout:
                logger.info(f"Circuit breaker {self.name}: OPEN -> HALF_OPEN (testing recovery)")
                self.state = CircuitState.HALF_OPEN
                self.success_count = 0
            else:
                raise CircuitBreakerOpenError(f"Circuit breaker {self.name} is OPEN. Last failure: {self.last_failure_time}")
        try:
            result = await func(*args, **kwargs)
            self._on_success()
            return result
        except self.expected_exception as e:
            self._on_failure()
            raise

    def _on_success(self):
        if self.state == CircuitState.HALF_OPEN:
            self.success_count += 1
            if self.success_count >= self.success_threshold:
                logger.info(f"Circuit breaker {self.name}: HALF_OPEN -> CLOSED (recovered)")
                self.state = CircuitState.CLOSED
                self.failure_count = 0
                self.success_count = 0
        elif self.state == CircuitState.CLOSED:
            if self.failure_count > 0:
                self.failure_count = max(0, self.failure_count - 1)

    def _on_failure(self):
        self.failure_count += 1
        self.last_failure_time = time.time()
        if self.state == CircuitState.HALF_OPEN:
            logger.warning(f"Circuit breaker {self.name}: HALF_OPEN -> OPEN (still failing)")
            self.state = CircuitState.OPEN
            self.success_count = 0
        elif self.state == CircuitState.CLOSED:
            if self.failure_count >= self.failure_threshold:
                logger.warning(f"Circuit breaker {self.name}: CLOSED -> OPEN ({self.failure_count} failures >= {self.failure_threshold})")
                self.state = CircuitState.OPEN

    def get_state(self) -> dict:
        return {
            "name": self.name,
            "state": self.state.value,
            "failure_count": self.failure_count,
            "last_failure_time": self.last_failure_time,
            "failure_threshold": self.failure_threshold,
            "recovery_timeout": self.recovery_timeout
        }
    def reset(self):
        logger.info(f"Circuit breaker {self.name}: Manual reset")
        self.state = CircuitState.CLOSED
        self.failure_count = 0
        self.success_count = 0
        self.last_failure_time = None

def circuit_breaker_decorator(name: str, failure_threshold: int = 5, recovery_timeout: float = 60.0):
    breaker = CircuitBreaker(name=name, failure_threshold=failure_threshold, recovery_timeout=recovery_timeout)
    def decorator(func: Callable):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            return await breaker.call(func, *args, **kwargs)
        wrapper.breaker = breaker
        return wrapper
    return decorator
