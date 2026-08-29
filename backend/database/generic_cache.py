"""Path-keyed Redis cache helpers (GET/SET/DELETE/GETDEL).

Split out of database/redis_db.py because that module sits at the product-file
line-count ratchet threshold and may not grow further without a declared
exception. pop_generic_cache was added for atomic cleanup session consumption.
"""

import base64
import json
from typing import Any, Optional

from database.redis_db import r, try_catch_decorator


@try_catch_decorator
def get_generic_cache(path: str) -> Any:
    key = base64.b64encode(f'{path}'.encode('utf-8'))
    key = key.decode('utf-8')

    data = r.get(f'cache:{key}')
    return json.loads(data) if data else None


@try_catch_decorator
def set_generic_cache(path: str, data: object, ttl: Optional[int] = None) -> None:
    key = base64.b64encode(f'{path}'.encode('utf-8'))
    key = key.decode('utf-8')

    r.set(f'cache:{key}', json.dumps(data, default=str))
    if ttl:
        r.expire(f'cache:{key}', ttl)


@try_catch_decorator
def delete_generic_cache(path: str) -> None:
    key = base64.b64encode(f'{path}'.encode('utf-8'))
    key = key.decode('utf-8')
    r.delete(f'cache:{key}')


@try_catch_decorator
def pop_generic_cache(path: str) -> Any:
    """Atomically read and remove a generic cache entry (Redis GETDEL)."""
    key = base64.b64encode(f'{path}'.encode('utf-8'))
    key = key.decode('utf-8')
    data = r.getdel(f'cache:{key}')
    return json.loads(data) if data else None
