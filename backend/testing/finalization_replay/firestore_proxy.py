"""Count Firestore RPCs from the Go replay process and forward them to the emulator."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from threading import Lock

import grpc
from google.cloud.firestore_v1.types import firestore

_SERVICE = 'google.firestore.v1.Firestore'
_SERVER_STREAMING = {'batch_get_documents', 'run_query', 'run_aggregation_query', 'list_documents'}
_BIDI_STREAMING = {'write', 'listen'}
_QUERIES = {'run_query', 'run_aggregation_query', 'list_documents'}
_METHODS = (
    'get_document',
    'list_documents',
    'update_document',
    'delete_document',
    'batch_get_documents',
    'begin_transaction',
    'commit',
    'rollback',
    'run_query',
    'run_aggregation_query',
    'partition_query',
    'write',
    'listen',
    'list_collection_ids',
    'batch_write',
    'create_document',
)
_RESPONSE_TYPES = {
    'batch_get_documents': firestore.BatchGetDocumentsResponse,
    'run_query': firestore.RunQueryResponse,
    'run_aggregation_query': firestore.RunAggregationQueryResponse,
    'list_documents': firestore.ListDocumentsResponse,
}


def _pascal(method):
    return ''.join(part.title() for part in method.split('_'))


def _resource_path(name):
    marker = '/documents/'
    if not isinstance(name, str) or marker not in name:
        return ''
    return name.split(marker, 1)[1].strip('/')


def _write_path(write):
    return (
        getattr(write, 'delete', '')
        or getattr(getattr(write, 'update', None), 'name', '')
        or getattr(getattr(write, 'transform', None), 'document', '')
        or ''
    )


class FirestoreProxy:
    """A loopback generic gRPC forwarder with value-free operation counters."""

    def __init__(self, target, privacy_document_path, home_dirty_receipt_path):
        self.target = target
        self.privacy_document_path = privacy_document_path.strip('/')
        self.home_dirty_receipt_path = home_dirty_receipt_path.strip('/')
        self._lock = Lock()
        self.reset()
        self._channel = grpc.insecure_channel(target)
        self._server = grpc.server(ThreadPoolExecutor(max_workers=32))
        handlers = {}
        for method in _METHODS:
            request_type = getattr(firestore, f'{_pascal(method)}Request')
            handlers[_pascal(method)] = self._handler(method, request_type)
        self._server.add_generic_rpc_handlers((grpc.method_handlers_generic_handler(_SERVICE, handlers),))
        port = self._server.add_insecure_port('127.0.0.1:0')
        if port == 0:
            raise RuntimeError('could not bind Firestore replay proxy')
        self.address = f'127.0.0.1:{port}'

    def __enter__(self):
        self._server.start()
        return self

    def __exit__(self, *_exc):
        self._server.stop(0).wait()
        self._channel.close()

    def reset(self):
        with self._lock:
            self._counts = {
                'rpc_calls': 0,
                'document_reads': 0,
                'query_documents': 0,
                'query_requests': 0,
                'writes': 0,
                'deletes': 0,
                'batch_pipeline_privacy_document_reads': 0,
                'batch_pipeline_privacy_document_writes': 0,
                'batch_pipeline_privacy_document_deletes': 0,
            }
            self._home_receipt_trace = {'set_true': 0, 'set_false': 0, 'deleted': 0, 'other_write': 0}
            self._operation_sources = {}

    def counts(self):
        with self._lock:
            return dict(self._counts)

    def home_receipt_trace(self):
        with self._lock:
            return dict(self._home_receipt_trace)

    def operation_sources(self):
        with self._lock:
            return {path: dict(counts) for path, counts in self._operation_sources.items()}

    def _add(self, **values):
        with self._lock:
            for name, value in values.items():
                self._counts[name] += value

    def _record_operation_source(self, name, operation, count=1):
        path = _resource_path(name)
        if not path or operation not in {'reads', 'writes', 'deletes'} or not count:
            return
        with self._lock:
            source = self._operation_sources.setdefault(path, {'reads': 0, 'writes': 0, 'deletes': 0})
            source[operation] += count

    def _is_privacy_document(self, name):
        return _resource_path(name) == self.privacy_document_path

    def _is_home_dirty_receipt(self, name):
        return _resource_path(name) == self.home_dirty_receipt_path

    def _record_home_receipt(self, name, document):
        if not self._is_home_dirty_receipt(name):
            return
        fields = getattr(document, 'fields', document)
        if 'home_dirty' not in fields:
            return
        value = getattr(fields['home_dirty'], '_pb', fields['home_dirty'])
        try:
            if value.WhichOneof('value_type') == 'boolean_value':
                bucket = 'set_true' if value.boolean_value else 'set_false'
            else:
                bucket = 'other_write'
        except (AttributeError, ValueError):
            raw = fields['home_dirty']
            bucket = 'set_true' if raw is True else 'set_false' if raw is False else 'other_write'
        with self._lock:
            self._home_receipt_trace[bucket] += 1

    def _query_targets_privacy(self, request):
        parent = getattr(request, 'parent', '')
        if parent.endswith('/documents/' + self.privacy_document_path):
            return True
        if not parent.endswith('/documents'):
            return False
        query = getattr(request, 'structured_query', None)
        return bool(query) and any(
            source.collection_id == 'batch_pipeline_privacy' for source in getattr(query, 'from_', ())
        )

    def _record_request(self, method, request, count_rpc=True):
        self._add(
            rpc_calls=int(count_rpc),
            query_requests=int(method in _QUERIES),
            document_reads=int(method == 'get_document'),
        )
        if method == 'get_document':
            self._record_operation_source(getattr(request, 'name', ''), 'reads')
        if method == 'get_document' and self._is_privacy_document(getattr(request, 'name', '')):
            self._add(batch_pipeline_privacy_document_reads=1)
        elif method == 'batch_get_documents':
            privacy_reads = sum(self._is_privacy_document(name) for name in request.documents)
            self._add(batch_pipeline_privacy_document_reads=privacy_reads)
        elif method in {'run_query', 'run_aggregation_query', 'list_documents'} and self._query_targets_privacy(
            request
        ):
            # Count collection reads conservatively: a filtered query can still read the target.
            self._add(batch_pipeline_privacy_document_reads=1)
        if method in {'commit', 'batch_write', 'write'}:
            writes = getattr(request, 'writes', ())
            self._record_writes(writes)
        elif method in {'create_document', 'update_document', 'delete_document'}:
            if method == 'delete_document':
                deletes, writes = 1, 0
            else:
                deletes, writes = 0, 1
            self._add(writes=writes, deletes=deletes)
            name = getattr(request, 'name', '')
            if method == 'create_document':
                name = '/'.join(
                    part.strip('/')
                    for part in (
                        getattr(request, 'parent', ''),
                        getattr(request, 'collection_id', ''),
                        getattr(request, 'document_id', ''),
                    )
                )
            self._record_operation_source(name, 'deletes' if deletes else 'writes')
            if self._is_privacy_document(name):
                self._add(
                    batch_pipeline_privacy_document_deletes=deletes,
                    batch_pipeline_privacy_document_writes=writes,
                )

    def _record_writes(self, writes):
        deletes = sum(bool(getattr(write, 'delete', '')) for write in writes)
        count = len(writes)
        privacy_deletes = sum(
            bool(getattr(write, 'delete', '')) and self._is_privacy_document(_write_path(write)) for write in writes
        )
        privacy_writes = sum(
            not bool(getattr(write, 'delete', '')) and self._is_privacy_document(_write_path(write)) for write in writes
        )
        self._add(
            writes=count - deletes,
            deletes=deletes,
            batch_pipeline_privacy_document_writes=privacy_writes,
            batch_pipeline_privacy_document_deletes=privacy_deletes,
        )
        for write in writes:
            is_delete = bool(getattr(write, 'delete', ''))
            self._record_operation_source(_write_path(write), 'deletes' if is_delete else 'writes')

    def _record_response(self, method, raw):
        response_type = _RESPONSE_TYPES.get(method)
        if response_type is None:
            return
        response = response_type.deserialize(raw)
        if method == 'batch_get_documents':
            try:
                result = response.WhichOneof('result')
            except (AttributeError, ValueError):
                result = (
                    'found'
                    if getattr(response, 'found', None)
                    else 'missing' if getattr(response, 'missing', '') else None
                )
            if result == 'found':
                self._add(document_reads=1)
                self._record_operation_source(getattr(response.found, 'name', ''), 'reads')
            elif result == 'missing':
                self._add(document_reads=1)
                self._record_operation_source(getattr(response, 'missing', ''), 'reads')
        elif method == 'run_query':
            document = getattr(response, 'document', None)
            if document and document.name:
                self._add(query_documents=1)
                self._record_operation_source(document.name, 'reads')
        elif method == 'list_documents':
            documents = getattr(response, 'documents', ())
            self._add(query_documents=len(documents))
            for document in documents:
                self._record_operation_source(getattr(document, 'name', ''), 'reads')

    def _record_committed_home_writes(self, method, request, response):
        if method in {'commit', 'batch_write'}:
            writes = getattr(request, 'writes', ())
            if method == 'batch_write':
                statuses = getattr(firestore.BatchWriteResponse.deserialize(response), 'status', ())
                writes = [
                    write for index, write in enumerate(writes) if index >= len(statuses) or statuses[index].code == 0
                ]
            for write in writes:
                name = _write_path(write)
                if getattr(write, 'delete', ''):
                    if self._is_home_dirty_receipt(name):
                        with self._lock:
                            self._home_receipt_trace['deleted'] += 1
                else:
                    self._record_home_receipt(name, getattr(write, 'update', None))
        elif method in {'create_document', 'update_document', 'delete_document'}:
            name = getattr(request, 'name', '')
            if method == 'create_document':
                name = '/'.join(
                    part.strip('/')
                    for part in (
                        getattr(request, 'parent', ''),
                        getattr(request, 'collection_id', ''),
                        getattr(request, 'document_id', ''),
                    )
                )
            if method == 'delete_document':
                if self._is_home_dirty_receipt(name):
                    with self._lock:
                        self._home_receipt_trace['deleted'] += 1
            else:
                self._record_home_receipt(name, getattr(request, 'document', {}))
        elif method == 'write':
            for write in getattr(request, 'writes', ()):
                name = _write_path(write)
                if getattr(write, 'delete', ''):
                    if self._is_home_dirty_receipt(name):
                        with self._lock:
                            self._home_receipt_trace['deleted'] += 1
                else:
                    self._record_home_receipt(name, getattr(write, 'update', None))

    def _handler(self, method, request_type):
        path = f'/{_SERVICE}/{_pascal(method)}'

        if method in _SERVER_STREAMING:

            def serve(request_bytes, context):
                try:
                    request = request_type.deserialize(request_bytes)
                    self._record_request(method, request)
                    call = self._channel.unary_stream(
                        path, request_serializer=lambda value: value, response_deserializer=lambda value: value
                    )
                    kwargs = {'metadata': tuple((item.key, item.value) for item in context.invocation_metadata())}
                    if context.time_remaining() is not None:
                        kwargs['timeout'] = context.time_remaining()
                    for response in call(request_bytes, **kwargs):
                        self._record_response(method, response)
                        yield response
                except grpc.RpcError as error:
                    context.abort(error.code(), error.details())

            return grpc.unary_stream_rpc_method_handler(
                serve, request_deserializer=lambda value: value, response_serializer=lambda value: value
            )

        if method in _BIDI_STREAMING:

            def serve(requests, context):
                pending_requests = []
                pending_lock = Lock()

                def forwarding_requests():
                    rpc_recorded = False
                    for raw in requests:
                        request = request_type.deserialize(raw)
                        if not rpc_recorded:
                            self._add(rpc_calls=1)
                            rpc_recorded = True
                        self._record_request(method, request, count_rpc=False)
                        if method == 'write':
                            with pending_lock:
                                pending_requests.append(request)
                        yield raw

                call = self._channel.stream_stream(
                    path, request_serializer=lambda value: value, response_deserializer=lambda value: value
                )
                kwargs = {'metadata': tuple((item.key, item.value) for item in context.invocation_metadata())}
                if context.time_remaining() is not None:
                    kwargs['timeout'] = context.time_remaining()
                try:
                    for response in call(forwarding_requests(), **kwargs):
                        if method == 'write':
                            with pending_lock:
                                request = pending_requests.pop(0) if pending_requests else None
                            if request is not None:
                                self._record_committed_home_writes('write', request, response)
                        yield response
                except grpc.RpcError as error:
                    context.abort(error.code(), error.details())

            return grpc.stream_stream_rpc_method_handler(
                serve, request_deserializer=lambda value: value, response_serializer=lambda value: value
            )

        def serve(request_bytes, context):
            try:
                request = request_type.deserialize(request_bytes)
                self._record_request(method, request)
                call = self._channel.unary_unary(
                    path, request_serializer=lambda value: value, response_deserializer=lambda value: value
                )
                kwargs = {'metadata': tuple((item.key, item.value) for item in context.invocation_metadata())}
                if context.time_remaining() is not None:
                    kwargs['timeout'] = context.time_remaining()
                response = call(request_bytes, **kwargs)
                self._record_committed_home_writes(method, request, response)
                return response
            except grpc.RpcError as error:
                context.abort(error.code(), error.details())

        return grpc.unary_unary_rpc_method_handler(
            serve, request_deserializer=lambda value: value, response_serializer=lambda value: value
        )
