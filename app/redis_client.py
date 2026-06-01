"""
Redis client setup.

We use Redis for the queue: a sorted set per doctor stores patient IDs
with their enqueue timestamp as the score. This lets us get the queue
position (ZRANK) and pop the head (ZPOPMIN) atomically without database
round-trips.

For learning, we use a sync Redis client. In production, you'd use aioredis
for async operations without blocking the event loop.
"""

import redis
from app.config import get_settings

settings = get_settings()

# Create a sync Redis client. In production, this would be async (aioredis).
client = redis.from_url(settings.redis_url, decode_responses=True)


def get_redis():
    """
    Dependency to hand out the Redis client. Right now we just return
    the global client, but this pattern lets us swap it for a pool
    or a mock in tests.
    """
    return client
