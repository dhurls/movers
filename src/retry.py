import time
import functools
from src.logger import get_logger

log = get_logger(__name__)


def with_retry(max_attempts: int = 3, base_delay: float = 1.0, exceptions: tuple = (Exception,)):
    """Decorator: retry a function with exponential backoff on specified exceptions."""
    def decorator(fn):
        @functools.wraps(fn)
        def wrapper(*args, **kwargs):
            for attempt in range(1, max_attempts + 1):
                try:
                    return fn(*args, **kwargs)
                except exceptions as e:
                    if attempt == max_attempts:
                        log.error("%s failed after %d attempts: %s", fn.__name__, max_attempts, e)
                        raise
                    delay = base_delay * (2 ** (attempt - 1))
                    log.warning("%s attempt %d failed (%s), retrying in %.1fs", fn.__name__, attempt, e, delay)
                    time.sleep(delay)
        return wrapper
    return decorator
