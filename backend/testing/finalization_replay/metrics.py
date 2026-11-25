"""Per-case provider-token estimates and Firestore SDK operation counts."""

from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
from datetime import datetime
from functools import lru_cache
import json
from threading import Lock

_ACTIVE_STATE = None
_ACTIVE_LOCK = Lock()
_METER_SUSPENDED = ContextVar('finalization_replay_meter_suspended', default=False)
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


def prompt_content(value):
    """Extract prompt text from Python messages or the jobd replay input envelope."""
    if not isinstance(value, str):
        return _content(value)
    try:
        request = json.loads(value)
    except (TypeError, ValueError):
        return [value]
    if not isinstance(request, dict) or not isinstance(request.get('prompt'), str):
        return [value]
    transcript = request.get('transcript')
    if not isinstance(transcript, list) or not all(isinstance(item, str) for item in transcript):
        return [value]
    return [request['prompt'], *transcript]


def prompt_token_estimate(value) -> int:
    """Count content text on the shared Python messages/jobd input basis."""
    return len(_encoding().encode('\n'.join(prompt_content(value))))


def embedding_token_estimate(value) -> int:
    """Count text embeddings with the pinned encoding and token-ID inputs exactly."""
    if type(value) is int:
        return 1
    if isinstance(value, (list, tuple)):
        if all(type(token) is int for token in value):
            return len(value)
        return sum(embedding_token_estimate(item) for item in value)
    if isinstance(value, (str, dict)):
        return token_estimate(value)
    return 0


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


@contextmanager
def suspend_meter():
    """Exclude harness reads in this context while other workers remain metered."""
    token = _METER_SUSPENDED.set(True)
    try:
        yield
    finally:
        _METER_SUSPENDED.reset(token)


def _active_state():
    if _METER_SUSPENDED.get():
        return None
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


def _field(value, name, default=None):
    if isinstance(value, dict):
        return value.get(name, default)
    return getattr(value, name, default)


def query_document_name(response):
    """A RunQuery response contributes a document read only if it has a document name."""
    return _field(_field(response, 'document'), 'name', '')


def _matches_batch_privacy_document(state, name):
    path = getattr(state, 'batch_privacy_document_path', '')
    if not isinstance(name, str) or not path:
        return False
    marker = '/documents/'
    resource = name.split(marker, 1)[1] if marker in name else name
    return resource.strip('/') == path


def _write_document_name(write):
    return (
        _field(write, 'delete', '')
        or _field(_field(write, 'update', {}), 'name', '')
        or _field(_field(write, 'transform', {}), 'document', '')
        or ''
    )


def _direct_write_document_name(name, request):
    document_name = _field(request, 'name', '') or _field(_field(request, 'document', {}), 'name', '')
    if document_name or name != 'create_document':
        return document_name
    parent = _field(request, 'parent', '') or ''
    collection = _field(request, 'collection_id', '') or ''
    document_id = _field(request, 'document_id', '') or ''
    if parent and collection and document_id:
        return f'{parent.rstrip("/")}/{collection}/{document_id}'
    return ''


def _batch_privacy_read_count(state, name, request):
    path = getattr(state, 'batch_privacy_document_path', '')
    if not path:
        return 0
    if name == 'get_document':
        return int(_matches_batch_privacy_document(state, _field(request, 'name', '')))
    if name == 'batch_get_documents':
        return sum(
            _matches_batch_privacy_document(state, document) for document in (_field(request, 'documents', ()) or ())
        )
    if name == 'list_documents':
        parent = _field(request, 'parent', '') or ''
        collection = _field(request, 'collection_id', '') or ''
        return int(collection == 'batch_pipeline_privacy' and parent.rstrip('/').endswith('/documents'))
    if name in {'run_query', 'run_aggregation_query'}:
        query = _field(request, 'structured_query', {}) or {}
        if name == 'run_aggregation_query':
            aggregation = _field(request, 'structured_aggregation_query', {}) or {}
            query = _field(aggregation, 'structured_query', query) or query
        sources = _field(query, 'from_', _field(query, 'from', ())) or ()
        targets_collection = any(_field(source, 'collection_id', '') == 'batch_pipeline_privacy' for source in sources)
        parent = _field(request, 'parent', '') or ''
        return int(targets_collection and parent.rstrip('/').endswith('/documents'))
    return 0


def _matches_home_dirty_receipt(state, name):
    path = getattr(state, 'home_dirty_receipt_path', '')
    if not isinstance(name, str) or not path:
        return False
    marker = '/documents/'
    resource = name.split(marker, 1)[1] if marker in name else name
    return resource.strip('/') == path


def _home_dirty_value(fields):
    if fields is None:
        return None, False
    try:
        if 'home_dirty' not in fields:
            return None, False
    except TypeError:
        return None, False
    value = fields['home_dirty']
    if isinstance(value, bool):
        return value, True
    value = getattr(value, '_pb', value)
    try:
        if value.WhichOneof('value_type') == 'boolean_value':
            return value.boolean_value, True
    except (AttributeError, ValueError):
        pass
    return None, True


def _record_home_receipt_write(state, name, fields):
    if not _matches_home_dirty_receipt(state, name):
        return
    value, present = _home_dirty_value(fields)
    if present:
        state.record_home_dirty_receipt_write(value)


def _delete_write(write):
    if isinstance(write, dict):
        return 'delete' in write and write['delete'] is not None
    try:
        return write.WhichOneof('operation') == 'delete'
    except (AttributeError, ValueError):
        return bool(getattr(write, 'delete', ''))


def _capture_parity_write(state, name, fields, *, committed_at=None, deleted=False, paths=()):
    if not hasattr(state, 'profile_writes'):
        return
    path = name.split('/documents/', 1)[-1]
    if len(path.split('/')) == 4 and path.split('/')[2] == 'action_items':
        with state._metrics_lock:
            state.task_writes.append(path if not deleted else '')
    if path != f'users/{state.uid}' or not (
        deleted or 'ai_user_profile' in fields or any(p.split('.', 1)[0] == 'ai_user_profile' for p in paths)
    ):
        return
    profile = fields.get('ai_user_profile')
    values = _field(_field(profile, 'map_value'), 'fields', {}) or {}
    event = {field: _field(values.get(field), 'string_value', '') for field in ('generated_at', 'refreshed_at')}
    if isinstance(committed_at, datetime):
        event['observed_at'] = committed_at.isoformat()
    with state._metrics_lock:
        state.profile_writes.append(event)


def _count_write_request(state, request, response=None, *, partial=False):
    writes = _writes(request)
    if not writes:
        return
    deletes = sum(_delete_write(write) for write in writes)
    privacy_writes = privacy_deletes = 0
    statuses = _field(response, 'status', ()) if partial else None
    results = _field(response, 'write_results', ()) or ()
    for index, write in enumerate(writes):
        name = _write_document_name(write)
        update = _field(write, 'update', {}) or {}
        fields = _field(update, 'fields', {}) or {}
        if statuses is None or (index < len(statuses) and statuses[index].code == 0):
            _capture_parity_write(
                state,
                name,
                fields,
                committed_at=_field(results[index], 'update_time') if index < len(results) else None,
                deleted=_delete_write(write),
                paths=_field(_field(write, 'update_mask'), 'field_paths', ()) or (),
            )
        if _delete_write(write):
            if _matches_home_dirty_receipt(state, name):
                state.record_home_dirty_receipt_write('deleted')
        else:
            _record_home_receipt_write(state, name, fields)
        if _matches_batch_privacy_document(state, name):
            if _delete_write(write):
                privacy_deletes += 1
            else:
                privacy_writes += 1
    state.add_firestore_operations(
        writes=len(writes) - deletes,
        deletes=deletes,
        batch_pipeline_privacy_document_writes=privacy_writes,
        batch_pipeline_privacy_document_deletes=privacy_deletes,
    )


def _invoke_rpc(state, name, read_methods, call, *args, **kwargs):
    if state is not None:
        state.add_firestore_operations(
            rpc_calls=1,
            query_requests=int(name in {'run_query', 'run_aggregation_query'}),
            document_reads=int(name in read_methods),
        )
        privacy_reads = _batch_privacy_read_count(state, name, _request(args, kwargs))
        if privacy_reads:
            state.add_firestore_operations(batch_pipeline_privacy_document_reads=privacy_reads)
    return call(*args, **kwargs)


def _is_read_result(method, item):
    if method == 'batch_get_documents':
        try:
            return item.WhichOneof('result') in {'found', 'missing'}
        except (AttributeError, ValueError):
            return bool(getattr(item, 'found', None) or getattr(item, 'missing', None))
    if method == 'run_query':
        return bool(query_document_name(item))
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
    """Count emulator RPCs made by Python; the Go child uses firestore_proxy."""
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
                request = _request(args, kwargs)
                result = _invoke_rpc(state, name, reads, call, self, *args, **kwargs)
                if state is None:
                    return result
                if name in direct_writes:
                    deleted = name == 'delete_document'
                    counts = {'deletes': int(deleted), 'writes': int(not deleted)}
                    if _matches_batch_privacy_document(state, _direct_write_document_name(name, request)):
                        counts[
                            (
                                'batch_pipeline_privacy_document_deletes'
                                if deleted
                                else 'batch_pipeline_privacy_document_writes'
                            )
                        ] = 1
                    state.add_firestore_operations(**counts)
                    document = _field(request, 'document', {}) or {}
                    document_name = _direct_write_document_name(name, request)
                    fields = _field(document, 'fields', {}) or {}
                    _capture_parity_write(
                        state,
                        document_name,
                        fields,
                        committed_at=_field(result, 'update_time'),
                        deleted=deleted,
                        paths=_field(_field(request, 'update_mask'), 'field_paths', ()) or (),
                    )
                    if deleted:
                        if _matches_home_dirty_receipt(state, document_name):
                            state.record_home_dirty_receipt_write('deleted')
                    else:
                        _record_home_receipt_write(state, document_name, fields)
                elif name in batched_writes:
                    _count_write_request(state, request, result, partial=name == 'batch_write')
                if name in streams:
                    return _wrap_stream(result, name, state)
                return result

            return wrapped

        setattr(FirestoreClient, method, make_wrapper(method, original))
    _METER_INSTALLED = True
