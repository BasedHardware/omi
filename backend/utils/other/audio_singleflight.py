"""Coalesce concurrent synchronous rebuilds; failures release admission for retry."""

import threading
import inspect
from concurrent.futures import Future
from functools import wraps

from config.audio_archive import admitted
from config.repeat_work import playback_on_demand
from utils.other.audio_archive_metrics import REBUILDS_COALESCED

_lock = threading.Lock()
_flights: dict[tuple, Future] = {}
_MAX_FLIGHTS = 2000


def coalesce_rebuild(function):
    signature = inspect.signature(function)

    @wraps(function)
    def wrapped(uid, conversation_id, *args, **kwargs):
        if not playback_on_demand() and not admitted(uid, 'COALESCE'):
            return function(uid, conversation_id, *args, **kwargs)
        bound = signature.bind(uid, conversation_id, *args, **kwargs)
        bound.apply_defaults()
        semantic = {key: value for key, value in bound.arguments.items() if key not in {'caller', 'pcm_to_wav_func'}}
        key = (function.__name__, repr(sorted(semantic.items())))
        with _lock:
            future = _flights.get(key)
            owner = future is None
            if owner:
                if len(_flights) >= _MAX_FLIGHTS:
                    raise RuntimeError('audio rebuild admission exhausted')
                future = Future()
                _flights[key] = future
        if not owner:
            REBUILDS_COALESCED.inc()
            return future.result(timeout=300)
        try:
            result = function(uid, conversation_id, *args, **kwargs)
            future.set_result(result)
            return result
        except BaseException as error:
            future.set_exception(error)
            raise
        finally:
            with _lock:
                _flights.pop(key, None)

    return wrapped
