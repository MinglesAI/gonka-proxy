"""
Retry utilities with exponential backoff
"""
import asyncio
import random
import logging
from typing import Callable, TypeVar, Optional, Tuple, Any

logger = logging.getLogger(__name__)

T = TypeVar('T')


async def retry_with_backoff(
    func: Callable[[], T],
    max_retries: int = 3,
    initial_delay: float = 1.0,
    max_delay: float = 60.0,
    exponential_base: float = 2.0,
    jitter: bool = True,
    exceptions: Tuple[type, ...] = (Exception,),
    on_retry: Optional[Callable[[int, Exception], None]] = None
) -> T:
    """
    Retry function with exponential backoff
    
    Args:
        func: Async function to retry (no arguments)
        max_retries: Maximum number of retry attempts
        initial_delay: Initial delay in seconds
        max_delay: Maximum delay in seconds
        exponential_base: Base for exponential backoff
        jitter: Add random jitter to prevent thundering herd
        exceptions: Tuple of exceptions to catch and retry
        on_retry: Optional callback called on each retry (attempt, exception)
    
    Returns:
        Function result
    
    Raises:
        Last exception if all retries fail
    """
    delay = initial_delay
    last_exception = None
    
    for attempt in range(max_retries + 1):
        try:
            return await func()
        except exceptions as e:
            last_exception = e
            
            if attempt == max_retries:
                logger.error(
                    f"Retry exhausted after {max_retries} attempts. "
                    f"Last error: {type(e).__name__}: {e}"
                )
                raise
            
            # Calculate delay with exponential backoff
            if jitter:
                # Add random jitter: delay * base + random(0, 1)
                delay = min(
                    delay * exponential_base + random.uniform(0, 1),
                    max_delay
                )
            else:
                delay = min(delay * exponential_base, max_delay)
            
            logger.warning(
                f"Attempt {attempt + 1}/{max_retries} failed: {type(e).__name__}: {e}. "
                f"Retrying in {delay:.2f}s"
            )
            
            if on_retry:
                try:
                    on_retry(attempt + 1, e)
                except Exception as callback_error:
                    logger.warning(f"Retry callback error: {callback_error}")
            
            await asyncio.sleep(delay)
    
    # Should never reach here, but just in case
    if last_exception:
        raise last_exception
    raise RuntimeError("Retry failed without exception")


async def retry_with_backoff_args(
    func: Callable[..., T],
    *args,
    max_retries: int = 3,
    initial_delay: float = 1.0,
    max_delay: float = 60.0,
    exponential_base: float = 2.0,
    jitter: bool = True,
    exceptions: Tuple[type, ...] = (Exception,),
    **kwargs
) -> T:
    """
    Retry function with exponential backoff (supports arguments)
    
    Args:
        func: Async function to retry
        *args: Positional arguments for function
        max_retries: Maximum number of retry attempts
        initial_delay: Initial delay in seconds
        max_delay: Maximum delay in seconds
        exponential_base: Base for exponential backoff
        jitter: Add random jitter
        exceptions: Tuple of exceptions to catch and retry
        **kwargs: Keyword arguments for function
    
    Returns:
        Function result
    
    Raises:
        Last exception if all retries fail
    """
    async def wrapper():
        return await func(*args, **kwargs)
    
    return await retry_with_backoff(
        wrapper,
        max_retries=max_retries,
        initial_delay=initial_delay,
        max_delay=max_delay,
        exponential_base=exponential_base,
        jitter=jitter,
        exceptions=exceptions
    )


class RetryConfig:
    """Configuration for retry behavior"""
    
    def __init__(
        self,
        max_retries: int = 3,
        initial_delay: float = 1.0,
        max_delay: float = 60.0,
        exponential_base: float = 2.0,
        jitter: bool = True,
        exceptions: Tuple[type, ...] = (Exception,)
    ):
        self.max_retries = max_retries
        self.initial_delay = initial_delay
        self.max_delay = max_delay
        self.exponential_base = exponential_base
        self.jitter = jitter
        self.exceptions = exceptions


# Predefined retry configurations
HTTP_RETRY_CONFIG = RetryConfig(
    max_retries=3,
    initial_delay=1.0,
    max_delay=30.0,
    exceptions=(Exception,)  # Catch all for HTTP errors
)

DATABASE_RETRY_CONFIG = RetryConfig(
    max_retries=3,
    initial_delay=0.5,
    max_delay=10.0,
    exceptions=(Exception,)
)

BACKEND_RETRY_CONFIG = RetryConfig(
    max_retries=2,  # Fewer retries for backend calls (circuit breaker handles failures)
    initial_delay=1.0,
    max_delay=20.0,
    exceptions=(Exception,)
)
