from redis.asyncio import Redis

from app.core.config import RedisSettings


def create_redis(settings: RedisSettings) -> Redis:
    client: Redis = Redis.from_url(
        settings.url.get_secret_value(),
        decode_responses=True,
        socket_connect_timeout=settings.connect_timeout_seconds,
    )
    return client
