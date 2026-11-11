"""Async-blocker gate sink-classification lattice.

One emitted test pins one (sink-kind x call-form x context) combination of
the event-loop blocking surface as literal finding counts: 8 sink
kinds x 6 call forms x 2 contexts = 96 cells. The
lattice documents the whole classification surface the source-resolved
database-module exemptions (FC-async-blocker-gate-false-positive-on-pure-db-classifiers) sit inside: a direct sink call is
classified by kind (db / file / network / sleep), a call handed to asyncio
(``await``, ``gather``, ``shield``) drives on the loop and is never
blocking, ``asyncio.to_thread`` is its own unmanaged-offload finding, and
the owned ``run_blocking`` pool is the sanctioned offload that stays silent.
Endpoint context reports the structural categories; a plain async helper
reports ``async_helpers_with_blocking``.

Every cell runs the real scanner over a fixture it writes into ``tmp_path``.
A scanner change that re-classifies any combination fails exactly the cells
whose behavior moved.

Failure-Class: FC-async-blocker-gate-false-positive-on-pure-db-classifiers
"""

import textwrap

from scripts.scan_async_blockers import scan_dirs


def _scan(tmp_path, source):
    (tmp_path / "caller.py").write_text(textwrap.dedent(source), encoding="utf-8")
    return scan_dirs([str(tmp_path)])


def test_sink_db_get_user_direct_endpoint(tmp_path) -> None:
    """db_get_user x direct x endpoint: mixed_await_sync_db=1."""
    source = '''
        from database.users import get_user
        import asyncio
        
        
        @router.get('/items/{uid}')
        async def read_item(uid):
            await asyncio.sleep(0)
            result = get_user(uid)
            return result
    '''
    results = _scan(tmp_path, source)
    assert results['high_network_io'] == [] if 0 == 0 else len(results['high_network_io']) == 1
    assert results['medium_file_io'] == [] if 0 == 0 else len(results['medium_file_io']) == 1
    assert results['no_await_should_be_def'] == [] if 0 == 0 else len(results['no_await_should_be_def']) == 1
    assert results['mixed_await_sync_db'] == [] if 1 == 0 else len(results['mixed_await_sync_db']) == 1
    assert results['time_sleep'] == [] if 0 == 0 else len(results['time_sleep']) == 1
    assert results['async_helpers_with_blocking'] == [] if 0 == 0 else len(results['async_helpers_with_blocking']) == 1
    assert results['unmanaged_thread_offload'] == [] if 0 == 0 else len(results['unmanaged_thread_offload']) == 1


def test_sink_db_get_user_direct_helper(tmp_path) -> None:
    """db_get_user x direct x helper: async_helpers_with_blocking=1."""
    source = '''
        from database.users import get_user
        
        
        async def read_item(uid):
            result = get_user(uid)
            return result
    '''
    results = _scan(tmp_path, source)
    assert results['high_network_io'] == [] if 0 == 0 else len(results['high_network_io']) == 1
    assert results['medium_file_io'] == [] if 0 == 0 else len(results['medium_file_io']) == 1
    assert results['no_await_should_be_def'] == [] if 0 == 0 else len(results['no_await_should_be_def']) == 1
    assert results['mixed_await_sync_db'] == [] if 0 == 0 else len(results['mixed_await_sync_db']) == 1
    assert results['time_sleep'] == [] if 0 == 0 else len(results['time_sleep']) == 1
    assert results['async_helpers_with_blocking'] == [] if 1 == 0 else len(results['async_helpers_with_blocking']) == 1
    assert results['unmanaged_thread_offload'] == [] if 0 == 0 else len(results['unmanaged_thread_offload']) == 1


def test_sink_db_get_user_awaited_endpoint(tmp_path) -> None:
    """db_get_user x awaited x endpoint: clean."""
    source = '''
        from database.users import get_user
        import asyncio
        
        
        @router.get('/items/{uid}')
        async def read_item(uid):
            await asyncio.sleep(0)
            result = await get_user(uid)
            return result
    '''
    results = _scan(tmp_path, source)
    assert results['high_network_io'] == [] if 0 == 0 else len(results['high_network_io']) == 1
    assert results['medium_file_io'] == [] if 0 == 0 else len(results['medium_file_io']) == 1
    assert results['no_await_should_be_def'] == [] if 0 == 0 else len(results['no_await_should_be_def']) == 1
    assert results['mixed_await_sync_db'] == [] if 0 == 0 else len(results['mixed_await_sync_db']) == 1
    assert results['time_sleep'] == [] if 0 == 0 else len(results['time_sleep']) == 1
    assert results['async_helpers_with_blocking'] == [] if 0 == 0 else len(results['async_helpers_with_blocking']) == 1
    assert results['unmanaged_thread_offload'] == [] if 0 == 0 else len(results['unmanaged_thread_offload']) == 1


def test_sink_db_get_user_awaited_helper(tmp_path) -> None:
    """db_get_user x awaited x helper: clean."""
    source = '''
        from database.users import get_user
        
        
        async def read_item(uid):
            result = await get_user(uid)
            return result
    '''
    results = _scan(tmp_path, source)
    assert results['high_network_io'] == [] if 0 == 0 else len(results['high_network_io']) == 1
    assert results['medium_file_io'] == [] if 0 == 0 else len(results['medium_file_io']) == 1
    assert results['no_await_should_be_def'] == [] if 0 == 0 else len(results['no_await_should_be_def']) == 1
    assert results['mixed_await_sync_db'] == [] if 0 == 0 else len(results['mixed_await_sync_db']) == 1
    assert results['time_sleep'] == [] if 0 == 0 else len(results['time_sleep']) == 1
    assert results['async_helpers_with_blocking'] == [] if 0 == 0 else len(results['async_helpers_with_blocking']) == 1
    assert results['unmanaged_thread_offload'] == [] if 0 == 0 else len(results['unmanaged_thread_offload']) == 1


def test_sink_db_get_user_gather_arg_endpoint(tmp_path) -> None:
    """db_get_user x gather_arg x endpoint: clean."""
    source = '''
        from database.users import get_user
        import asyncio
        
        
        @router.get('/items/{uid}')
        async def read_item(uid):
            await asyncio.sleep(0)
            result = asyncio.gather(get_user(uid))
            return result
    '''
    results = _scan(tmp_path, source)
    assert results['high_network_io'] == [] if 0 == 0 else len(results['high_network_io']) == 1
    assert results['medium_file_io'] == [] if 0 == 0 else len(results['medium_file_io']) == 1
    assert results['no_await_should_be_def'] == [] if 0 == 0 else len(results['no_await_should_be_def']) == 1
    assert results['mixed_await_sync_db'] == [] if 0 == 0 else len(results['mixed_await_sync_db']) == 1
    assert results['time_sleep'] == [] if 0 == 0 else len(results['time_sleep']) == 1
    assert results['async_helpers_with_blocking'] == [] if 0 == 0 else len(results['async_helpers_with_blocking']) == 1
    assert results['unmanaged_thread_offload'] == [] if 0 == 0 else len(results['unmanaged_thread_offload']) == 1


def test_sink_db_get_user_gather_arg_helper(tmp_path) -> None:
    """db_get_user x gather_arg x helper: clean."""
    source = '''
        from database.users import get_user
        import asyncio
        
        
        async def read_item(uid):
            result = asyncio.gather(get_user(uid))
            return result
    '''
    results = _scan(tmp_path, source)
    assert results['high_network_io'] == [] if 0 == 0 else len(results['high_network_io']) == 1
    assert results['medium_file_io'] == [] if 0 == 0 else len(results['medium_file_io']) == 1
    assert results['no_await_should_be_def'] == [] if 0 == 0 else len(results['no_await_should_be_def']) == 1
    assert results['mixed_await_sync_db'] == [] if 0 == 0 else len(results['mixed_await_sync_db']) == 1
    assert results['time_sleep'] == [] if 0 == 0 else len(results['time_sleep']) == 1
    assert results['async_helpers_with_blocking'] == [] if 0 == 0 else len(results['async_helpers_with_blocking']) == 1
    assert results['unmanaged_thread_offload'] == [] if 0 == 0 else len(results['unmanaged_thread_offload']) == 1


def test_sink_db_get_user_shield_arg_endpoint(tmp_path) -> None:
    """db_get_user x shield_arg x endpoint: clean."""
    source = '''
        from database.users import get_user
        import asyncio
        
        
        @router.get('/items/{uid}')
        async def read_item(uid):
            await asyncio.sleep(0)
            result = asyncio.shield(get_user(uid))
            return result
    '''
    results = _scan(tmp_path, source)
    assert results['high_network_io'] == [] if 0 == 0 else len(results['high_network_io']) == 1
    assert results['medium_file_io'] == [] if 0 == 0 else len(results['medium_file_io']) == 1
    assert results['no_await_should_be_def'] == [] if 0 == 0 else len(results['no_await_should_be_def']) == 1
    assert results['mixed_await_sync_db'] == [] if 0 == 0 else len(results['mixed_await_sync_db']) == 1
    assert results['time_sleep'] == [] if 0 == 0 else len(results['time_sleep']) == 1
    assert results['async_helpers_with_blocking'] == [] if 0 == 0 else len(results['async_helpers_with_blocking']) == 1
    assert results['unmanaged_thread_offload'] == [] if 0 == 0 else len(results['unmanaged_thread_offload']) == 1


def test_sink_db_get_user_shield_arg_helper(tmp_path) -> None:
    """db_get_user x shield_arg x helper: clean."""
    source = '''
        from database.users import get_user
        import asyncio
        
        
        async def read_item(uid):
            result = asyncio.shield(get_user(uid))
            return result
    '''
    results = _scan(tmp_path, source)
    assert results['high_network_io'] == [] if 0 == 0 else len(results['high_network_io']) == 1
    assert results['medium_file_io'] == [] if 0 == 0 else len(results['medium_file_io']) == 1
    assert results['no_await_should_be_def'] == [] if 0 == 0 else len(results['no_await_should_be_def']) == 1
    assert results['mixed_await_sync_db'] == [] if 0 == 0 else len(results['mixed_await_sync_db']) == 1
    assert results['time_sleep'] == [] if 0 == 0 else len(results['time_sleep']) == 1
    assert results['async_helpers_with_blocking'] == [] if 0 == 0 else len(results['async_helpers_with_blocking']) == 1
    assert results['unmanaged_thread_offload'] == [] if 0 == 0 else len(results['unmanaged_thread_offload']) == 1


def test_sink_db_get_user_to_thread_offload_endpoint(tmp_path) -> None:
    """db_get_user x to_thread_offload x endpoint: unmanaged_thread_offload=1."""
    source = '''
        from database.users import get_user
        import asyncio
        
        
        @router.get('/items/{uid}')
        async def read_item(uid):
            await asyncio.sleep(0)
            result = asyncio.to_thread(get_user, uid)
            return result
    '''
    results = _scan(tmp_path, source)
    assert results['high_network_io'] == [] if 0 == 0 else len(results['high_network_io']) == 1
    assert results['medium_file_io'] == [] if 0 == 0 else len(results['medium_file_io']) == 1
    assert results['no_await_should_be_def'] == [] if 0 == 0 else len(results['no_await_should_be_def']) == 1
    assert results['mixed_await_sync_db'] == [] if 0 == 0 else len(results['mixed_await_sync_db']) == 1
    assert results['time_sleep'] == [] if 0 == 0 else len(results['time_sleep']) == 1
    assert results['async_helpers_with_blocking'] == [] if 0 == 0 else len(results['async_helpers_with_blocking']) == 1
    assert results['unmanaged_thread_offload'] == [] if 1 == 0 else len(results['unmanaged_thread_offload']) == 1


def test_sink_db_get_user_to_thread_offload_helper(tmp_path) -> None:
    """db_get_user x to_thread_offload x helper: unmanaged_thread_offload=1."""
    source = '''
        from database.users import get_user
        import asyncio
        
        
        async def read_item(uid):
            result = asyncio.to_thread(get_user, uid)
            return result
    '''
    results = _scan(tmp_path, source)
    assert results['high_network_io'] == [] if 0 == 0 else len(results['high_network_io']) == 1
    assert results['medium_file_io'] == [] if 0 == 0 else len(results['medium_file_io']) == 1
    assert results['no_await_should_be_def'] == [] if 0 == 0 else len(results['no_await_should_be_def']) == 1
    assert results['mixed_await_sync_db'] == [] if 0 == 0 else len(results['mixed_await_sync_db']) == 1
    assert results['time_sleep'] == [] if 0 == 0 else len(results['time_sleep']) == 1
    assert results['async_helpers_with_blocking'] == [] if 0 == 0 else len(results['async_helpers_with_blocking']) == 1
    assert results['unmanaged_thread_offload'] == [] if 1 == 0 else len(results['unmanaged_thread_offload']) == 1


def test_sink_db_get_user_run_blocking_offload_endpoint(tmp_path) -> None:
    """db_get_user x run_blocking_offload x endpoint: clean."""
    source = '''
        from database.users import get_user
        import asyncio
        from utils.executors import run_blocking
        
        
        @router.get('/items/{uid}')
        async def read_item(uid):
            await asyncio.sleep(0)
            result = run_blocking(POOL, get_user, uid)
            return result
    '''
    results = _scan(tmp_path, source)
    assert results['high_network_io'] == [] if 0 == 0 else len(results['high_network_io']) == 1
    assert results['medium_file_io'] == [] if 0 == 0 else len(results['medium_file_io']) == 1
    assert results['no_await_should_be_def'] == [] if 0 == 0 else len(results['no_await_should_be_def']) == 1
    assert results['mixed_await_sync_db'] == [] if 0 == 0 else len(results['mixed_await_sync_db']) == 1
    assert results['time_sleep'] == [] if 0 == 0 else len(results['time_sleep']) == 1
    assert results['async_helpers_with_blocking'] == [] if 0 == 0 else len(results['async_helpers_with_blocking']) == 1
    assert results['unmanaged_thread_offload'] == [] if 0 == 0 else len(results['unmanaged_thread_offload']) == 1


def test_sink_db_get_user_run_blocking_offload_helper(tmp_path) -> None:
    """db_get_user x run_blocking_offload x helper: clean."""
    source = '''
        from database.users import get_user
        from utils.executors import run_blocking
        
        
        async def read_item(uid):
            result = run_blocking(POOL, get_user, uid)
            return result
    '''
    results = _scan(tmp_path, source)
    assert results['high_network_io'] == [] if 0 == 0 else len(results['high_network_io']) == 1
    assert results['medium_file_io'] == [] if 0 == 0 else len(results['medium_file_io']) == 1
    assert results['no_await_should_be_def'] == [] if 0 == 0 else len(results['no_await_should_be_def']) == 1
    assert results['mixed_await_sync_db'] == [] if 0 == 0 else len(results['mixed_await_sync_db']) == 1
    assert results['time_sleep'] == [] if 0 == 0 else len(results['time_sleep']) == 1
    assert results['async_helpers_with_blocking'] == [] if 0 == 0 else len(results['async_helpers_with_blocking']) == 1
    assert results['unmanaged_thread_offload'] == [] if 0 == 0 else len(results['unmanaged_thread_offload']) == 1


def test_sink_db_module_attr_direct_endpoint(tmp_path) -> None:
    """db_module_attr x direct x endpoint: mixed_await_sync_db=1."""
    source = '''
        import database.redis_db
        import asyncio
        
        
        @router.get('/items/{uid}')
        async def read_item(uid):
            await asyncio.sleep(0)
            result = redis_db.get_cache(uid)
            return result
    '''
    results = _scan(tmp_path, source)
    assert results['high_network_io'] == [] if 0 == 0 else len(results['high_network_io']) == 1
    assert results['medium_file_io'] == [] if 0 == 0 else len(results['medium_file_io']) == 1
    assert results['no_await_should_be_def'] == [] if 0 == 0 else len(results['no_await_should_be_def']) == 1
    assert results['mixed_await_sync_db'] == [] if 1 == 0 else len(results['mixed_await_sync_db']) == 1
    assert results['time_sleep'] == [] if 0 == 0 else len(results['time_sleep']) == 1
    assert results['async_helpers_with_blocking'] == [] if 0 == 0 else len(results['async_helpers_with_blocking']) == 1
    assert results['unmanaged_thread_offload'] == [] if 0 == 0 else len(results['unmanaged_thread_offload']) == 1


def test_sink_db_module_attr_direct_helper(tmp_path) -> None:
    """db_module_attr x direct x helper: async_helpers_with_blocking=1."""
    source = '''
        import database.redis_db
        
        
        async def read_item(uid):
            result = redis_db.get_cache(uid)
            return result
    '''
    results = _scan(tmp_path, source)
    assert results['high_network_io'] == [] if 0 == 0 else len(results['high_network_io']) == 1
    assert results['medium_file_io'] == [] if 0 == 0 else len(results['medium_file_io']) == 1
    assert results['no_await_should_be_def'] == [] if 0 == 0 else len(results['no_await_should_be_def']) == 1
    assert results['mixed_await_sync_db'] == [] if 0 == 0 else len(results['mixed_await_sync_db']) == 1
    assert results['time_sleep'] == [] if 0 == 0 else len(results['time_sleep']) == 1
    assert results['async_helpers_with_blocking'] == [] if 1 == 0 else len(results['async_helpers_with_blocking']) == 1
    assert results['unmanaged_thread_offload'] == [] if 0 == 0 else len(results['unmanaged_thread_offload']) == 1


def test_sink_db_module_attr_awaited_endpoint(tmp_path) -> None:
    """db_module_attr x awaited x endpoint: clean."""
    source = '''
        import database.redis_db
        import asyncio
        
        
        @router.get('/items/{uid}')
        async def read_item(uid):
            await asyncio.sleep(0)
            result = await redis_db.get_cache(uid)
            return result
    '''
    results = _scan(tmp_path, source)
    assert results['high_network_io'] == [] if 0 == 0 else len(results['high_network_io']) == 1
    assert results['medium_file_io'] == [] if 0 == 0 else len(results['medium_file_io']) == 1
    assert results['no_await_should_be_def'] == [] if 0 == 0 else len(results['no_await_should_be_def']) == 1
    assert results['mixed_await_sync_db'] == [] if 0 == 0 else len(results['mixed_await_sync_db']) == 1
    assert results['time_sleep'] == [] if 0 == 0 else len(results['time_sleep']) == 1
    assert results['async_helpers_with_blocking'] == [] if 0 == 0 else len(results['async_helpers_with_blocking']) == 1
    assert results['unmanaged_thread_offload'] == [] if 0 == 0 else len(results['unmanaged_thread_offload']) == 1


def test_sink_db_module_attr_awaited_helper(tmp_path) -> None:
    """db_module_attr x awaited x helper: clean."""
    source = '''
        import database.redis_db
        
        
        async def read_item(uid):
            result = await redis_db.get_cache(uid)
            return result
    '''
    results = _scan(tmp_path, source)
    assert results['high_network_io'] == [] if 0 == 0 else len(results['high_network_io']) == 1
    assert results['medium_file_io'] == [] if 0 == 0 else len(results['medium_file_io']) == 1
    assert results['no_await_should_be_def'] == [] if 0 == 0 else len(results['no_await_should_be_def']) == 1
    assert results['mixed_await_sync_db'] == [] if 0 == 0 else len(results['mixed_await_sync_db']) == 1
    assert results['time_sleep'] == [] if 0 == 0 else len(results['time_sleep']) == 1
    assert results['async_helpers_with_blocking'] == [] if 0 == 0 else len(results['async_helpers_with_blocking']) == 1
    assert results['unmanaged_thread_offload'] == [] if 0 == 0 else len(results['unmanaged_thread_offload']) == 1


def test_sink_db_module_attr_gather_arg_endpoint(tmp_path) -> None:
    """db_module_attr x gather_arg x endpoint: clean."""
    source = '''
        import database.redis_db
        import asyncio
        
        
        @router.get('/items/{uid}')
        async def read_item(uid):
            await asyncio.sleep(0)
            result = asyncio.gather(redis_db.get_cache(uid))
            return result
    '''
    results = _scan(tmp_path, source)
    assert results['high_network_io'] == [] if 0 == 0 else len(results['high_network_io']) == 1
    assert results['medium_file_io'] == [] if 0 == 0 else len(results['medium_file_io']) == 1
    assert results['no_await_should_be_def'] == [] if 0 == 0 else len(results['no_await_should_be_def']) == 1
    assert results['mixed_await_sync_db'] == [] if 0 == 0 else len(results['mixed_await_sync_db']) == 1
    assert results['time_sleep'] == [] if 0 == 0 else len(results['time_sleep']) == 1
    assert results['async_helpers_with_blocking'] == [] if 0 == 0 else len(results['async_helpers_with_blocking']) == 1
    assert results['unmanaged_thread_offload'] == [] if 0 == 0 else len(results['unmanaged_thread_offload']) == 1


def test_sink_db_module_attr_gather_arg_helper(tmp_path) -> None:
    """db_module_attr x gather_arg x helper: clean."""
    source = '''
        import database.redis_db
        import asyncio
        
        
        async def read_item(uid):
            result = asyncio.gather(redis_db.get_cache(uid))
            return result
    '''
    results = _scan(tmp_path, source)
    assert results['high_network_io'] == [] if 0 == 0 else len(results['high_network_io']) == 1
    assert results['medium_file_io'] == [] if 0 == 0 else len(results['medium_file_io']) == 1
    assert results['no_await_should_be_def'] == [] if 0 == 0 else len(results['no_await_should_be_def']) == 1
    assert results['mixed_await_sync_db'] == [] if 0 == 0 else len(results['mixed_await_sync_db']) == 1
    assert results['time_sleep'] == [] if 0 == 0 else len(results['time_sleep']) == 1
    assert results['async_helpers_with_blocking'] == [] if 0 == 0 else len(results['async_helpers_with_blocking']) == 1
    assert results['unmanaged_thread_offload'] == [] if 0 == 0 else len(results['unmanaged_thread_offload']) == 1


def test_sink_db_module_attr_shield_arg_endpoint(tmp_path) -> None:
    """db_module_attr x shield_arg x endpoint: clean."""
    source = '''
        import database.redis_db
        import asyncio
        
        
        @router.get('/items/{uid}')
        async def read_item(uid):
            await asyncio.sleep(0)
            result = asyncio.shield(redis_db.get_cache(uid))
            return result
    '''
    results = _scan(tmp_path, source)
    assert results['high_network_io'] == [] if 0 == 0 else len(results['high_network_io']) == 1
    assert results['medium_file_io'] == [] if 0 == 0 else len(results['medium_file_io']) == 1
    assert results['no_await_should_be_def'] == [] if 0 == 0 else len(results['no_await_should_be_def']) == 1
    assert results['mixed_await_sync_db'] == [] if 0 == 0 else len(results['mixed_await_sync_db']) == 1
    assert results['time_sleep'] == [] if 0 == 0 else len(results['time_sleep']) == 1
    assert results['async_helpers_with_blocking'] == [] if 0 == 0 else len(results['async_helpers_with_blocking']) == 1
    assert results['unmanaged_thread_offload'] == [] if 0 == 0 else len(results['unmanaged_thread_offload']) == 1


def test_sink_db_module_attr_shield_arg_helper(tmp_path) -> None:
    """db_module_attr x shield_arg x helper: clean."""
    source = '''
        import database.redis_db
        import asyncio
        
        
        async def read_item(uid):
            result = asyncio.shield(redis_db.get_cache(uid))
            return result
    '''
    results = _scan(tmp_path, source)
    assert results['high_network_io'] == [] if 0 == 0 else len(results['high_network_io']) == 1
    assert results['medium_file_io'] == [] if 0 == 0 else len(results['medium_file_io']) == 1
    assert results['no_await_should_be_def'] == [] if 0 == 0 else len(results['no_await_should_be_def']) == 1
    assert results['mixed_await_sync_db'] == [] if 0 == 0 else len(results['mixed_await_sync_db']) == 1
    assert results['time_sleep'] == [] if 0 == 0 else len(results['time_sleep']) == 1
    assert results['async_helpers_with_blocking'] == [] if 0 == 0 else len(results['async_helpers_with_blocking']) == 1
    assert results['unmanaged_thread_offload'] == [] if 0 == 0 else len(results['unmanaged_thread_offload']) == 1


def test_sink_db_module_attr_to_thread_offload_endpoint(tmp_path) -> None:
    """db_module_attr x to_thread_offload x endpoint: unmanaged_thread_offload=1."""
    source = '''
        import database.redis_db
        import asyncio
        
        
        @router.get('/items/{uid}')
        async def read_item(uid):
            await asyncio.sleep(0)
            result = asyncio.to_thread(redis_db.get_cache, uid)
            return result
    '''
    results = _scan(tmp_path, source)
    assert results['high_network_io'] == [] if 0 == 0 else len(results['high_network_io']) == 1
    assert results['medium_file_io'] == [] if 0 == 0 else len(results['medium_file_io']) == 1
    assert results['no_await_should_be_def'] == [] if 0 == 0 else len(results['no_await_should_be_def']) == 1
    assert results['mixed_await_sync_db'] == [] if 0 == 0 else len(results['mixed_await_sync_db']) == 1
    assert results['time_sleep'] == [] if 0 == 0 else len(results['time_sleep']) == 1
    assert results['async_helpers_with_blocking'] == [] if 0 == 0 else len(results['async_helpers_with_blocking']) == 1
    assert results['unmanaged_thread_offload'] == [] if 1 == 0 else len(results['unmanaged_thread_offload']) == 1


def test_sink_db_module_attr_to_thread_offload_helper(tmp_path) -> None:
    """db_module_attr x to_thread_offload x helper: unmanaged_thread_offload=1."""
    source = '''
        import database.redis_db
        import asyncio
        
        
        async def read_item(uid):
            result = asyncio.to_thread(redis_db.get_cache, uid)
            return result
    '''
    results = _scan(tmp_path, source)
    assert results['high_network_io'] == [] if 0 == 0 else len(results['high_network_io']) == 1
    assert results['medium_file_io'] == [] if 0 == 0 else len(results['medium_file_io']) == 1
    assert results['no_await_should_be_def'] == [] if 0 == 0 else len(results['no_await_should_be_def']) == 1
    assert results['mixed_await_sync_db'] == [] if 0 == 0 else len(results['mixed_await_sync_db']) == 1
    assert results['time_sleep'] == [] if 0 == 0 else len(results['time_sleep']) == 1
    assert results['async_helpers_with_blocking'] == [] if 0 == 0 else len(results['async_helpers_with_blocking']) == 1
    assert results['unmanaged_thread_offload'] == [] if 1 == 0 else len(results['unmanaged_thread_offload']) == 1


def test_sink_db_module_attr_run_blocking_offload_endpoint(tmp_path) -> None:
    """db_module_attr x run_blocking_offload x endpoint: clean."""
    source = '''
        import database.redis_db
        import asyncio
        from utils.executors import run_blocking
        
        
        @router.get('/items/{uid}')
        async def read_item(uid):
            await asyncio.sleep(0)
            result = run_blocking(POOL, redis_db.get_cache, uid)
            return result
    '''
    results = _scan(tmp_path, source)
    assert results['high_network_io'] == [] if 0 == 0 else len(results['high_network_io']) == 1
    assert results['medium_file_io'] == [] if 0 == 0 else len(results['medium_file_io']) == 1
    assert results['no_await_should_be_def'] == [] if 0 == 0 else len(results['no_await_should_be_def']) == 1
    assert results['mixed_await_sync_db'] == [] if 0 == 0 else len(results['mixed_await_sync_db']) == 1
    assert results['time_sleep'] == [] if 0 == 0 else len(results['time_sleep']) == 1
    assert results['async_helpers_with_blocking'] == [] if 0 == 0 else len(results['async_helpers_with_blocking']) == 1
    assert results['unmanaged_thread_offload'] == [] if 0 == 0 else len(results['unmanaged_thread_offload']) == 1


def test_sink_db_module_attr_run_blocking_offload_helper(tmp_path) -> None:
    """db_module_attr x run_blocking_offload x helper: clean."""
    source = '''
        import database.redis_db
        from utils.executors import run_blocking
        
        
        async def read_item(uid):
            result = run_blocking(POOL, redis_db.get_cache, uid)
            return result
    '''
    results = _scan(tmp_path, source)
    assert results['high_network_io'] == [] if 0 == 0 else len(results['high_network_io']) == 1
    assert results['medium_file_io'] == [] if 0 == 0 else len(results['medium_file_io']) == 1
    assert results['no_await_should_be_def'] == [] if 0 == 0 else len(results['no_await_should_be_def']) == 1
    assert results['mixed_await_sync_db'] == [] if 0 == 0 else len(results['mixed_await_sync_db']) == 1
    assert results['time_sleep'] == [] if 0 == 0 else len(results['time_sleep']) == 1
    assert results['async_helpers_with_blocking'] == [] if 0 == 0 else len(results['async_helpers_with_blocking']) == 1
    assert results['unmanaged_thread_offload'] == [] if 0 == 0 else len(results['unmanaged_thread_offload']) == 1


def test_sink_storage_upload_direct_endpoint(tmp_path) -> None:
    """storage_upload x direct x endpoint: high_network_io=1."""
    source = '''
        from utils.storage.upload import upload_audio
        import asyncio
        
        
        @router.get('/items/{uid}')
        async def read_item(uid):
            await asyncio.sleep(0)
            result = upload_audio(uid)
            return result
    '''
    results = _scan(tmp_path, source)
    assert results['high_network_io'] == [] if 1 == 0 else len(results['high_network_io']) == 1
    assert results['medium_file_io'] == [] if 0 == 0 else len(results['medium_file_io']) == 1
    assert results['no_await_should_be_def'] == [] if 0 == 0 else len(results['no_await_should_be_def']) == 1
    assert results['mixed_await_sync_db'] == [] if 0 == 0 else len(results['mixed_await_sync_db']) == 1
    assert results['time_sleep'] == [] if 0 == 0 else len(results['time_sleep']) == 1
    assert results['async_helpers_with_blocking'] == [] if 0 == 0 else len(results['async_helpers_with_blocking']) == 1
    assert results['unmanaged_thread_offload'] == [] if 0 == 0 else len(results['unmanaged_thread_offload']) == 1


def test_sink_storage_upload_direct_helper(tmp_path) -> None:
    """storage_upload x direct x helper: async_helpers_with_blocking=1."""
    source = '''
        from utils.storage.upload import upload_audio
        
        
        async def read_item(uid):
            result = upload_audio(uid)
            return result
    '''
    results = _scan(tmp_path, source)
    assert results['high_network_io'] == [] if 0 == 0 else len(results['high_network_io']) == 1
    assert results['medium_file_io'] == [] if 0 == 0 else len(results['medium_file_io']) == 1
    assert results['no_await_should_be_def'] == [] if 0 == 0 else len(results['no_await_should_be_def']) == 1
    assert results['mixed_await_sync_db'] == [] if 0 == 0 else len(results['mixed_await_sync_db']) == 1
    assert results['time_sleep'] == [] if 0 == 0 else len(results['time_sleep']) == 1
    assert results['async_helpers_with_blocking'] == [] if 1 == 0 else len(results['async_helpers_with_blocking']) == 1
    assert results['unmanaged_thread_offload'] == [] if 0 == 0 else len(results['unmanaged_thread_offload']) == 1


def test_sink_storage_upload_awaited_endpoint(tmp_path) -> None:
    """storage_upload x awaited x endpoint: clean."""
    source = '''
        from utils.storage.upload import upload_audio
        import asyncio
        
        
        @router.get('/items/{uid}')
        async def read_item(uid):
            await asyncio.sleep(0)
            result = await upload_audio(uid)
            return result
    '''
    results = _scan(tmp_path, source)
    assert results['high_network_io'] == [] if 0 == 0 else len(results['high_network_io']) == 1
    assert results['medium_file_io'] == [] if 0 == 0 else len(results['medium_file_io']) == 1
    assert results['no_await_should_be_def'] == [] if 0 == 0 else len(results['no_await_should_be_def']) == 1
    assert results['mixed_await_sync_db'] == [] if 0 == 0 else len(results['mixed_await_sync_db']) == 1
    assert results['time_sleep'] == [] if 0 == 0 else len(results['time_sleep']) == 1
    assert results['async_helpers_with_blocking'] == [] if 0 == 0 else len(results['async_helpers_with_blocking']) == 1
    assert results['unmanaged_thread_offload'] == [] if 0 == 0 else len(results['unmanaged_thread_offload']) == 1


def test_sink_storage_upload_awaited_helper(tmp_path) -> None:
    """storage_upload x awaited x helper: clean."""
    source = '''
        from utils.storage.upload import upload_audio
        
        
        async def read_item(uid):
            result = await upload_audio(uid)
            return result
    '''
    results = _scan(tmp_path, source)
    assert results['high_network_io'] == [] if 0 == 0 else len(results['high_network_io']) == 1
    assert results['medium_file_io'] == [] if 0 == 0 else len(results['medium_file_io']) == 1
    assert results['no_await_should_be_def'] == [] if 0 == 0 else len(results['no_await_should_be_def']) == 1
    assert results['mixed_await_sync_db'] == [] if 0 == 0 else len(results['mixed_await_sync_db']) == 1
    assert results['time_sleep'] == [] if 0 == 0 else len(results['time_sleep']) == 1
    assert results['async_helpers_with_blocking'] == [] if 0 == 0 else len(results['async_helpers_with_blocking']) == 1
    assert results['unmanaged_thread_offload'] == [] if 0 == 0 else len(results['unmanaged_thread_offload']) == 1


def test_sink_storage_upload_gather_arg_endpoint(tmp_path) -> None:
    """storage_upload x gather_arg x endpoint: clean."""
    source = '''
        from utils.storage.upload import upload_audio
        import asyncio
        
        
        @router.get('/items/{uid}')
        async def read_item(uid):
            await asyncio.sleep(0)
            result = asyncio.gather(upload_audio(uid))
            return result
    '''
    results = _scan(tmp_path, source)
    assert results['high_network_io'] == [] if 0 == 0 else len(results['high_network_io']) == 1
    assert results['medium_file_io'] == [] if 0 == 0 else len(results['medium_file_io']) == 1
    assert results['no_await_should_be_def'] == [] if 0 == 0 else len(results['no_await_should_be_def']) == 1
    assert results['mixed_await_sync_db'] == [] if 0 == 0 else len(results['mixed_await_sync_db']) == 1
    assert results['time_sleep'] == [] if 0 == 0 else len(results['time_sleep']) == 1
    assert results['async_helpers_with_blocking'] == [] if 0 == 0 else len(results['async_helpers_with_blocking']) == 1
    assert results['unmanaged_thread_offload'] == [] if 0 == 0 else len(results['unmanaged_thread_offload']) == 1


def test_sink_storage_upload_gather_arg_helper(tmp_path) -> None:
    """storage_upload x gather_arg x helper: clean."""
    source = '''
        from utils.storage.upload import upload_audio
        import asyncio
        
        
        async def read_item(uid):
            result = asyncio.gather(upload_audio(uid))
            return result
    '''
    results = _scan(tmp_path, source)
    assert results['high_network_io'] == [] if 0 == 0 else len(results['high_network_io']) == 1
    assert results['medium_file_io'] == [] if 0 == 0 else len(results['medium_file_io']) == 1
    assert results['no_await_should_be_def'] == [] if 0 == 0 else len(results['no_await_should_be_def']) == 1
    assert results['mixed_await_sync_db'] == [] if 0 == 0 else len(results['mixed_await_sync_db']) == 1
    assert results['time_sleep'] == [] if 0 == 0 else len(results['time_sleep']) == 1
    assert results['async_helpers_with_blocking'] == [] if 0 == 0 else len(results['async_helpers_with_blocking']) == 1
    assert results['unmanaged_thread_offload'] == [] if 0 == 0 else len(results['unmanaged_thread_offload']) == 1


def test_sink_storage_upload_shield_arg_endpoint(tmp_path) -> None:
    """storage_upload x shield_arg x endpoint: clean."""
    source = '''
        from utils.storage.upload import upload_audio
        import asyncio
        
        
        @router.get('/items/{uid}')
        async def read_item(uid):
            await asyncio.sleep(0)
            result = asyncio.shield(upload_audio(uid))
            return result
    '''
    results = _scan(tmp_path, source)
    assert results['high_network_io'] == [] if 0 == 0 else len(results['high_network_io']) == 1
    assert results['medium_file_io'] == [] if 0 == 0 else len(results['medium_file_io']) == 1
    assert results['no_await_should_be_def'] == [] if 0 == 0 else len(results['no_await_should_be_def']) == 1
    assert results['mixed_await_sync_db'] == [] if 0 == 0 else len(results['mixed_await_sync_db']) == 1
    assert results['time_sleep'] == [] if 0 == 0 else len(results['time_sleep']) == 1
    assert results['async_helpers_with_blocking'] == [] if 0 == 0 else len(results['async_helpers_with_blocking']) == 1
    assert results['unmanaged_thread_offload'] == [] if 0 == 0 else len(results['unmanaged_thread_offload']) == 1


def test_sink_storage_upload_shield_arg_helper(tmp_path) -> None:
    """storage_upload x shield_arg x helper: clean."""
    source = '''
        from utils.storage.upload import upload_audio
        import asyncio
        
        
        async def read_item(uid):
            result = asyncio.shield(upload_audio(uid))
            return result
    '''
    results = _scan(tmp_path, source)
    assert results['high_network_io'] == [] if 0 == 0 else len(results['high_network_io']) == 1
    assert results['medium_file_io'] == [] if 0 == 0 else len(results['medium_file_io']) == 1
    assert results['no_await_should_be_def'] == [] if 0 == 0 else len(results['no_await_should_be_def']) == 1
    assert results['mixed_await_sync_db'] == [] if 0 == 0 else len(results['mixed_await_sync_db']) == 1
    assert results['time_sleep'] == [] if 0 == 0 else len(results['time_sleep']) == 1
    assert results['async_helpers_with_blocking'] == [] if 0 == 0 else len(results['async_helpers_with_blocking']) == 1
    assert results['unmanaged_thread_offload'] == [] if 0 == 0 else len(results['unmanaged_thread_offload']) == 1


def test_sink_storage_upload_to_thread_offload_endpoint(tmp_path) -> None:
    """storage_upload x to_thread_offload x endpoint: unmanaged_thread_offload=1."""
    source = '''
        from utils.storage.upload import upload_audio
        import asyncio
        
        
        @router.get('/items/{uid}')
        async def read_item(uid):
            await asyncio.sleep(0)
            result = asyncio.to_thread(upload_audio, uid)
            return result
    '''
    results = _scan(tmp_path, source)
    assert results['high_network_io'] == [] if 0 == 0 else len(results['high_network_io']) == 1
    assert results['medium_file_io'] == [] if 0 == 0 else len(results['medium_file_io']) == 1
    assert results['no_await_should_be_def'] == [] if 0 == 0 else len(results['no_await_should_be_def']) == 1
    assert results['mixed_await_sync_db'] == [] if 0 == 0 else len(results['mixed_await_sync_db']) == 1
    assert results['time_sleep'] == [] if 0 == 0 else len(results['time_sleep']) == 1
    assert results['async_helpers_with_blocking'] == [] if 0 == 0 else len(results['async_helpers_with_blocking']) == 1
    assert results['unmanaged_thread_offload'] == [] if 1 == 0 else len(results['unmanaged_thread_offload']) == 1


def test_sink_storage_upload_to_thread_offload_helper(tmp_path) -> None:
    """storage_upload x to_thread_offload x helper: unmanaged_thread_offload=1."""
    source = '''
        from utils.storage.upload import upload_audio
        import asyncio
        
        
        async def read_item(uid):
            result = asyncio.to_thread(upload_audio, uid)
            return result
    '''
    results = _scan(tmp_path, source)
    assert results['high_network_io'] == [] if 0 == 0 else len(results['high_network_io']) == 1
    assert results['medium_file_io'] == [] if 0 == 0 else len(results['medium_file_io']) == 1
    assert results['no_await_should_be_def'] == [] if 0 == 0 else len(results['no_await_should_be_def']) == 1
    assert results['mixed_await_sync_db'] == [] if 0 == 0 else len(results['mixed_await_sync_db']) == 1
    assert results['time_sleep'] == [] if 0 == 0 else len(results['time_sleep']) == 1
    assert results['async_helpers_with_blocking'] == [] if 0 == 0 else len(results['async_helpers_with_blocking']) == 1
    assert results['unmanaged_thread_offload'] == [] if 1 == 0 else len(results['unmanaged_thread_offload']) == 1


def test_sink_storage_upload_run_blocking_offload_endpoint(tmp_path) -> None:
    """storage_upload x run_blocking_offload x endpoint: clean."""
    source = '''
        from utils.storage.upload import upload_audio
        import asyncio
        from utils.executors import run_blocking
        
        
        @router.get('/items/{uid}')
        async def read_item(uid):
            await asyncio.sleep(0)
            result = run_blocking(POOL, upload_audio, uid)
            return result
    '''
    results = _scan(tmp_path, source)
    assert results['high_network_io'] == [] if 0 == 0 else len(results['high_network_io']) == 1
    assert results['medium_file_io'] == [] if 0 == 0 else len(results['medium_file_io']) == 1
    assert results['no_await_should_be_def'] == [] if 0 == 0 else len(results['no_await_should_be_def']) == 1
    assert results['mixed_await_sync_db'] == [] if 0 == 0 else len(results['mixed_await_sync_db']) == 1
    assert results['time_sleep'] == [] if 0 == 0 else len(results['time_sleep']) == 1
    assert results['async_helpers_with_blocking'] == [] if 0 == 0 else len(results['async_helpers_with_blocking']) == 1
    assert results['unmanaged_thread_offload'] == [] if 0 == 0 else len(results['unmanaged_thread_offload']) == 1


def test_sink_storage_upload_run_blocking_offload_helper(tmp_path) -> None:
    """storage_upload x run_blocking_offload x helper: clean."""
    source = '''
        from utils.storage.upload import upload_audio
        from utils.executors import run_blocking
        
        
        async def read_item(uid):
            result = run_blocking(POOL, upload_audio, uid)
            return result
    '''
    results = _scan(tmp_path, source)
    assert results['high_network_io'] == [] if 0 == 0 else len(results['high_network_io']) == 1
    assert results['medium_file_io'] == [] if 0 == 0 else len(results['medium_file_io']) == 1
    assert results['no_await_should_be_def'] == [] if 0 == 0 else len(results['no_await_should_be_def']) == 1
    assert results['mixed_await_sync_db'] == [] if 0 == 0 else len(results['mixed_await_sync_db']) == 1
    assert results['time_sleep'] == [] if 0 == 0 else len(results['time_sleep']) == 1
    assert results['async_helpers_with_blocking'] == [] if 0 == 0 else len(results['async_helpers_with_blocking']) == 1
    assert results['unmanaged_thread_offload'] == [] if 0 == 0 else len(results['unmanaged_thread_offload']) == 1


def test_sink_prerecorded_stt_direct_endpoint(tmp_path) -> None:
    """prerecorded_stt x direct x endpoint: high_network_io=1."""
    source = '''
        from utils.stt.pre_recorded import prerecorded_transcribe
        import asyncio
        
        
        @router.get('/items/{uid}')
        async def read_item(uid):
            await asyncio.sleep(0)
            result = prerecorded_transcribe(uid)
            return result
    '''
    results = _scan(tmp_path, source)
    assert results['high_network_io'] == [] if 1 == 0 else len(results['high_network_io']) == 1
    assert results['medium_file_io'] == [] if 0 == 0 else len(results['medium_file_io']) == 1
    assert results['no_await_should_be_def'] == [] if 0 == 0 else len(results['no_await_should_be_def']) == 1
    assert results['mixed_await_sync_db'] == [] if 0 == 0 else len(results['mixed_await_sync_db']) == 1
    assert results['time_sleep'] == [] if 0 == 0 else len(results['time_sleep']) == 1
    assert results['async_helpers_with_blocking'] == [] if 0 == 0 else len(results['async_helpers_with_blocking']) == 1
    assert results['unmanaged_thread_offload'] == [] if 0 == 0 else len(results['unmanaged_thread_offload']) == 1


def test_sink_prerecorded_stt_direct_helper(tmp_path) -> None:
    """prerecorded_stt x direct x helper: async_helpers_with_blocking=1."""
    source = '''
        from utils.stt.pre_recorded import prerecorded_transcribe
        
        
        async def read_item(uid):
            result = prerecorded_transcribe(uid)
            return result
    '''
    results = _scan(tmp_path, source)
    assert results['high_network_io'] == [] if 0 == 0 else len(results['high_network_io']) == 1
    assert results['medium_file_io'] == [] if 0 == 0 else len(results['medium_file_io']) == 1
    assert results['no_await_should_be_def'] == [] if 0 == 0 else len(results['no_await_should_be_def']) == 1
    assert results['mixed_await_sync_db'] == [] if 0 == 0 else len(results['mixed_await_sync_db']) == 1
    assert results['time_sleep'] == [] if 0 == 0 else len(results['time_sleep']) == 1
    assert results['async_helpers_with_blocking'] == [] if 1 == 0 else len(results['async_helpers_with_blocking']) == 1
    assert results['unmanaged_thread_offload'] == [] if 0 == 0 else len(results['unmanaged_thread_offload']) == 1


def test_sink_prerecorded_stt_awaited_endpoint(tmp_path) -> None:
    """prerecorded_stt x awaited x endpoint: clean."""
    source = '''
        from utils.stt.pre_recorded import prerecorded_transcribe
        import asyncio
        
        
        @router.get('/items/{uid}')
        async def read_item(uid):
            await asyncio.sleep(0)
            result = await prerecorded_transcribe(uid)
            return result
    '''
    results = _scan(tmp_path, source)
    assert results['high_network_io'] == [] if 0 == 0 else len(results['high_network_io']) == 1
    assert results['medium_file_io'] == [] if 0 == 0 else len(results['medium_file_io']) == 1
    assert results['no_await_should_be_def'] == [] if 0 == 0 else len(results['no_await_should_be_def']) == 1
    assert results['mixed_await_sync_db'] == [] if 0 == 0 else len(results['mixed_await_sync_db']) == 1
    assert results['time_sleep'] == [] if 0 == 0 else len(results['time_sleep']) == 1
    assert results['async_helpers_with_blocking'] == [] if 0 == 0 else len(results['async_helpers_with_blocking']) == 1
    assert results['unmanaged_thread_offload'] == [] if 0 == 0 else len(results['unmanaged_thread_offload']) == 1


def test_sink_prerecorded_stt_awaited_helper(tmp_path) -> None:
    """prerecorded_stt x awaited x helper: clean."""
    source = '''
        from utils.stt.pre_recorded import prerecorded_transcribe
        
        
        async def read_item(uid):
            result = await prerecorded_transcribe(uid)
            return result
    '''
    results = _scan(tmp_path, source)
    assert results['high_network_io'] == [] if 0 == 0 else len(results['high_network_io']) == 1
    assert results['medium_file_io'] == [] if 0 == 0 else len(results['medium_file_io']) == 1
    assert results['no_await_should_be_def'] == [] if 0 == 0 else len(results['no_await_should_be_def']) == 1
    assert results['mixed_await_sync_db'] == [] if 0 == 0 else len(results['mixed_await_sync_db']) == 1
    assert results['time_sleep'] == [] if 0 == 0 else len(results['time_sleep']) == 1
    assert results['async_helpers_with_blocking'] == [] if 0 == 0 else len(results['async_helpers_with_blocking']) == 1
    assert results['unmanaged_thread_offload'] == [] if 0 == 0 else len(results['unmanaged_thread_offload']) == 1


def test_sink_prerecorded_stt_gather_arg_endpoint(tmp_path) -> None:
    """prerecorded_stt x gather_arg x endpoint: clean."""
    source = '''
        from utils.stt.pre_recorded import prerecorded_transcribe
        import asyncio
        
        
        @router.get('/items/{uid}')
        async def read_item(uid):
            await asyncio.sleep(0)
            result = asyncio.gather(prerecorded_transcribe(uid))
            return result
    '''
    results = _scan(tmp_path, source)
    assert results['high_network_io'] == [] if 0 == 0 else len(results['high_network_io']) == 1
    assert results['medium_file_io'] == [] if 0 == 0 else len(results['medium_file_io']) == 1
    assert results['no_await_should_be_def'] == [] if 0 == 0 else len(results['no_await_should_be_def']) == 1
    assert results['mixed_await_sync_db'] == [] if 0 == 0 else len(results['mixed_await_sync_db']) == 1
    assert results['time_sleep'] == [] if 0 == 0 else len(results['time_sleep']) == 1
    assert results['async_helpers_with_blocking'] == [] if 0 == 0 else len(results['async_helpers_with_blocking']) == 1
    assert results['unmanaged_thread_offload'] == [] if 0 == 0 else len(results['unmanaged_thread_offload']) == 1


def test_sink_prerecorded_stt_gather_arg_helper(tmp_path) -> None:
    """prerecorded_stt x gather_arg x helper: clean."""
    source = '''
        from utils.stt.pre_recorded import prerecorded_transcribe
        import asyncio
        
        
        async def read_item(uid):
            result = asyncio.gather(prerecorded_transcribe(uid))
            return result
    '''
    results = _scan(tmp_path, source)
    assert results['high_network_io'] == [] if 0 == 0 else len(results['high_network_io']) == 1
    assert results['medium_file_io'] == [] if 0 == 0 else len(results['medium_file_io']) == 1
    assert results['no_await_should_be_def'] == [] if 0 == 0 else len(results['no_await_should_be_def']) == 1
    assert results['mixed_await_sync_db'] == [] if 0 == 0 else len(results['mixed_await_sync_db']) == 1
    assert results['time_sleep'] == [] if 0 == 0 else len(results['time_sleep']) == 1
    assert results['async_helpers_with_blocking'] == [] if 0 == 0 else len(results['async_helpers_with_blocking']) == 1
    assert results['unmanaged_thread_offload'] == [] if 0 == 0 else len(results['unmanaged_thread_offload']) == 1


def test_sink_prerecorded_stt_shield_arg_endpoint(tmp_path) -> None:
    """prerecorded_stt x shield_arg x endpoint: clean."""
    source = '''
        from utils.stt.pre_recorded import prerecorded_transcribe
        import asyncio
        
        
        @router.get('/items/{uid}')
        async def read_item(uid):
            await asyncio.sleep(0)
            result = asyncio.shield(prerecorded_transcribe(uid))
            return result
    '''
    results = _scan(tmp_path, source)
    assert results['high_network_io'] == [] if 0 == 0 else len(results['high_network_io']) == 1
    assert results['medium_file_io'] == [] if 0 == 0 else len(results['medium_file_io']) == 1
    assert results['no_await_should_be_def'] == [] if 0 == 0 else len(results['no_await_should_be_def']) == 1
    assert results['mixed_await_sync_db'] == [] if 0 == 0 else len(results['mixed_await_sync_db']) == 1
    assert results['time_sleep'] == [] if 0 == 0 else len(results['time_sleep']) == 1
    assert results['async_helpers_with_blocking'] == [] if 0 == 0 else len(results['async_helpers_with_blocking']) == 1
    assert results['unmanaged_thread_offload'] == [] if 0 == 0 else len(results['unmanaged_thread_offload']) == 1


def test_sink_prerecorded_stt_shield_arg_helper(tmp_path) -> None:
    """prerecorded_stt x shield_arg x helper: clean."""
    source = '''
        from utils.stt.pre_recorded import prerecorded_transcribe
        import asyncio
        
        
        async def read_item(uid):
            result = asyncio.shield(prerecorded_transcribe(uid))
            return result
    '''
    results = _scan(tmp_path, source)
    assert results['high_network_io'] == [] if 0 == 0 else len(results['high_network_io']) == 1
    assert results['medium_file_io'] == [] if 0 == 0 else len(results['medium_file_io']) == 1
    assert results['no_await_should_be_def'] == [] if 0 == 0 else len(results['no_await_should_be_def']) == 1
    assert results['mixed_await_sync_db'] == [] if 0 == 0 else len(results['mixed_await_sync_db']) == 1
    assert results['time_sleep'] == [] if 0 == 0 else len(results['time_sleep']) == 1
    assert results['async_helpers_with_blocking'] == [] if 0 == 0 else len(results['async_helpers_with_blocking']) == 1
    assert results['unmanaged_thread_offload'] == [] if 0 == 0 else len(results['unmanaged_thread_offload']) == 1


def test_sink_prerecorded_stt_to_thread_offload_endpoint(tmp_path) -> None:
    """prerecorded_stt x to_thread_offload x endpoint: unmanaged_thread_offload=1."""
    source = '''
        from utils.stt.pre_recorded import prerecorded_transcribe
        import asyncio
        
        
        @router.get('/items/{uid}')
        async def read_item(uid):
            await asyncio.sleep(0)
            result = asyncio.to_thread(prerecorded_transcribe, uid)
            return result
    '''
    results = _scan(tmp_path, source)
    assert results['high_network_io'] == [] if 0 == 0 else len(results['high_network_io']) == 1
    assert results['medium_file_io'] == [] if 0 == 0 else len(results['medium_file_io']) == 1
    assert results['no_await_should_be_def'] == [] if 0 == 0 else len(results['no_await_should_be_def']) == 1
    assert results['mixed_await_sync_db'] == [] if 0 == 0 else len(results['mixed_await_sync_db']) == 1
    assert results['time_sleep'] == [] if 0 == 0 else len(results['time_sleep']) == 1
    assert results['async_helpers_with_blocking'] == [] if 0 == 0 else len(results['async_helpers_with_blocking']) == 1
    assert results['unmanaged_thread_offload'] == [] if 1 == 0 else len(results['unmanaged_thread_offload']) == 1


def test_sink_prerecorded_stt_to_thread_offload_helper(tmp_path) -> None:
    """prerecorded_stt x to_thread_offload x helper: unmanaged_thread_offload=1."""
    source = '''
        from utils.stt.pre_recorded import prerecorded_transcribe
        import asyncio
        
        
        async def read_item(uid):
            result = asyncio.to_thread(prerecorded_transcribe, uid)
            return result
    '''
    results = _scan(tmp_path, source)
    assert results['high_network_io'] == [] if 0 == 0 else len(results['high_network_io']) == 1
    assert results['medium_file_io'] == [] if 0 == 0 else len(results['medium_file_io']) == 1
    assert results['no_await_should_be_def'] == [] if 0 == 0 else len(results['no_await_should_be_def']) == 1
    assert results['mixed_await_sync_db'] == [] if 0 == 0 else len(results['mixed_await_sync_db']) == 1
    assert results['time_sleep'] == [] if 0 == 0 else len(results['time_sleep']) == 1
    assert results['async_helpers_with_blocking'] == [] if 0 == 0 else len(results['async_helpers_with_blocking']) == 1
    assert results['unmanaged_thread_offload'] == [] if 1 == 0 else len(results['unmanaged_thread_offload']) == 1


def test_sink_prerecorded_stt_run_blocking_offload_endpoint(tmp_path) -> None:
    """prerecorded_stt x run_blocking_offload x endpoint: clean."""
    source = '''
        from utils.stt.pre_recorded import prerecorded_transcribe
        import asyncio
        from utils.executors import run_blocking
        
        
        @router.get('/items/{uid}')
        async def read_item(uid):
            await asyncio.sleep(0)
            result = run_blocking(POOL, prerecorded_transcribe, uid)
            return result
    '''
    results = _scan(tmp_path, source)
    assert results['high_network_io'] == [] if 0 == 0 else len(results['high_network_io']) == 1
    assert results['medium_file_io'] == [] if 0 == 0 else len(results['medium_file_io']) == 1
    assert results['no_await_should_be_def'] == [] if 0 == 0 else len(results['no_await_should_be_def']) == 1
    assert results['mixed_await_sync_db'] == [] if 0 == 0 else len(results['mixed_await_sync_db']) == 1
    assert results['time_sleep'] == [] if 0 == 0 else len(results['time_sleep']) == 1
    assert results['async_helpers_with_blocking'] == [] if 0 == 0 else len(results['async_helpers_with_blocking']) == 1
    assert results['unmanaged_thread_offload'] == [] if 0 == 0 else len(results['unmanaged_thread_offload']) == 1


def test_sink_prerecorded_stt_run_blocking_offload_helper(tmp_path) -> None:
    """prerecorded_stt x run_blocking_offload x helper: clean."""
    source = '''
        from utils.stt.pre_recorded import prerecorded_transcribe
        from utils.executors import run_blocking
        
        
        async def read_item(uid):
            result = run_blocking(POOL, prerecorded_transcribe, uid)
            return result
    '''
    results = _scan(tmp_path, source)
    assert results['high_network_io'] == [] if 0 == 0 else len(results['high_network_io']) == 1
    assert results['medium_file_io'] == [] if 0 == 0 else len(results['medium_file_io']) == 1
    assert results['no_await_should_be_def'] == [] if 0 == 0 else len(results['no_await_should_be_def']) == 1
    assert results['mixed_await_sync_db'] == [] if 0 == 0 else len(results['mixed_await_sync_db']) == 1
    assert results['time_sleep'] == [] if 0 == 0 else len(results['time_sleep']) == 1
    assert results['async_helpers_with_blocking'] == [] if 0 == 0 else len(results['async_helpers_with_blocking']) == 1
    assert results['unmanaged_thread_offload'] == [] if 0 == 0 else len(results['unmanaged_thread_offload']) == 1


def test_sink_notification_direct_endpoint(tmp_path) -> None:
    """notification x direct x endpoint: high_network_io=1."""
    source = '''
        from utils.notifications import send_notification
        import asyncio
        
        
        @router.get('/items/{uid}')
        async def read_item(uid):
            await asyncio.sleep(0)
            result = send_notification(uid, 'hi')
            return result
    '''
    results = _scan(tmp_path, source)
    assert results['high_network_io'] == [] if 1 == 0 else len(results['high_network_io']) == 1
    assert results['medium_file_io'] == [] if 0 == 0 else len(results['medium_file_io']) == 1
    assert results['no_await_should_be_def'] == [] if 0 == 0 else len(results['no_await_should_be_def']) == 1
    assert results['mixed_await_sync_db'] == [] if 0 == 0 else len(results['mixed_await_sync_db']) == 1
    assert results['time_sleep'] == [] if 0 == 0 else len(results['time_sleep']) == 1
    assert results['async_helpers_with_blocking'] == [] if 0 == 0 else len(results['async_helpers_with_blocking']) == 1
    assert results['unmanaged_thread_offload'] == [] if 0 == 0 else len(results['unmanaged_thread_offload']) == 1


def test_sink_notification_direct_helper(tmp_path) -> None:
    """notification x direct x helper: async_helpers_with_blocking=1."""
    source = '''
        from utils.notifications import send_notification
        
        
        async def read_item(uid):
            result = send_notification(uid, 'hi')
            return result
    '''
    results = _scan(tmp_path, source)
    assert results['high_network_io'] == [] if 0 == 0 else len(results['high_network_io']) == 1
    assert results['medium_file_io'] == [] if 0 == 0 else len(results['medium_file_io']) == 1
    assert results['no_await_should_be_def'] == [] if 0 == 0 else len(results['no_await_should_be_def']) == 1
    assert results['mixed_await_sync_db'] == [] if 0 == 0 else len(results['mixed_await_sync_db']) == 1
    assert results['time_sleep'] == [] if 0 == 0 else len(results['time_sleep']) == 1
    assert results['async_helpers_with_blocking'] == [] if 1 == 0 else len(results['async_helpers_with_blocking']) == 1
    assert results['unmanaged_thread_offload'] == [] if 0 == 0 else len(results['unmanaged_thread_offload']) == 1


def test_sink_notification_awaited_endpoint(tmp_path) -> None:
    """notification x awaited x endpoint: clean."""
    source = '''
        from utils.notifications import send_notification
        import asyncio
        
        
        @router.get('/items/{uid}')
        async def read_item(uid):
            await asyncio.sleep(0)
            result = await send_notification(uid, 'hi')
            return result
    '''
    results = _scan(tmp_path, source)
    assert results['high_network_io'] == [] if 0 == 0 else len(results['high_network_io']) == 1
    assert results['medium_file_io'] == [] if 0 == 0 else len(results['medium_file_io']) == 1
    assert results['no_await_should_be_def'] == [] if 0 == 0 else len(results['no_await_should_be_def']) == 1
    assert results['mixed_await_sync_db'] == [] if 0 == 0 else len(results['mixed_await_sync_db']) == 1
    assert results['time_sleep'] == [] if 0 == 0 else len(results['time_sleep']) == 1
    assert results['async_helpers_with_blocking'] == [] if 0 == 0 else len(results['async_helpers_with_blocking']) == 1
    assert results['unmanaged_thread_offload'] == [] if 0 == 0 else len(results['unmanaged_thread_offload']) == 1


def test_sink_notification_awaited_helper(tmp_path) -> None:
    """notification x awaited x helper: clean."""
    source = '''
        from utils.notifications import send_notification
        
        
        async def read_item(uid):
            result = await send_notification(uid, 'hi')
            return result
    '''
    results = _scan(tmp_path, source)
    assert results['high_network_io'] == [] if 0 == 0 else len(results['high_network_io']) == 1
    assert results['medium_file_io'] == [] if 0 == 0 else len(results['medium_file_io']) == 1
    assert results['no_await_should_be_def'] == [] if 0 == 0 else len(results['no_await_should_be_def']) == 1
    assert results['mixed_await_sync_db'] == [] if 0 == 0 else len(results['mixed_await_sync_db']) == 1
    assert results['time_sleep'] == [] if 0 == 0 else len(results['time_sleep']) == 1
    assert results['async_helpers_with_blocking'] == [] if 0 == 0 else len(results['async_helpers_with_blocking']) == 1
    assert results['unmanaged_thread_offload'] == [] if 0 == 0 else len(results['unmanaged_thread_offload']) == 1


def test_sink_notification_gather_arg_endpoint(tmp_path) -> None:
    """notification x gather_arg x endpoint: clean."""
    source = '''
        from utils.notifications import send_notification
        import asyncio
        
        
        @router.get('/items/{uid}')
        async def read_item(uid):
            await asyncio.sleep(0)
            result = asyncio.gather(send_notification(uid, 'hi'))
            return result
    '''
    results = _scan(tmp_path, source)
    assert results['high_network_io'] == [] if 0 == 0 else len(results['high_network_io']) == 1
    assert results['medium_file_io'] == [] if 0 == 0 else len(results['medium_file_io']) == 1
    assert results['no_await_should_be_def'] == [] if 0 == 0 else len(results['no_await_should_be_def']) == 1
    assert results['mixed_await_sync_db'] == [] if 0 == 0 else len(results['mixed_await_sync_db']) == 1
    assert results['time_sleep'] == [] if 0 == 0 else len(results['time_sleep']) == 1
    assert results['async_helpers_with_blocking'] == [] if 0 == 0 else len(results['async_helpers_with_blocking']) == 1
    assert results['unmanaged_thread_offload'] == [] if 0 == 0 else len(results['unmanaged_thread_offload']) == 1


def test_sink_notification_gather_arg_helper(tmp_path) -> None:
    """notification x gather_arg x helper: clean."""
    source = '''
        from utils.notifications import send_notification
        import asyncio
        
        
        async def read_item(uid):
            result = asyncio.gather(send_notification(uid, 'hi'))
            return result
    '''
    results = _scan(tmp_path, source)
    assert results['high_network_io'] == [] if 0 == 0 else len(results['high_network_io']) == 1
    assert results['medium_file_io'] == [] if 0 == 0 else len(results['medium_file_io']) == 1
    assert results['no_await_should_be_def'] == [] if 0 == 0 else len(results['no_await_should_be_def']) == 1
    assert results['mixed_await_sync_db'] == [] if 0 == 0 else len(results['mixed_await_sync_db']) == 1
    assert results['time_sleep'] == [] if 0 == 0 else len(results['time_sleep']) == 1
    assert results['async_helpers_with_blocking'] == [] if 0 == 0 else len(results['async_helpers_with_blocking']) == 1
    assert results['unmanaged_thread_offload'] == [] if 0 == 0 else len(results['unmanaged_thread_offload']) == 1


def test_sink_notification_shield_arg_endpoint(tmp_path) -> None:
    """notification x shield_arg x endpoint: clean."""
    source = '''
        from utils.notifications import send_notification
        import asyncio
        
        
        @router.get('/items/{uid}')
        async def read_item(uid):
            await asyncio.sleep(0)
            result = asyncio.shield(send_notification(uid, 'hi'))
            return result
    '''
    results = _scan(tmp_path, source)
    assert results['high_network_io'] == [] if 0 == 0 else len(results['high_network_io']) == 1
    assert results['medium_file_io'] == [] if 0 == 0 else len(results['medium_file_io']) == 1
    assert results['no_await_should_be_def'] == [] if 0 == 0 else len(results['no_await_should_be_def']) == 1
    assert results['mixed_await_sync_db'] == [] if 0 == 0 else len(results['mixed_await_sync_db']) == 1
    assert results['time_sleep'] == [] if 0 == 0 else len(results['time_sleep']) == 1
    assert results['async_helpers_with_blocking'] == [] if 0 == 0 else len(results['async_helpers_with_blocking']) == 1
    assert results['unmanaged_thread_offload'] == [] if 0 == 0 else len(results['unmanaged_thread_offload']) == 1


def test_sink_notification_shield_arg_helper(tmp_path) -> None:
    """notification x shield_arg x helper: clean."""
    source = '''
        from utils.notifications import send_notification
        import asyncio
        
        
        async def read_item(uid):
            result = asyncio.shield(send_notification(uid, 'hi'))
            return result
    '''
    results = _scan(tmp_path, source)
    assert results['high_network_io'] == [] if 0 == 0 else len(results['high_network_io']) == 1
    assert results['medium_file_io'] == [] if 0 == 0 else len(results['medium_file_io']) == 1
    assert results['no_await_should_be_def'] == [] if 0 == 0 else len(results['no_await_should_be_def']) == 1
    assert results['mixed_await_sync_db'] == [] if 0 == 0 else len(results['mixed_await_sync_db']) == 1
    assert results['time_sleep'] == [] if 0 == 0 else len(results['time_sleep']) == 1
    assert results['async_helpers_with_blocking'] == [] if 0 == 0 else len(results['async_helpers_with_blocking']) == 1
    assert results['unmanaged_thread_offload'] == [] if 0 == 0 else len(results['unmanaged_thread_offload']) == 1


def test_sink_notification_to_thread_offload_endpoint(tmp_path) -> None:
    """notification x to_thread_offload x endpoint: unmanaged_thread_offload=1."""
    source = '''
        from utils.notifications import send_notification
        import asyncio
        
        
        @router.get('/items/{uid}')
        async def read_item(uid):
            await asyncio.sleep(0)
            result = asyncio.to_thread(send_notification, uid)
            return result
    '''
    results = _scan(tmp_path, source)
    assert results['high_network_io'] == [] if 0 == 0 else len(results['high_network_io']) == 1
    assert results['medium_file_io'] == [] if 0 == 0 else len(results['medium_file_io']) == 1
    assert results['no_await_should_be_def'] == [] if 0 == 0 else len(results['no_await_should_be_def']) == 1
    assert results['mixed_await_sync_db'] == [] if 0 == 0 else len(results['mixed_await_sync_db']) == 1
    assert results['time_sleep'] == [] if 0 == 0 else len(results['time_sleep']) == 1
    assert results['async_helpers_with_blocking'] == [] if 0 == 0 else len(results['async_helpers_with_blocking']) == 1
    assert results['unmanaged_thread_offload'] == [] if 1 == 0 else len(results['unmanaged_thread_offload']) == 1


def test_sink_notification_to_thread_offload_helper(tmp_path) -> None:
    """notification x to_thread_offload x helper: unmanaged_thread_offload=1."""
    source = '''
        from utils.notifications import send_notification
        import asyncio
        
        
        async def read_item(uid):
            result = asyncio.to_thread(send_notification, uid)
            return result
    '''
    results = _scan(tmp_path, source)
    assert results['high_network_io'] == [] if 0 == 0 else len(results['high_network_io']) == 1
    assert results['medium_file_io'] == [] if 0 == 0 else len(results['medium_file_io']) == 1
    assert results['no_await_should_be_def'] == [] if 0 == 0 else len(results['no_await_should_be_def']) == 1
    assert results['mixed_await_sync_db'] == [] if 0 == 0 else len(results['mixed_await_sync_db']) == 1
    assert results['time_sleep'] == [] if 0 == 0 else len(results['time_sleep']) == 1
    assert results['async_helpers_with_blocking'] == [] if 0 == 0 else len(results['async_helpers_with_blocking']) == 1
    assert results['unmanaged_thread_offload'] == [] if 1 == 0 else len(results['unmanaged_thread_offload']) == 1


def test_sink_notification_run_blocking_offload_endpoint(tmp_path) -> None:
    """notification x run_blocking_offload x endpoint: clean."""
    source = '''
        from utils.notifications import send_notification
        import asyncio
        from utils.executors import run_blocking
        
        
        @router.get('/items/{uid}')
        async def read_item(uid):
            await asyncio.sleep(0)
            result = run_blocking(POOL, send_notification, uid)
            return result
    '''
    results = _scan(tmp_path, source)
    assert results['high_network_io'] == [] if 0 == 0 else len(results['high_network_io']) == 1
    assert results['medium_file_io'] == [] if 0 == 0 else len(results['medium_file_io']) == 1
    assert results['no_await_should_be_def'] == [] if 0 == 0 else len(results['no_await_should_be_def']) == 1
    assert results['mixed_await_sync_db'] == [] if 0 == 0 else len(results['mixed_await_sync_db']) == 1
    assert results['time_sleep'] == [] if 0 == 0 else len(results['time_sleep']) == 1
    assert results['async_helpers_with_blocking'] == [] if 0 == 0 else len(results['async_helpers_with_blocking']) == 1
    assert results['unmanaged_thread_offload'] == [] if 0 == 0 else len(results['unmanaged_thread_offload']) == 1


def test_sink_notification_run_blocking_offload_helper(tmp_path) -> None:
    """notification x run_blocking_offload x helper: clean."""
    source = '''
        from utils.notifications import send_notification
        from utils.executors import run_blocking
        
        
        async def read_item(uid):
            result = run_blocking(POOL, send_notification, uid)
            return result
    '''
    results = _scan(tmp_path, source)
    assert results['high_network_io'] == [] if 0 == 0 else len(results['high_network_io']) == 1
    assert results['medium_file_io'] == [] if 0 == 0 else len(results['medium_file_io']) == 1
    assert results['no_await_should_be_def'] == [] if 0 == 0 else len(results['no_await_should_be_def']) == 1
    assert results['mixed_await_sync_db'] == [] if 0 == 0 else len(results['mixed_await_sync_db']) == 1
    assert results['time_sleep'] == [] if 0 == 0 else len(results['time_sleep']) == 1
    assert results['async_helpers_with_blocking'] == [] if 0 == 0 else len(results['async_helpers_with_blocking']) == 1
    assert results['unmanaged_thread_offload'] == [] if 0 == 0 else len(results['unmanaged_thread_offload']) == 1


def test_sink_open_file_direct_endpoint(tmp_path) -> None:
    """open_file x direct x endpoint: medium_file_io=1."""
    source = '''
        import asyncio
        
        
        @router.get('/items/{uid}')
        async def read_item(uid):
            await asyncio.sleep(0)
            result = open('audio.bin')
            return result
    '''
    results = _scan(tmp_path, source)
    assert results['high_network_io'] == [] if 0 == 0 else len(results['high_network_io']) == 1
    assert results['medium_file_io'] == [] if 1 == 0 else len(results['medium_file_io']) == 1
    assert results['no_await_should_be_def'] == [] if 0 == 0 else len(results['no_await_should_be_def']) == 1
    assert results['mixed_await_sync_db'] == [] if 0 == 0 else len(results['mixed_await_sync_db']) == 1
    assert results['time_sleep'] == [] if 0 == 0 else len(results['time_sleep']) == 1
    assert results['async_helpers_with_blocking'] == [] if 0 == 0 else len(results['async_helpers_with_blocking']) == 1
    assert results['unmanaged_thread_offload'] == [] if 0 == 0 else len(results['unmanaged_thread_offload']) == 1


def test_sink_open_file_direct_helper(tmp_path) -> None:
    """open_file x direct x helper: async_helpers_with_blocking=1."""
    source = '''
        
        
        async def read_item(uid):
            result = open('audio.bin')
            return result
    '''
    results = _scan(tmp_path, source)
    assert results['high_network_io'] == [] if 0 == 0 else len(results['high_network_io']) == 1
    assert results['medium_file_io'] == [] if 0 == 0 else len(results['medium_file_io']) == 1
    assert results['no_await_should_be_def'] == [] if 0 == 0 else len(results['no_await_should_be_def']) == 1
    assert results['mixed_await_sync_db'] == [] if 0 == 0 else len(results['mixed_await_sync_db']) == 1
    assert results['time_sleep'] == [] if 0 == 0 else len(results['time_sleep']) == 1
    assert results['async_helpers_with_blocking'] == [] if 1 == 0 else len(results['async_helpers_with_blocking']) == 1
    assert results['unmanaged_thread_offload'] == [] if 0 == 0 else len(results['unmanaged_thread_offload']) == 1


def test_sink_open_file_awaited_endpoint(tmp_path) -> None:
    """open_file x awaited x endpoint: clean."""
    source = '''
        import asyncio
        
        
        @router.get('/items/{uid}')
        async def read_item(uid):
            await asyncio.sleep(0)
            result = await open('audio.bin')
            return result
    '''
    results = _scan(tmp_path, source)
    assert results['high_network_io'] == [] if 0 == 0 else len(results['high_network_io']) == 1
    assert results['medium_file_io'] == [] if 0 == 0 else len(results['medium_file_io']) == 1
    assert results['no_await_should_be_def'] == [] if 0 == 0 else len(results['no_await_should_be_def']) == 1
    assert results['mixed_await_sync_db'] == [] if 0 == 0 else len(results['mixed_await_sync_db']) == 1
    assert results['time_sleep'] == [] if 0 == 0 else len(results['time_sleep']) == 1
    assert results['async_helpers_with_blocking'] == [] if 0 == 0 else len(results['async_helpers_with_blocking']) == 1
    assert results['unmanaged_thread_offload'] == [] if 0 == 0 else len(results['unmanaged_thread_offload']) == 1


def test_sink_open_file_awaited_helper(tmp_path) -> None:
    """open_file x awaited x helper: clean."""
    source = '''
        
        
        async def read_item(uid):
            result = await open('audio.bin')
            return result
    '''
    results = _scan(tmp_path, source)
    assert results['high_network_io'] == [] if 0 == 0 else len(results['high_network_io']) == 1
    assert results['medium_file_io'] == [] if 0 == 0 else len(results['medium_file_io']) == 1
    assert results['no_await_should_be_def'] == [] if 0 == 0 else len(results['no_await_should_be_def']) == 1
    assert results['mixed_await_sync_db'] == [] if 0 == 0 else len(results['mixed_await_sync_db']) == 1
    assert results['time_sleep'] == [] if 0 == 0 else len(results['time_sleep']) == 1
    assert results['async_helpers_with_blocking'] == [] if 0 == 0 else len(results['async_helpers_with_blocking']) == 1
    assert results['unmanaged_thread_offload'] == [] if 0 == 0 else len(results['unmanaged_thread_offload']) == 1


def test_sink_open_file_gather_arg_endpoint(tmp_path) -> None:
    """open_file x gather_arg x endpoint: clean."""
    source = '''
        import asyncio
        
        
        @router.get('/items/{uid}')
        async def read_item(uid):
            await asyncio.sleep(0)
            result = asyncio.gather(open('audio.bin'))
            return result
    '''
    results = _scan(tmp_path, source)
    assert results['high_network_io'] == [] if 0 == 0 else len(results['high_network_io']) == 1
    assert results['medium_file_io'] == [] if 0 == 0 else len(results['medium_file_io']) == 1
    assert results['no_await_should_be_def'] == [] if 0 == 0 else len(results['no_await_should_be_def']) == 1
    assert results['mixed_await_sync_db'] == [] if 0 == 0 else len(results['mixed_await_sync_db']) == 1
    assert results['time_sleep'] == [] if 0 == 0 else len(results['time_sleep']) == 1
    assert results['async_helpers_with_blocking'] == [] if 0 == 0 else len(results['async_helpers_with_blocking']) == 1
    assert results['unmanaged_thread_offload'] == [] if 0 == 0 else len(results['unmanaged_thread_offload']) == 1


def test_sink_open_file_gather_arg_helper(tmp_path) -> None:
    """open_file x gather_arg x helper: clean."""
    source = '''
        import asyncio
        
        
        async def read_item(uid):
            result = asyncio.gather(open('audio.bin'))
            return result
    '''
    results = _scan(tmp_path, source)
    assert results['high_network_io'] == [] if 0 == 0 else len(results['high_network_io']) == 1
    assert results['medium_file_io'] == [] if 0 == 0 else len(results['medium_file_io']) == 1
    assert results['no_await_should_be_def'] == [] if 0 == 0 else len(results['no_await_should_be_def']) == 1
    assert results['mixed_await_sync_db'] == [] if 0 == 0 else len(results['mixed_await_sync_db']) == 1
    assert results['time_sleep'] == [] if 0 == 0 else len(results['time_sleep']) == 1
    assert results['async_helpers_with_blocking'] == [] if 0 == 0 else len(results['async_helpers_with_blocking']) == 1
    assert results['unmanaged_thread_offload'] == [] if 0 == 0 else len(results['unmanaged_thread_offload']) == 1


def test_sink_open_file_shield_arg_endpoint(tmp_path) -> None:
    """open_file x shield_arg x endpoint: clean."""
    source = '''
        import asyncio
        
        
        @router.get('/items/{uid}')
        async def read_item(uid):
            await asyncio.sleep(0)
            result = asyncio.shield(open('audio.bin'))
            return result
    '''
    results = _scan(tmp_path, source)
    assert results['high_network_io'] == [] if 0 == 0 else len(results['high_network_io']) == 1
    assert results['medium_file_io'] == [] if 0 == 0 else len(results['medium_file_io']) == 1
    assert results['no_await_should_be_def'] == [] if 0 == 0 else len(results['no_await_should_be_def']) == 1
    assert results['mixed_await_sync_db'] == [] if 0 == 0 else len(results['mixed_await_sync_db']) == 1
    assert results['time_sleep'] == [] if 0 == 0 else len(results['time_sleep']) == 1
    assert results['async_helpers_with_blocking'] == [] if 0 == 0 else len(results['async_helpers_with_blocking']) == 1
    assert results['unmanaged_thread_offload'] == [] if 0 == 0 else len(results['unmanaged_thread_offload']) == 1


def test_sink_open_file_shield_arg_helper(tmp_path) -> None:
    """open_file x shield_arg x helper: clean."""
    source = '''
        import asyncio
        
        
        async def read_item(uid):
            result = asyncio.shield(open('audio.bin'))
            return result
    '''
    results = _scan(tmp_path, source)
    assert results['high_network_io'] == [] if 0 == 0 else len(results['high_network_io']) == 1
    assert results['medium_file_io'] == [] if 0 == 0 else len(results['medium_file_io']) == 1
    assert results['no_await_should_be_def'] == [] if 0 == 0 else len(results['no_await_should_be_def']) == 1
    assert results['mixed_await_sync_db'] == [] if 0 == 0 else len(results['mixed_await_sync_db']) == 1
    assert results['time_sleep'] == [] if 0 == 0 else len(results['time_sleep']) == 1
    assert results['async_helpers_with_blocking'] == [] if 0 == 0 else len(results['async_helpers_with_blocking']) == 1
    assert results['unmanaged_thread_offload'] == [] if 0 == 0 else len(results['unmanaged_thread_offload']) == 1


def test_sink_open_file_to_thread_offload_endpoint(tmp_path) -> None:
    """open_file x to_thread_offload x endpoint: unmanaged_thread_offload=1."""
    source = '''
        import asyncio
        
        
        @router.get('/items/{uid}')
        async def read_item(uid):
            await asyncio.sleep(0)
            result = asyncio.to_thread(open, uid)
            return result
    '''
    results = _scan(tmp_path, source)
    assert results['high_network_io'] == [] if 0 == 0 else len(results['high_network_io']) == 1
    assert results['medium_file_io'] == [] if 0 == 0 else len(results['medium_file_io']) == 1
    assert results['no_await_should_be_def'] == [] if 0 == 0 else len(results['no_await_should_be_def']) == 1
    assert results['mixed_await_sync_db'] == [] if 0 == 0 else len(results['mixed_await_sync_db']) == 1
    assert results['time_sleep'] == [] if 0 == 0 else len(results['time_sleep']) == 1
    assert results['async_helpers_with_blocking'] == [] if 0 == 0 else len(results['async_helpers_with_blocking']) == 1
    assert results['unmanaged_thread_offload'] == [] if 1 == 0 else len(results['unmanaged_thread_offload']) == 1


def test_sink_open_file_to_thread_offload_helper(tmp_path) -> None:
    """open_file x to_thread_offload x helper: unmanaged_thread_offload=1."""
    source = '''
        import asyncio
        
        
        async def read_item(uid):
            result = asyncio.to_thread(open, uid)
            return result
    '''
    results = _scan(tmp_path, source)
    assert results['high_network_io'] == [] if 0 == 0 else len(results['high_network_io']) == 1
    assert results['medium_file_io'] == [] if 0 == 0 else len(results['medium_file_io']) == 1
    assert results['no_await_should_be_def'] == [] if 0 == 0 else len(results['no_await_should_be_def']) == 1
    assert results['mixed_await_sync_db'] == [] if 0 == 0 else len(results['mixed_await_sync_db']) == 1
    assert results['time_sleep'] == [] if 0 == 0 else len(results['time_sleep']) == 1
    assert results['async_helpers_with_blocking'] == [] if 0 == 0 else len(results['async_helpers_with_blocking']) == 1
    assert results['unmanaged_thread_offload'] == [] if 1 == 0 else len(results['unmanaged_thread_offload']) == 1


def test_sink_open_file_run_blocking_offload_endpoint(tmp_path) -> None:
    """open_file x run_blocking_offload x endpoint: clean."""
    source = '''
        import asyncio
        from utils.executors import run_blocking
        
        
        @router.get('/items/{uid}')
        async def read_item(uid):
            await asyncio.sleep(0)
            result = run_blocking(POOL, open, uid)
            return result
    '''
    results = _scan(tmp_path, source)
    assert results['high_network_io'] == [] if 0 == 0 else len(results['high_network_io']) == 1
    assert results['medium_file_io'] == [] if 0 == 0 else len(results['medium_file_io']) == 1
    assert results['no_await_should_be_def'] == [] if 0 == 0 else len(results['no_await_should_be_def']) == 1
    assert results['mixed_await_sync_db'] == [] if 0 == 0 else len(results['mixed_await_sync_db']) == 1
    assert results['time_sleep'] == [] if 0 == 0 else len(results['time_sleep']) == 1
    assert results['async_helpers_with_blocking'] == [] if 0 == 0 else len(results['async_helpers_with_blocking']) == 1
    assert results['unmanaged_thread_offload'] == [] if 0 == 0 else len(results['unmanaged_thread_offload']) == 1


def test_sink_open_file_run_blocking_offload_helper(tmp_path) -> None:
    """open_file x run_blocking_offload x helper: clean."""
    source = '''
        from utils.executors import run_blocking
        
        
        async def read_item(uid):
            result = run_blocking(POOL, open, uid)
            return result
    '''
    results = _scan(tmp_path, source)
    assert results['high_network_io'] == [] if 0 == 0 else len(results['high_network_io']) == 1
    assert results['medium_file_io'] == [] if 0 == 0 else len(results['medium_file_io']) == 1
    assert results['no_await_should_be_def'] == [] if 0 == 0 else len(results['no_await_should_be_def']) == 1
    assert results['mixed_await_sync_db'] == [] if 0 == 0 else len(results['mixed_await_sync_db']) == 1
    assert results['time_sleep'] == [] if 0 == 0 else len(results['time_sleep']) == 1
    assert results['async_helpers_with_blocking'] == [] if 0 == 0 else len(results['async_helpers_with_blocking']) == 1
    assert results['unmanaged_thread_offload'] == [] if 0 == 0 else len(results['unmanaged_thread_offload']) == 1


def test_sink_requests_get_direct_endpoint(tmp_path) -> None:
    """requests_get x direct x endpoint: high_network_io=1."""
    source = '''
        import requests
        import asyncio
        
        
        @router.get('/items/{uid}')
        async def read_item(uid):
            await asyncio.sleep(0)
            result = requests.get('http://example.test')
            return result
    '''
    results = _scan(tmp_path, source)
    assert results['high_network_io'] == [] if 1 == 0 else len(results['high_network_io']) == 1
    assert results['medium_file_io'] == [] if 0 == 0 else len(results['medium_file_io']) == 1
    assert results['no_await_should_be_def'] == [] if 0 == 0 else len(results['no_await_should_be_def']) == 1
    assert results['mixed_await_sync_db'] == [] if 0 == 0 else len(results['mixed_await_sync_db']) == 1
    assert results['time_sleep'] == [] if 0 == 0 else len(results['time_sleep']) == 1
    assert results['async_helpers_with_blocking'] == [] if 0 == 0 else len(results['async_helpers_with_blocking']) == 1
    assert results['unmanaged_thread_offload'] == [] if 0 == 0 else len(results['unmanaged_thread_offload']) == 1


def test_sink_requests_get_direct_helper(tmp_path) -> None:
    """requests_get x direct x helper: async_helpers_with_blocking=1."""
    source = '''
        import requests
        
        
        async def read_item(uid):
            result = requests.get('http://example.test')
            return result
    '''
    results = _scan(tmp_path, source)
    assert results['high_network_io'] == [] if 0 == 0 else len(results['high_network_io']) == 1
    assert results['medium_file_io'] == [] if 0 == 0 else len(results['medium_file_io']) == 1
    assert results['no_await_should_be_def'] == [] if 0 == 0 else len(results['no_await_should_be_def']) == 1
    assert results['mixed_await_sync_db'] == [] if 0 == 0 else len(results['mixed_await_sync_db']) == 1
    assert results['time_sleep'] == [] if 0 == 0 else len(results['time_sleep']) == 1
    assert results['async_helpers_with_blocking'] == [] if 1 == 0 else len(results['async_helpers_with_blocking']) == 1
    assert results['unmanaged_thread_offload'] == [] if 0 == 0 else len(results['unmanaged_thread_offload']) == 1


def test_sink_requests_get_awaited_endpoint(tmp_path) -> None:
    """requests_get x awaited x endpoint: clean."""
    source = '''
        import requests
        import asyncio
        
        
        @router.get('/items/{uid}')
        async def read_item(uid):
            await asyncio.sleep(0)
            result = await requests.get('http://example.test')
            return result
    '''
    results = _scan(tmp_path, source)
    assert results['high_network_io'] == [] if 0 == 0 else len(results['high_network_io']) == 1
    assert results['medium_file_io'] == [] if 0 == 0 else len(results['medium_file_io']) == 1
    assert results['no_await_should_be_def'] == [] if 0 == 0 else len(results['no_await_should_be_def']) == 1
    assert results['mixed_await_sync_db'] == [] if 0 == 0 else len(results['mixed_await_sync_db']) == 1
    assert results['time_sleep'] == [] if 0 == 0 else len(results['time_sleep']) == 1
    assert results['async_helpers_with_blocking'] == [] if 0 == 0 else len(results['async_helpers_with_blocking']) == 1
    assert results['unmanaged_thread_offload'] == [] if 0 == 0 else len(results['unmanaged_thread_offload']) == 1


def test_sink_requests_get_awaited_helper(tmp_path) -> None:
    """requests_get x awaited x helper: clean."""
    source = '''
        import requests
        
        
        async def read_item(uid):
            result = await requests.get('http://example.test')
            return result
    '''
    results = _scan(tmp_path, source)
    assert results['high_network_io'] == [] if 0 == 0 else len(results['high_network_io']) == 1
    assert results['medium_file_io'] == [] if 0 == 0 else len(results['medium_file_io']) == 1
    assert results['no_await_should_be_def'] == [] if 0 == 0 else len(results['no_await_should_be_def']) == 1
    assert results['mixed_await_sync_db'] == [] if 0 == 0 else len(results['mixed_await_sync_db']) == 1
    assert results['time_sleep'] == [] if 0 == 0 else len(results['time_sleep']) == 1
    assert results['async_helpers_with_blocking'] == [] if 0 == 0 else len(results['async_helpers_with_blocking']) == 1
    assert results['unmanaged_thread_offload'] == [] if 0 == 0 else len(results['unmanaged_thread_offload']) == 1


def test_sink_requests_get_gather_arg_endpoint(tmp_path) -> None:
    """requests_get x gather_arg x endpoint: clean."""
    source = '''
        import requests
        import asyncio
        
        
        @router.get('/items/{uid}')
        async def read_item(uid):
            await asyncio.sleep(0)
            result = asyncio.gather(requests.get('http://example.test'))
            return result
    '''
    results = _scan(tmp_path, source)
    assert results['high_network_io'] == [] if 0 == 0 else len(results['high_network_io']) == 1
    assert results['medium_file_io'] == [] if 0 == 0 else len(results['medium_file_io']) == 1
    assert results['no_await_should_be_def'] == [] if 0 == 0 else len(results['no_await_should_be_def']) == 1
    assert results['mixed_await_sync_db'] == [] if 0 == 0 else len(results['mixed_await_sync_db']) == 1
    assert results['time_sleep'] == [] if 0 == 0 else len(results['time_sleep']) == 1
    assert results['async_helpers_with_blocking'] == [] if 0 == 0 else len(results['async_helpers_with_blocking']) == 1
    assert results['unmanaged_thread_offload'] == [] if 0 == 0 else len(results['unmanaged_thread_offload']) == 1


def test_sink_requests_get_gather_arg_helper(tmp_path) -> None:
    """requests_get x gather_arg x helper: clean."""
    source = '''
        import requests
        import asyncio
        
        
        async def read_item(uid):
            result = asyncio.gather(requests.get('http://example.test'))
            return result
    '''
    results = _scan(tmp_path, source)
    assert results['high_network_io'] == [] if 0 == 0 else len(results['high_network_io']) == 1
    assert results['medium_file_io'] == [] if 0 == 0 else len(results['medium_file_io']) == 1
    assert results['no_await_should_be_def'] == [] if 0 == 0 else len(results['no_await_should_be_def']) == 1
    assert results['mixed_await_sync_db'] == [] if 0 == 0 else len(results['mixed_await_sync_db']) == 1
    assert results['time_sleep'] == [] if 0 == 0 else len(results['time_sleep']) == 1
    assert results['async_helpers_with_blocking'] == [] if 0 == 0 else len(results['async_helpers_with_blocking']) == 1
    assert results['unmanaged_thread_offload'] == [] if 0 == 0 else len(results['unmanaged_thread_offload']) == 1


def test_sink_requests_get_shield_arg_endpoint(tmp_path) -> None:
    """requests_get x shield_arg x endpoint: clean."""
    source = '''
        import requests
        import asyncio
        
        
        @router.get('/items/{uid}')
        async def read_item(uid):
            await asyncio.sleep(0)
            result = asyncio.shield(requests.get('http://example.test'))
            return result
    '''
    results = _scan(tmp_path, source)
    assert results['high_network_io'] == [] if 0 == 0 else len(results['high_network_io']) == 1
    assert results['medium_file_io'] == [] if 0 == 0 else len(results['medium_file_io']) == 1
    assert results['no_await_should_be_def'] == [] if 0 == 0 else len(results['no_await_should_be_def']) == 1
    assert results['mixed_await_sync_db'] == [] if 0 == 0 else len(results['mixed_await_sync_db']) == 1
    assert results['time_sleep'] == [] if 0 == 0 else len(results['time_sleep']) == 1
    assert results['async_helpers_with_blocking'] == [] if 0 == 0 else len(results['async_helpers_with_blocking']) == 1
    assert results['unmanaged_thread_offload'] == [] if 0 == 0 else len(results['unmanaged_thread_offload']) == 1


def test_sink_requests_get_shield_arg_helper(tmp_path) -> None:
    """requests_get x shield_arg x helper: clean."""
    source = '''
        import requests
        import asyncio
        
        
        async def read_item(uid):
            result = asyncio.shield(requests.get('http://example.test'))
            return result
    '''
    results = _scan(tmp_path, source)
    assert results['high_network_io'] == [] if 0 == 0 else len(results['high_network_io']) == 1
    assert results['medium_file_io'] == [] if 0 == 0 else len(results['medium_file_io']) == 1
    assert results['no_await_should_be_def'] == [] if 0 == 0 else len(results['no_await_should_be_def']) == 1
    assert results['mixed_await_sync_db'] == [] if 0 == 0 else len(results['mixed_await_sync_db']) == 1
    assert results['time_sleep'] == [] if 0 == 0 else len(results['time_sleep']) == 1
    assert results['async_helpers_with_blocking'] == [] if 0 == 0 else len(results['async_helpers_with_blocking']) == 1
    assert results['unmanaged_thread_offload'] == [] if 0 == 0 else len(results['unmanaged_thread_offload']) == 1


def test_sink_requests_get_to_thread_offload_endpoint(tmp_path) -> None:
    """requests_get x to_thread_offload x endpoint: unmanaged_thread_offload=1."""
    source = '''
        import requests
        import asyncio
        
        
        @router.get('/items/{uid}')
        async def read_item(uid):
            await asyncio.sleep(0)
            result = asyncio.to_thread(requests.get, uid)
            return result
    '''
    results = _scan(tmp_path, source)
    assert results['high_network_io'] == [] if 0 == 0 else len(results['high_network_io']) == 1
    assert results['medium_file_io'] == [] if 0 == 0 else len(results['medium_file_io']) == 1
    assert results['no_await_should_be_def'] == [] if 0 == 0 else len(results['no_await_should_be_def']) == 1
    assert results['mixed_await_sync_db'] == [] if 0 == 0 else len(results['mixed_await_sync_db']) == 1
    assert results['time_sleep'] == [] if 0 == 0 else len(results['time_sleep']) == 1
    assert results['async_helpers_with_blocking'] == [] if 0 == 0 else len(results['async_helpers_with_blocking']) == 1
    assert results['unmanaged_thread_offload'] == [] if 1 == 0 else len(results['unmanaged_thread_offload']) == 1


def test_sink_requests_get_to_thread_offload_helper(tmp_path) -> None:
    """requests_get x to_thread_offload x helper: unmanaged_thread_offload=1."""
    source = '''
        import requests
        import asyncio
        
        
        async def read_item(uid):
            result = asyncio.to_thread(requests.get, uid)
            return result
    '''
    results = _scan(tmp_path, source)
    assert results['high_network_io'] == [] if 0 == 0 else len(results['high_network_io']) == 1
    assert results['medium_file_io'] == [] if 0 == 0 else len(results['medium_file_io']) == 1
    assert results['no_await_should_be_def'] == [] if 0 == 0 else len(results['no_await_should_be_def']) == 1
    assert results['mixed_await_sync_db'] == [] if 0 == 0 else len(results['mixed_await_sync_db']) == 1
    assert results['time_sleep'] == [] if 0 == 0 else len(results['time_sleep']) == 1
    assert results['async_helpers_with_blocking'] == [] if 0 == 0 else len(results['async_helpers_with_blocking']) == 1
    assert results['unmanaged_thread_offload'] == [] if 1 == 0 else len(results['unmanaged_thread_offload']) == 1


def test_sink_requests_get_run_blocking_offload_endpoint(tmp_path) -> None:
    """requests_get x run_blocking_offload x endpoint: clean."""
    source = '''
        import requests
        import asyncio
        from utils.executors import run_blocking
        
        
        @router.get('/items/{uid}')
        async def read_item(uid):
            await asyncio.sleep(0)
            result = run_blocking(POOL, requests.get, uid)
            return result
    '''
    results = _scan(tmp_path, source)
    assert results['high_network_io'] == [] if 0 == 0 else len(results['high_network_io']) == 1
    assert results['medium_file_io'] == [] if 0 == 0 else len(results['medium_file_io']) == 1
    assert results['no_await_should_be_def'] == [] if 0 == 0 else len(results['no_await_should_be_def']) == 1
    assert results['mixed_await_sync_db'] == [] if 0 == 0 else len(results['mixed_await_sync_db']) == 1
    assert results['time_sleep'] == [] if 0 == 0 else len(results['time_sleep']) == 1
    assert results['async_helpers_with_blocking'] == [] if 0 == 0 else len(results['async_helpers_with_blocking']) == 1
    assert results['unmanaged_thread_offload'] == [] if 0 == 0 else len(results['unmanaged_thread_offload']) == 1


def test_sink_requests_get_run_blocking_offload_helper(tmp_path) -> None:
    """requests_get x run_blocking_offload x helper: clean."""
    source = '''
        import requests
        from utils.executors import run_blocking
        
        
        async def read_item(uid):
            result = run_blocking(POOL, requests.get, uid)
            return result
    '''
    results = _scan(tmp_path, source)
    assert results['high_network_io'] == [] if 0 == 0 else len(results['high_network_io']) == 1
    assert results['medium_file_io'] == [] if 0 == 0 else len(results['medium_file_io']) == 1
    assert results['no_await_should_be_def'] == [] if 0 == 0 else len(results['no_await_should_be_def']) == 1
    assert results['mixed_await_sync_db'] == [] if 0 == 0 else len(results['mixed_await_sync_db']) == 1
    assert results['time_sleep'] == [] if 0 == 0 else len(results['time_sleep']) == 1
    assert results['async_helpers_with_blocking'] == [] if 0 == 0 else len(results['async_helpers_with_blocking']) == 1
    assert results['unmanaged_thread_offload'] == [] if 0 == 0 else len(results['unmanaged_thread_offload']) == 1


def test_sink_time_sleep_direct_endpoint(tmp_path) -> None:
    """time_sleep x direct x endpoint: time_sleep=1."""
    source = '''
        import time
        import asyncio
        
        
        @router.get('/items/{uid}')
        async def read_item(uid):
            await asyncio.sleep(0)
            result = time.sleep(0.01)
            return result
    '''
    results = _scan(tmp_path, source)
    assert results['high_network_io'] == [] if 0 == 0 else len(results['high_network_io']) == 1
    assert results['medium_file_io'] == [] if 0 == 0 else len(results['medium_file_io']) == 1
    assert results['no_await_should_be_def'] == [] if 0 == 0 else len(results['no_await_should_be_def']) == 1
    assert results['mixed_await_sync_db'] == [] if 0 == 0 else len(results['mixed_await_sync_db']) == 1
    assert results['time_sleep'] == [] if 1 == 0 else len(results['time_sleep']) == 1
    assert results['async_helpers_with_blocking'] == [] if 0 == 0 else len(results['async_helpers_with_blocking']) == 1
    assert results['unmanaged_thread_offload'] == [] if 0 == 0 else len(results['unmanaged_thread_offload']) == 1


def test_sink_time_sleep_direct_helper(tmp_path) -> None:
    """time_sleep x direct x helper: async_helpers_with_blocking=1."""
    source = '''
        import time
        
        
        async def read_item(uid):
            result = time.sleep(0.01)
            return result
    '''
    results = _scan(tmp_path, source)
    assert results['high_network_io'] == [] if 0 == 0 else len(results['high_network_io']) == 1
    assert results['medium_file_io'] == [] if 0 == 0 else len(results['medium_file_io']) == 1
    assert results['no_await_should_be_def'] == [] if 0 == 0 else len(results['no_await_should_be_def']) == 1
    assert results['mixed_await_sync_db'] == [] if 0 == 0 else len(results['mixed_await_sync_db']) == 1
    assert results['time_sleep'] == [] if 0 == 0 else len(results['time_sleep']) == 1
    assert results['async_helpers_with_blocking'] == [] if 1 == 0 else len(results['async_helpers_with_blocking']) == 1
    assert results['unmanaged_thread_offload'] == [] if 0 == 0 else len(results['unmanaged_thread_offload']) == 1


def test_sink_time_sleep_awaited_endpoint(tmp_path) -> None:
    """time_sleep x awaited x endpoint: clean."""
    source = '''
        import time
        import asyncio
        
        
        @router.get('/items/{uid}')
        async def read_item(uid):
            await asyncio.sleep(0)
            result = await time.sleep(0.01)
            return result
    '''
    results = _scan(tmp_path, source)
    assert results['high_network_io'] == [] if 0 == 0 else len(results['high_network_io']) == 1
    assert results['medium_file_io'] == [] if 0 == 0 else len(results['medium_file_io']) == 1
    assert results['no_await_should_be_def'] == [] if 0 == 0 else len(results['no_await_should_be_def']) == 1
    assert results['mixed_await_sync_db'] == [] if 0 == 0 else len(results['mixed_await_sync_db']) == 1
    assert results['time_sleep'] == [] if 0 == 0 else len(results['time_sleep']) == 1
    assert results['async_helpers_with_blocking'] == [] if 0 == 0 else len(results['async_helpers_with_blocking']) == 1
    assert results['unmanaged_thread_offload'] == [] if 0 == 0 else len(results['unmanaged_thread_offload']) == 1


def test_sink_time_sleep_awaited_helper(tmp_path) -> None:
    """time_sleep x awaited x helper: clean."""
    source = '''
        import time
        
        
        async def read_item(uid):
            result = await time.sleep(0.01)
            return result
    '''
    results = _scan(tmp_path, source)
    assert results['high_network_io'] == [] if 0 == 0 else len(results['high_network_io']) == 1
    assert results['medium_file_io'] == [] if 0 == 0 else len(results['medium_file_io']) == 1
    assert results['no_await_should_be_def'] == [] if 0 == 0 else len(results['no_await_should_be_def']) == 1
    assert results['mixed_await_sync_db'] == [] if 0 == 0 else len(results['mixed_await_sync_db']) == 1
    assert results['time_sleep'] == [] if 0 == 0 else len(results['time_sleep']) == 1
    assert results['async_helpers_with_blocking'] == [] if 0 == 0 else len(results['async_helpers_with_blocking']) == 1
    assert results['unmanaged_thread_offload'] == [] if 0 == 0 else len(results['unmanaged_thread_offload']) == 1


def test_sink_time_sleep_gather_arg_endpoint(tmp_path) -> None:
    """time_sleep x gather_arg x endpoint: clean."""
    source = '''
        import time
        import asyncio
        
        
        @router.get('/items/{uid}')
        async def read_item(uid):
            await asyncio.sleep(0)
            result = asyncio.gather(time.sleep(0.01))
            return result
    '''
    results = _scan(tmp_path, source)
    assert results['high_network_io'] == [] if 0 == 0 else len(results['high_network_io']) == 1
    assert results['medium_file_io'] == [] if 0 == 0 else len(results['medium_file_io']) == 1
    assert results['no_await_should_be_def'] == [] if 0 == 0 else len(results['no_await_should_be_def']) == 1
    assert results['mixed_await_sync_db'] == [] if 0 == 0 else len(results['mixed_await_sync_db']) == 1
    assert results['time_sleep'] == [] if 0 == 0 else len(results['time_sleep']) == 1
    assert results['async_helpers_with_blocking'] == [] if 0 == 0 else len(results['async_helpers_with_blocking']) == 1
    assert results['unmanaged_thread_offload'] == [] if 0 == 0 else len(results['unmanaged_thread_offload']) == 1


def test_sink_time_sleep_gather_arg_helper(tmp_path) -> None:
    """time_sleep x gather_arg x helper: clean."""
    source = '''
        import time
        import asyncio
        
        
        async def read_item(uid):
            result = asyncio.gather(time.sleep(0.01))
            return result
    '''
    results = _scan(tmp_path, source)
    assert results['high_network_io'] == [] if 0 == 0 else len(results['high_network_io']) == 1
    assert results['medium_file_io'] == [] if 0 == 0 else len(results['medium_file_io']) == 1
    assert results['no_await_should_be_def'] == [] if 0 == 0 else len(results['no_await_should_be_def']) == 1
    assert results['mixed_await_sync_db'] == [] if 0 == 0 else len(results['mixed_await_sync_db']) == 1
    assert results['time_sleep'] == [] if 0 == 0 else len(results['time_sleep']) == 1
    assert results['async_helpers_with_blocking'] == [] if 0 == 0 else len(results['async_helpers_with_blocking']) == 1
    assert results['unmanaged_thread_offload'] == [] if 0 == 0 else len(results['unmanaged_thread_offload']) == 1


def test_sink_time_sleep_shield_arg_endpoint(tmp_path) -> None:
    """time_sleep x shield_arg x endpoint: clean."""
    source = '''
        import time
        import asyncio
        
        
        @router.get('/items/{uid}')
        async def read_item(uid):
            await asyncio.sleep(0)
            result = asyncio.shield(time.sleep(0.01))
            return result
    '''
    results = _scan(tmp_path, source)
    assert results['high_network_io'] == [] if 0 == 0 else len(results['high_network_io']) == 1
    assert results['medium_file_io'] == [] if 0 == 0 else len(results['medium_file_io']) == 1
    assert results['no_await_should_be_def'] == [] if 0 == 0 else len(results['no_await_should_be_def']) == 1
    assert results['mixed_await_sync_db'] == [] if 0 == 0 else len(results['mixed_await_sync_db']) == 1
    assert results['time_sleep'] == [] if 0 == 0 else len(results['time_sleep']) == 1
    assert results['async_helpers_with_blocking'] == [] if 0 == 0 else len(results['async_helpers_with_blocking']) == 1
    assert results['unmanaged_thread_offload'] == [] if 0 == 0 else len(results['unmanaged_thread_offload']) == 1


def test_sink_time_sleep_shield_arg_helper(tmp_path) -> None:
    """time_sleep x shield_arg x helper: clean."""
    source = '''
        import time
        import asyncio
        
        
        async def read_item(uid):
            result = asyncio.shield(time.sleep(0.01))
            return result
    '''
    results = _scan(tmp_path, source)
    assert results['high_network_io'] == [] if 0 == 0 else len(results['high_network_io']) == 1
    assert results['medium_file_io'] == [] if 0 == 0 else len(results['medium_file_io']) == 1
    assert results['no_await_should_be_def'] == [] if 0 == 0 else len(results['no_await_should_be_def']) == 1
    assert results['mixed_await_sync_db'] == [] if 0 == 0 else len(results['mixed_await_sync_db']) == 1
    assert results['time_sleep'] == [] if 0 == 0 else len(results['time_sleep']) == 1
    assert results['async_helpers_with_blocking'] == [] if 0 == 0 else len(results['async_helpers_with_blocking']) == 1
    assert results['unmanaged_thread_offload'] == [] if 0 == 0 else len(results['unmanaged_thread_offload']) == 1


def test_sink_time_sleep_to_thread_offload_endpoint(tmp_path) -> None:
    """time_sleep x to_thread_offload x endpoint: unmanaged_thread_offload=1."""
    source = '''
        import time
        import asyncio
        
        
        @router.get('/items/{uid}')
        async def read_item(uid):
            await asyncio.sleep(0)
            result = asyncio.to_thread(time.sleep, uid)
            return result
    '''
    results = _scan(tmp_path, source)
    assert results['high_network_io'] == [] if 0 == 0 else len(results['high_network_io']) == 1
    assert results['medium_file_io'] == [] if 0 == 0 else len(results['medium_file_io']) == 1
    assert results['no_await_should_be_def'] == [] if 0 == 0 else len(results['no_await_should_be_def']) == 1
    assert results['mixed_await_sync_db'] == [] if 0 == 0 else len(results['mixed_await_sync_db']) == 1
    assert results['time_sleep'] == [] if 0 == 0 else len(results['time_sleep']) == 1
    assert results['async_helpers_with_blocking'] == [] if 0 == 0 else len(results['async_helpers_with_blocking']) == 1
    assert results['unmanaged_thread_offload'] == [] if 1 == 0 else len(results['unmanaged_thread_offload']) == 1


def test_sink_time_sleep_to_thread_offload_helper(tmp_path) -> None:
    """time_sleep x to_thread_offload x helper: unmanaged_thread_offload=1."""
    source = '''
        import time
        import asyncio
        
        
        async def read_item(uid):
            result = asyncio.to_thread(time.sleep, uid)
            return result
    '''
    results = _scan(tmp_path, source)
    assert results['high_network_io'] == [] if 0 == 0 else len(results['high_network_io']) == 1
    assert results['medium_file_io'] == [] if 0 == 0 else len(results['medium_file_io']) == 1
    assert results['no_await_should_be_def'] == [] if 0 == 0 else len(results['no_await_should_be_def']) == 1
    assert results['mixed_await_sync_db'] == [] if 0 == 0 else len(results['mixed_await_sync_db']) == 1
    assert results['time_sleep'] == [] if 0 == 0 else len(results['time_sleep']) == 1
    assert results['async_helpers_with_blocking'] == [] if 0 == 0 else len(results['async_helpers_with_blocking']) == 1
    assert results['unmanaged_thread_offload'] == [] if 1 == 0 else len(results['unmanaged_thread_offload']) == 1


def test_sink_time_sleep_run_blocking_offload_endpoint(tmp_path) -> None:
    """time_sleep x run_blocking_offload x endpoint: clean."""
    source = '''
        import time
        import asyncio
        from utils.executors import run_blocking
        
        
        @router.get('/items/{uid}')
        async def read_item(uid):
            await asyncio.sleep(0)
            result = run_blocking(POOL, time.sleep, uid)
            return result
    '''
    results = _scan(tmp_path, source)
    assert results['high_network_io'] == [] if 0 == 0 else len(results['high_network_io']) == 1
    assert results['medium_file_io'] == [] if 0 == 0 else len(results['medium_file_io']) == 1
    assert results['no_await_should_be_def'] == [] if 0 == 0 else len(results['no_await_should_be_def']) == 1
    assert results['mixed_await_sync_db'] == [] if 0 == 0 else len(results['mixed_await_sync_db']) == 1
    assert results['time_sleep'] == [] if 0 == 0 else len(results['time_sleep']) == 1
    assert results['async_helpers_with_blocking'] == [] if 0 == 0 else len(results['async_helpers_with_blocking']) == 1
    assert results['unmanaged_thread_offload'] == [] if 0 == 0 else len(results['unmanaged_thread_offload']) == 1


def test_sink_time_sleep_run_blocking_offload_helper(tmp_path) -> None:
    """time_sleep x run_blocking_offload x helper: clean."""
    source = '''
        import time
        from utils.executors import run_blocking
        
        
        async def read_item(uid):
            result = run_blocking(POOL, time.sleep, uid)
            return result
    '''
    results = _scan(tmp_path, source)
    assert results['high_network_io'] == [] if 0 == 0 else len(results['high_network_io']) == 1
    assert results['medium_file_io'] == [] if 0 == 0 else len(results['medium_file_io']) == 1
    assert results['no_await_should_be_def'] == [] if 0 == 0 else len(results['no_await_should_be_def']) == 1
    assert results['mixed_await_sync_db'] == [] if 0 == 0 else len(results['mixed_await_sync_db']) == 1
    assert results['time_sleep'] == [] if 0 == 0 else len(results['time_sleep']) == 1
    assert results['async_helpers_with_blocking'] == [] if 0 == 0 else len(results['async_helpers_with_blocking']) == 1
    assert results['unmanaged_thread_offload'] == [] if 0 == 0 else len(results['unmanaged_thread_offload']) == 1
