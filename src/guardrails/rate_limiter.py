"""
src/guardrails/rate_limiter.py

Sliding window rate limiter for user queries.
Supports Redis Cloud backend (Phase 6) and falls back to a thread-safe,
in-memory sliding window dictionary in RAM.

Timestamps older than 60 seconds are discarded dynamically during each check.
Returns (allowed, retry_after_seconds).
"""

import time
import asyncio
import logging
from typing import Tuple

logger = logging.getLogger(__name__)

# ── In-Memory Storage ─────────────────────────────────────────────────────────
_user_logs: dict[str, list[float]] = {}
_limiter_lock = asyncio.Lock()


async def check_rate_limit(
    user_id: str,
    limit: int = 10,
    window_seconds: int = 60,
    redis_client=None,
) -> Tuple[bool, int]:
    """
    Check if a user is within their rate limit.
    
    Args:
        user_id: The UUID of the user.
        limit: Max queries allowed in the window.
        window_seconds: Duration of limit window.
        redis_client: Optional redis connection client.
        
    Returns:
        Tuple of:
          - bool: True if query is allowed, False if rate-limited.
          - int: Remaining seconds until next slot opens up (retry_after).
    """
    now = time.time()
    
    # 1. Try Redis rate limiting if client is available (Phase 6 integration)
    if redis_client is not None:
        try:
            key = f"rate_limit:{user_id}"
            # Multi-exec transactions or sorted sets for sliding window
            pipe = redis_client.pipeline()
            # Remove expired timestamps
            pipe.zremrangebyscore(key, 0, now - window_seconds)
            # Count elements remaining
            pipe.zcard(key)
            # Add current timestamp
            pipe.zadd(key, {str(now): now})
            # Set TTL on key
            pipe.expire(key, window_seconds)
            
            _, count, _, _ = pipe.execute()
            
            if count >= limit:
                # Get the oldest timestamp in set to calculate retry_after
                oldest = redis_client.zrange(key, 0, 0, withscores=True)
                retry_after = 0
                if oldest:
                    retry_after = max(1, int(oldest[0][1] + window_seconds - now))
                return False, retry_after
            return True, 0
        except Exception as e:
            logger.error(f"[RateLimiter] Redis rate limiting failed: {e}. Falling back to in-memory.")

    # 2. In-Memory Sliding Window Fallback
    async with _limiter_lock:
        user_logs = _user_logs.setdefault(user_id, [])
        
        # Remove timestamps older than window
        cutoff = now - window_seconds
        _user_logs[user_id] = [t for t in user_logs if t > cutoff]
        
        if len(_user_logs[user_id]) >= limit:
            # Calculate retry after based on oldest log
            oldest = _user_logs[user_id][0]
            retry_after = max(1, int(oldest + window_seconds - now))
            logger.warning(f"[RateLimiter] User {user_id} was rate limited. Retry after {retry_after}s.")
            return False, retry_after
            
        # Add current timestamp
        _user_logs[user_id].append(now)
        return True, 0
