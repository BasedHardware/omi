"""Redis server-clock pacing shared by all instances using one Telegram bot."""

from utils.executors import db_executor, run_blocking
from utils.messaging.identity import key

_RESERVE = """
local clock = redis.call('TIME')
local now = tonumber(clock[1]) + tonumber(clock[2]) / 1000000
local global = tonumber(redis.call('GET', KEYS[1]) or '0')
local chat = tonumber(redis.call('GET', KEYS[2]) or '0')
local deadline = math.max(now, global, chat)
if deadline - now > 30 then return '-1' end
redis.call('SET', KEYS[1], tostring(deadline + 1/30), 'EX', 300)
redis.call('SET', KEYS[2], tostring(deadline + tonumber(ARGV[1])), 'EX', 300)
return tostring(deadline - now)
"""


def reserve(bot, chat):
    from database.redis_db import r
    from utils.messaging.adapters.transport import ProviderError

    global_key = 'messaging:telegram:' + key(bot) + ':global'
    chat_key = 'messaging:telegram:' + key(bot, chat) if chat else global_key
    delay = float(r.eval(_RESERVE, 2, global_key, chat_key, 1.05 if chat else 1 / 30))
    if delay < 0:
        raise ProviderError('Shared pacing backlog full', status_code=429)
    return delay


async def pace(bot, chat, sleep):
    """Return False on Redis outage so the adapter applies its local limiter."""
    from utils.messaging.adapters.transport import ProviderError
    from utils.observability.fallback import record_fallback
    import logging

    try:
        delay = await run_blocking(db_executor, reserve, bot, chat)
    except ProviderError:
        raise  # Deliberate backlog admission, not a Redis outage.
    except Exception as error:
        logging.getLogger(__name__).warning('Shared pacing unavailable error_type=%s', type(error).__name__)
        record_fallback(
            component='other',
            from_mode='redis_ratelimit',
            to_mode='local',
            reason='connection_error',
            outcome='degraded',
        )
        return False
    if delay:
        await sleep(delay)
    return True
