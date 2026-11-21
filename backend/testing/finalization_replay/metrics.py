"""Per-case provider-token estimates and Firestore SDK operation counts."""

from __future__ import annotations

from contextlib import contextmanager
from functools import lru_cache
from threading import Lock

_ACTIVE_STATE = None
_ACTIVE_LOCK = Lock()
_METER_INSTALLED = False


@lru_cache(maxsize=1)
def _encoding():
    import tiktoken

    return tiktoken.get_encoding('cl100k_base')


def _content(value):
    if isinstance(value, str):
        return [value]
    if isinstance(value, dict):
        if 'content' in value:
            return _content(value['content'])
        return [text for child in value.values() for text in _content(child)]
    if isinstance(value, (list, tuple)):
        return [text for child in value for text in _content(child)]
    return []


def token_estimate(value) -> int:
    """Count content tokens with the pinned local encoding, excluding API framing."""
    return len(_encoding().encode('\n'.join(_content(value))))


@contextmanager
def measure(state):
    global _ACTIVE_STATE
    with _ACTIVE_LOCK:
        if _ACTIVE_STATE is not None:
            raise RuntimeError('nested finalization replay cost measurement')
        _ACTIVE_STATE = state
        state.cost_measured = True
    try:
        yield
    finally:
        with _ACTIVE_LOCK:
            _ACTIVE_STATE = None


def _active_state():
    with _ACTIVE_LOCK:
        return _ACTIVE_STATE


def _request(args, kwargs):
    if 'request' in kwargs:
        return kwargs['request']
    return args[0] if args else None


def _writes(request):
    if request is None:
        return ()
    if isinstance(request, dict):
        return request.get('writes', ())
    return getattr(request, 'writes', ())


def _delete_write(write):
    if isinstance(write, dict):
        return bool(write.get('delete'))
    try:
        return write.WhichOneof('operation') == 'delete'
    except (AttributeError, ValueError):
        return bool(getattr(write, 'delete', ''))


def _count_write_request(state, request):
    writes = _writes(request)
    if not writes:
        return
    deletes = sum(_delete_write(write) for write in writes)
    state.add_firestore_operations(writes=len(writes) - deletes, deletes=deletes)


def _is_read_result(method, item):
    if method == 'batch_get_documents':
        try:
            return item.WhichOneof('result') in {'found', 'missing'}
        except (AttributeError, ValueError):
            return bool(getattr(item, 'found', None) or getattr(item, 'missing', None))
    if method == 'run_query':
        return getattr(item, 'document', None) is not None
    if method == 'list_documents':
        return True
    return False


def _wrap_stream(result, method, state):
    def counted():
        for item in result:
            if _is_read_result(method, item):
                bucket = 'query_documents' if method in {'run_query', 'list_documents'} else 'document_reads'
                state.add_firestore_operations(**{bucket: 1})
            yield item

    return counted()


def install_firestore_meter():
    """Count emulator RPCs made by both the Python reference and Go shim."""
    global _METER_INSTALLED
    if _METER_INSTALLED:
        return

    from google.cloud.firestore_v1.services.firestore.client import FirestoreClient

    streams = {'batch_get_documents', 'run_query', 'list_documents'}
    reads = {'get_document'}
    direct_writes = {'create_document', 'update_document', 'delete_document'}
    batched_writes = {'commit', 'batch_write'}
    for method in reads | streams | direct_writes | batched_writes | {'run_aggregation_query'}:
        original = getattr(FirestoreClient, method)

        def make_wrapper(name, call):
            def wrapped(self, *args, **kwargs):
                state = _active_state()
                if state is not None:
                    query = int(name in {'run_query', 'run_aggregation_query'})
                    state.add_firestore_operations(rpc_calls=1, query_requests=query)
                request = _request(args, kwargs)
                result = call(self, *args, **kwargs)
                if state is None:
                    return result
                if name in reads:
                    state.add_firestore_operations(document_reads=1)
                elif name in direct_writes:
                    state.add_firestore_operations(**({'deletes': 1} if name == 'delete_document' else {'writes': 1}))
                elif name in batched_writes:
                    _count_write_request(state, request)
                if name in streams:
                    return _wrap_stream(result, name, state)
                return result

            return wrapped

        setattr(FirestoreClient, method, make_wrapper(method, original))
    _METER_INSTALLED = True
