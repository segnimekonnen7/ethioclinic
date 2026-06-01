"""
Redis client setup.

We use Redis for the queue: a sorted set per doctor stores patient IDs
with their enqueue timestamp as the score. This lets us get the queue
position (ZRANK) and pop the head (ZPOPMIN) atomically without database
round-trips.

For learning, we use a sync Redis client. In production, you'd use aioredis
for async operations without blocking the event loop.
"""

import os
import redis

# Read Redis URL from the environment, defaulting to localhost.
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")

# Create a sync Redis client. In production, this would be async (aioredis).
client = redis.from_url(REDIS_URL, decode_responses=True)


def get_redis():
    """
    Dependency to hand out the Redis client. Right now we just return
    the global client, but this pattern lets us swap it for a pool
    or a mock in tests.
    """
    return client
