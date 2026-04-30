import asyncio
import random
import logging
from typing import Callable, TypeVar, Optional, Tuple

logger = logging.getLogger(__name__)

T = TypeVar('T')

async def retry_with_backoff(func: Callable[[], T], max_retries: int = 3, initial_delay: float = 1.0, max_delay: float = 60.0, exponential_base: float = 2.0, jitter: bool = True, exceptions: Tuple[type, ...] = (Exception,), on_retry: Optional[Callable[[int, Exception], None]] = None) -> T:
    delay = initial_delay
    last_exception = None
    for attempt in range(max_retries + 1):
        try:
            return await func()
        except exceptions as e:
            last_exception = e
            if attempt == max_retries:
                logger.error(f"Retry exhausted after {max_retries} attempts. Last error: {type(e).__name__}: {e}")
                raise
            if jitter:
                delay = min(delay * exponential_base + random.uniform(0, 1), max_delay)
            else:
                delay = min(delay * exponential_base, max_delay)
            logger.warning(f"Attempt {attempt + 1}/{max_retries} failed: {type(e).__name__}: {e}. Retrying in {delay:.2f}s")
            if on_retry:
                try:
                    on_retry(attempt + 1, e)
                except Exception as callback_error:
                    logger.warning(f"Retry callback error: {callback_error}")
            await asyncio.sleep(delay)
    if last_exception:
        raise last_exception
    raise RuntimeError("Retry failed without exception")
