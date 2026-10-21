import logging
import random
import re
import time
from threading import Lock
from typing import Any, Callable

import os
from google.api_core.exceptions import Aborted, DeadlineExceeded, InvalidArgument, ResourceExhausted, ServiceUnavailable
from google.cloud import firestore

from database.document_ids import document_id_from_seed
from database.firestore_transaction_retry import (
    FirestoreAborted,
    FirestoreContentionExhausted,
    equal_jitter_delay,
)
from database.google_credentials import (
    customer_data_service_account,
    customer_entitlement_service_account,
    prepare_google_credentials,
)

__all__ = [
    "data_plane_db",
    "db",
    "delete_collection_recursive",
    "document_id_from_seed",
    "FIRESTORE_DOCUMENT_KINDS",
    "firestore_document_kind",
    "firestore_error_document_path",
    "firestore_failure_reason",
    "get_customer_firestore_client",
    "get_data_plane_firestore_client",
    "get_firestore_client",
    "get_users_uid",
    "is_document_size_limit_error",
    "is_expired_transaction_error",
    "is_retryable_firestore_transaction_error",
    "run_transactional",
]

logger = logging.getLogger(__name__)


def _run_query_retry(transport: Any) -> Any:
    """The RunQuery retry policy, resolved from wherever the transport exposes it.

    ``transport.run_query`` is the RAW gRPC stub (``_UnaryStreamMultiCallable``); the
    policy lives on the wrapped method the transport built for it.
    """
    gapic_callable = transport.run_query
    retry = getattr(gapic_callable, '_retry', None)
    if retry is not None:
        return retry
    wrapped = getattr(transport, '_wrapped_methods', {}).get(gapic_callable)
    return getattr(wrapped, '_retry', None)


def _retry_query_after_exception(self: Any, exc: BaseException, retry: Any, transaction: Any) -> bool:
    """Decide whether a query stream resumes after a retryable error.

    Replaces ``Query._retry_query_after_exception``, which reads the retry policy off
    ``transport.run_query`` — the raw stub, which carries no ``_retry``. Every
    mid-stream ``ServiceUnavailable``/``DeadlineExceeded`` therefore died with
    ``AttributeError: '_UnaryStreamMultiCallable' object has no attribute '_retry'``
    instead of resuming, surfacing as a 500 on any read that streams a collection.
    """
    from google.api_core import gapic_v1

    if transaction is not None:  # no snapshot-based retry inside a transaction
        return False
    if retry is gapic_v1.method.DEFAULT:
        retry = _run_query_retry(self._client._firestore_api._transport)
        if retry is None:
            # No policy to consult: let the original provider error surface intact.
            return False
    return bool(retry._predicate(exc))


def _install_query_stream_retry_compat() -> None:
    """Bind the replacement onto the SDK's Query class.

    ``firestore_v1.query`` and ``gapic_v1`` are imported here, not at module scope:
    both pull in ``google.auth``, which unit-test harnesses that stub the ``google``
    namespace package (``testing.import_isolation.stub_modules``) cannot resolve.
    Under those stubs there is no real Query to patch, so skipping is correct.
    """
    try:
        from google.cloud.firestore_v1.query import Query
    except ImportError:
        return
    # setattr, not attribute assignment: the SDK hook is a protected member, and
    # binding it by name keeps the type checker's private-usage rule intact.
    setattr(Query, '_retry_query_after_exception', _retry_query_after_exception)


_install_query_stream_retry_compat()


def _install_document_read_probe() -> None:
    """Count every Firestore read on the SDK classes, for every client in-process.

    The patch is on the classes, not on one instance, so a later ``firestore.Client()``
    or ``AsyncClient()`` in this process is covered. A process that never imports
    this module does not install it. Same lazy-import discipline as the query retry
    shim above: the probe wraps SDK classes that do not exist under the unit-test
    import stubs.
    """
    try:
        from database.firestore_document_probe import install_document_read_probe
    except ImportError:
        return

    install_document_read_probe()


_install_document_read_probe()


def _install_action_item_write_fences() -> None:
    # Match the SDK read probe's import-isolation seam. No clients or IO here.
    try:
        from database.action_item_write_fence import install_write_fences
    except ImportError:
        return
    install_write_fences()


_install_action_item_write_fences()


_firestore_client = None
_firestore_client_lock = Lock()
_customer_firestore_client = None
_customer_firestore_client_lock = Lock()


def _firestore_database_id(project: str | None = None) -> str | None:
    """Reject named database overrides outside the emulator, except staging's own DB.

    The staging deployment (contract (i)) reads and writes the named database
    ``staging`` in ``based-hardware-dev``. That is allowed only when
    ``OMI_DEPLOYMENT=staging`` and the client's project is ``based-hardware-dev``;
    the staging isolation fence runs first, so a staging process pointed at prod
    never gets this far.
    """
    from utils.staging_fence import STAGING_DATABASE, STAGING_PROJECT, assert_staging_isolation, is_staging

    assert_staging_isolation()
    database = (os.getenv("FIRESTORE_DATABASE_ID") or "").strip()
    if not database or database == "(default)":
        return None
    if database == STAGING_DATABASE and is_staging() and project == STAGING_PROJECT:
        return database
    raise RuntimeError("FIRESTORE_DATABASE_ID is restricted to local Firestore emulators and staging")


def _client_kwargs(credentials: Any, project: str) -> dict[str, Any]:
    """Client kwargs for a pinned project; ``None`` credentials mean the runtime identity (ADC)."""
    if credentials is None:
        prepare_google_credentials()
        return {"project": project}
    return {"credentials": credentials, "project": project}


def _build_firestore_client() -> Any:
    # Production safety: only override project/database when pointed at a local
    # Firestore emulator. Without FIRESTORE_EMULATOR_HOST set (i.e. real Firestore),
    # never let bare GOOGLE_CLOUD_PROJECT (often the GKE compute project) repoint
    # the customer-data client away from SERVICE_ACCOUNT_JSON's project_id.
    if os.environ.get("FIRESTORE_EMULATOR_HOST"):
        prepare_google_credentials()
        project = os.environ.get("FIREBASE_PROJECT_ID") or os.environ.get("GOOGLE_CLOUD_PROJECT")
        database = os.environ.get("FIRESTORE_DATABASE_ID")
        kwargs: dict[str, str] = {}
        if project:
            kwargs["project"] = project
        if database:
            kwargs["database"] = database
        return firestore.Client(**kwargs)

    customer_data = customer_data_service_account()
    if customer_data is not None:
        credentials, project_id = customer_data
        database = _firestore_database_id(project_id)
        customer_kwargs: dict[str, Any] = _client_kwargs(credentials, project_id)
        if database:
            customer_kwargs["database"] = database
        return firestore.Client(**customer_kwargs)

    prepare_google_credentials()
    database = _firestore_database_id("based-hardware-dev")
    if database:
        return firestore.Client(project="based-hardware-dev", database=database)
    return firestore.Client()


def get_firestore_client() -> Any:
    global _firestore_client

    if _firestore_client is None:
        with _firestore_client_lock:
            if _firestore_client is None:
                _firestore_client = _build_firestore_client()
    return _firestore_client


def _build_customer_firestore_client() -> Any:
    """Identity, subscription, and usage — production customer project.

    Compute-local state (``agentVm``, GCE) keeps using ``get_firestore_client()``
    so development Cloud Run ADC can stay on ``based-hardware-dev``.
    """
    if os.environ.get("FIRESTORE_EMULATOR_HOST"):
        return _build_firestore_client()

    entitlements = customer_entitlement_service_account()
    if entitlements is not None:
        credentials, project_id = entitlements
        database = _firestore_database_id(project_id)
        kwargs: dict[str, Any] = _client_kwargs(credentials, project_id)
        if database:
            kwargs["database"] = database
        return firestore.Client(**kwargs)

    return get_firestore_client()


def get_customer_firestore_client() -> Any:
    global _customer_firestore_client

    if _customer_firestore_client is None:
        with _customer_firestore_client_lock:
            if _customer_firestore_client is None:
                _customer_firestore_client = _build_customer_firestore_client()
    return _customer_firestore_client


_data_plane_firestore_client = None
_data_plane_firestore_client_lock = Lock()


def _build_data_plane_firestore_client() -> Any:
    """The customer data plane for services whose compute project differs from it.

    Some deployments (desktop-backend in dev) run their compute on one GCP
    project via bare ADC (``GOOGLE_CLOUD_PROJECT``) while the user's actual
    Firestore data — the memory ledger, retained proactivity history, screen-activity
    sync — lives in a different project (see ``backend/deploy/runtime_env``'s
    ``data_plane_project``). ``OMI_FIRESTORE_DATA_PLANE_PROJECT`` names that
    project explicitly so ADC can be pinned to it instead of silently
    resolving to the compute project's empty Firestore.

    Compute-local state (``agentVm``, GCE) must keep using
    ``get_firestore_client()`` directly rather than this seam.
    """
    if os.environ.get("FIRESTORE_EMULATOR_HOST"):
        return get_firestore_client()

    data_plane_project = os.environ.get("OMI_FIRESTORE_DATA_PLANE_PROJECT", "").strip()
    if not data_plane_project:
        service = (os.getenv("K_SERVICE") or os.getenv("APP_NAME") or "").strip().casefold()
        if "desktop-backend" in service:
            raise RuntimeError("OMI_FIRESTORE_DATA_PLANE_PROJECT is required on desktop-backend")
        return get_firestore_client()
    # Resolved only once a data-plane project is pinned: without one this seam is the default client,
    # which applies its own (project-aware) named-DB check.
    database = _firestore_database_id(data_plane_project)

    # Bare ADC pinned to another project is not enough: the dev compute
    # service account has no data-plane Firestore IAM (writes came back 403
    # the first time this seam served traffic). The data-plane SA is already
    # mounted for exactly this split — SERVICE_ACCOUNT_JSON env on listen /
    # Python / jobs, FIREBASE_AUTH_CREDENTIALS_PATH file on desktop-backend —
    # so the seam pins those credentials, the same way entitlement reads do.
    pinned = customer_entitlement_service_account()
    if pinned is not None:
        credentials, sa_project = pinned
        if sa_project != data_plane_project:
            # Writing user data to whatever project the mounted SA happens to
            # serve would be silent cross-plane corruption; refuse instead.
            raise RuntimeError(
                "OMI_FIRESTORE_DATA_PLANE_PROJECT="
                f"{data_plane_project} does not match the mounted service account's "
                f"project {sa_project}"
            )
        kwargs: dict[str, Any] = _client_kwargs(credentials, data_plane_project)
        if database:
            kwargs["database"] = database
        return firestore.Client(**kwargs)

    prepare_google_credentials()
    kwargs = {"project": data_plane_project}
    if database:
        kwargs["database"] = database
    return firestore.Client(**kwargs)


def get_data_plane_firestore_client() -> Any:
    global _data_plane_firestore_client

    if _data_plane_firestore_client is None:
        with _data_plane_firestore_client_lock:
            if _data_plane_firestore_client is None:
                _data_plane_firestore_client = _build_data_plane_firestore_client()
    return _data_plane_firestore_client


_EXPIRED_TRANSACTION_MARKER = "transaction has expired"


def is_expired_transaction_error(error: BaseException) -> bool:
    """True when Firestore has retired the transaction id mid-flight.

    A commit reports that as ``InvalidArgument`` 400. A streaming read
    (``BatchGetDocuments`` / ``RunQuery``) reports the same retirement as
    ``Aborted`` 409, raised from ``google.api_core.grpc_helpers``. The SDK
    retries ``Aborted`` only when ``_commit`` raises it, and that retry reuses
    the dead id, so the read-path ``Aborted`` has to be recognized here.
    """
    return isinstance(error, (InvalidArgument, Aborted)) and _EXPIRED_TRANSACTION_MARKER in str(error).lower()


_DOCUMENT_SIZE_LIMIT_MARKER = "exceeds the maximum allowed size"

# Google RPC codes whose rejections do not change when the same write is
# retried: the row's size, its ACL, or the database's policy refuses the
# operation itself, not this attempt at it.
_PERMANENT_WRITE_CODE_MARKERS = (
    _DOCUMENT_SIZE_LIMIT_MARKER,
    "the request must be modified",  # failed_precondition envelope
    "permission denied",  # permission_denied on the row or database
    "caller does not have permission",
    "forbidden for",  # policy refusals phrased as ``... forbidden for ...``
)


def is_document_size_limit_error(error: BaseException) -> bool:
    """True for the Firestore 400 rejecting a write that would exceed the 1 MiB document ceiling.

    Unlike contention or an expired transaction, this is permanent: retrying the
    same growing write can never succeed, so callers must take a different path
    rather than loop.
    """
    return isinstance(error, InvalidArgument) and _DOCUMENT_SIZE_LIMIT_MARKER in str(error).lower()


def is_permanent_firestore_write_rejection(error: BaseException) -> bool:
    """True when Firestore refused the write itself, not this attempt at it.

    The document-size 400 is the volume case, but the same permanence holds for
    a permission-denied row and for failed-precondition policy refusals: no
    retry of the same write can succeed, so callers must move the payload to
    storage that still accepts it (or a different row) instead of looping.
    Transient classes — contention (``Aborted``), an expired transaction id,
    availability faults — return False; callers keep their retry.
    """
    if is_document_size_limit_error(error):
        return True
    message = str(error).lower()
    return any(marker in message for marker in _PERMANENT_WRITE_CODE_MARKERS[1:])


# The SDK's ``_Transactional`` raises a bare ValueError once its own attempts are spent.
_SDK_COMMIT_EXHAUSTED_PREFIX = "failed to commit transaction"


def firestore_failure_reason(error: BaseException) -> str:
    """Bounded, loggable token for why a Firestore call failed; never the message itself.

    Firestore error text names the rejected document by path, which carries the
    uid, so callers log this token (and ``firestore_document_kind``) instead.
    ``document_size_limit`` is permanent; ``expired_transaction``,
    ``contention``, ``deadline_exceeded``, ``unavailable``, and
    ``resource_exhausted`` are transient and succeed on a later attempt.
    ``resource_exhausted`` is retried only by the ``transient=True`` path.
    """
    if is_document_size_limit_error(error):
        return 'document_size_limit'
    if is_expired_transaction_error(error):
        return 'expired_transaction'
    if isinstance(error, (FirestoreAborted, FirestoreContentionExhausted)) or (
        type(error) is ValueError and str(error).lower().startswith(_SDK_COMMIT_EXHAUSTED_PREFIX)
    ):
        return 'contention'
    if isinstance(error, DeadlineExceeded):
        return 'deadline_exceeded'
    if isinstance(error, ServiceUnavailable):
        return 'unavailable'
    if isinstance(error, ResourceExhausted):
        return 'resource_exhausted'
    return 'other'


# Used only by the transient publication opt-in. The default transactional path
# still retries an expired id alone and does not consult this set.
_RETRYABLE_FIRESTORE_REASONS = frozenset(
    {'expired_transaction', 'contention', 'deadline_exceeded', 'unavailable', 'resource_exhausted'}
)


def is_retryable_firestore_transaction_error(error: BaseException) -> bool:
    """True when a new transaction can succeed and the write itself is not refused.

    Composes ``firestore_failure_reason`` and ``is_permanent_firestore_write_rejection``.
    Expired transaction ids, contention (including the SDK's exhausted-commit
    wrapper), ``DeadlineExceeded``, ``ServiceUnavailable``, and
    ``ResourceExhausted`` are retryable. Any other ``InvalidArgument`` is not.
    The cause chain is walked because the SDK wraps a spent ``Aborted`` retry
    in ``ValueError``. Callers that do not pass ``transient=True`` do not use
    this predicate.
    """
    if is_permanent_firestore_write_rejection(error):
        return False
    current: BaseException | None = error
    seen: set[int] = set()
    while current is not None and id(current) not in seen:
        seen.add(id(current))
        if firestore_failure_reason(current) in _RETRYABLE_FIRESTORE_REASONS:
            return True
        current = current.__cause__
    return False


# Firestore names the rejected document as ``.../documents/<collection>/<id>/...``.
_ERROR_DOCUMENT_PATH = re.compile(r"/documents/([^'\"\s]+)")
# Every token a persistence log may carry for the rejected document.
FIRESTORE_DOCUMENT_KINDS = frozenset({'conversation', 'sync_day_index', 'sync_recent', 'donor', 'other', 'none'})


def firestore_error_document_path(error: BaseException) -> tuple[str, ...] | None:
    """The relative document path a Firestore ``InvalidArgument`` names, or ``None``.

    For in-process decisions only. The segments contain uids and document ids,
    so callers must never log them; log ``firestore_document_kind`` instead.
    """
    if not isinstance(error, InvalidArgument):
        return None
    match = _ERROR_DOCUMENT_PATH.search(str(error))
    if not match:
        return None
    # The message quotes the path, so the match ends at the closing quote.
    segments = tuple(match.group(1).split('/'))
    if len(segments) < 2 or len(segments) % 2 or not all(segments):
        return None
    return segments


def firestore_document_kind(error: BaseException) -> str:
    """Bounded token for the document a Firestore ``InvalidArgument`` names.

    Derived from the collection segments only (plus the fixed ``recent`` index
    name), never from ids: ``conversation``, ``sync_day_index``, ``sync_recent``,
    ``other`` for any other document, and ``none`` when the error is not an
    ``InvalidArgument`` or names no document. ``donor`` is a refinement only the
    sync assignment boundary can make, because it alone knows which
    conversation was the write's canonical.
    """
    segments = firestore_error_document_path(error)
    if segments is None:
        return 'none'
    collections = segments[0::2]
    if collections == ('users', 'conversations'):
        return 'conversation'
    if collections == ('users', 'sync_assignment'):
        return 'sync_recent' if segments[-1] == 'recent' else 'sync_day_index'
    return 'other'


def run_transactional(
    client: Any,
    transactional_callable: Any,
    *args: Any,
    attempts: int = 3,
    initial_transaction: Any = None,
    transient: bool = False,
    sleep: Callable[[float], None] | None = None,
    random_value: Callable[[], float] | None = None,
    outcome: dict[str, str] | None = None,
    **kwargs: Any,
) -> Any:
    """Run a ``@firestore.transactional`` callable, restarting it on an expired transaction.

    ``_Transactional.__call__`` retries contention by replaying the *same* transaction id,
    which is exactly what cannot work once Firestore has retired that id. The commit comes
    back ``400 The referenced transaction has expired or is no longer valid``; a streaming
    read comes back ``409`` ``Aborted`` with the same message, and the SDK does not retry
    that read. Nothing was written. Recovery requires a brand-new transaction and belongs
    to this boundary rather than to every caller — callers that own a live WebSocket
    session have no way to distinguish it from a real write failure.
    ``initial_transaction`` lets an outer contention budget own the first transaction;
    expiry still replaces it with a new transaction under the existing attempt limit.

    ``transient=True`` is the idempotent-caller opt-in. It also restarts on contention,
    ``DeadlineExceeded``, ``ServiceUnavailable``, and ``ResourceExhausted``, with
    equal-jitter backoff between fresh transactions. A deadline or a throttle at
    commit can be ambiguous, so the callable must re-read and refuse a second
    increment. Backoff runs in this helper, after the callable has returned, so a
    lock held only inside the callable is not held during the sleep. The default
    path still retries only an expired transaction id and does not sleep.
    ``outcome`` receives ``retried_ok`` or ``exhausted`` when set.
    """
    predicate = is_retryable_firestore_transaction_error if transient else is_expired_transaction_error
    caught: tuple[type[BaseException], ...] | type[Exception] = Exception if transient else (InvalidArgument, Aborted)
    for attempt in range(1, max(1, attempts) + 1):
        try:
            transaction = (
                initial_transaction if attempt == 1 and initial_transaction is not None else client.transaction()
            )
            result = transactional_callable(transaction, *args, **kwargs)
            if outcome is not None and attempt > 1:
                outcome['status'] = 'retried_ok'
            return result
        except caught as error:
            retryable = predicate(error)
            if attempt >= attempts or not retryable:
                if outcome is not None and retryable and attempt >= attempts:
                    outcome['status'] = 'exhausted'
                raise
            if transient:
                logger.warning(
                    'Firestore transaction retryable, restarting attempt=%d/%d reason=%s',
                    attempt,
                    attempts,
                    firestore_failure_reason(error),
                )
                delay = equal_jitter_delay(attempt, random_value or random.random)
                (sleep or time.sleep)(delay)
            else:
                logger.warning('Firestore transaction expired, restarting attempt=%d/%d', attempt, attempts)


class _LazyFirestoreClient:
    # google-cloud-firestore ships no type stubs; attribute access proxies onto
    # the real client. Returning Any here is the SDK boundary; call sites narrow
    # the returned documents into typed dicts via the adapter pattern.
    def __getattr__(self, name: str) -> Any:
        return getattr(get_firestore_client(), name)


db = _LazyFirestoreClient()


class _LazyDataPlaneFirestoreClient:
    # Same lazy-proxy idiom as ``_LazyFirestoreClient`` above, deferring
    # ``get_data_plane_firestore_client()`` until first attribute access so a
    # module can bind this as a default parameter value at import time without
    # forcing client construction (and its env/ADC reads) before that.
    def __getattr__(self, name: str) -> Any:
        return getattr(get_data_plane_firestore_client(), name)


data_plane_db = _LazyDataPlaneFirestoreClient()


def delete_collection_recursive(collection_ref: Any, *, client: Any, batch_size: int = 450) -> None:
    """Delete every document under a collection, descending into nested subcollections first.

    Firestore does not cascade: deleting a document leaves its subcollections in
    place as data no query can reach (the parent no longer exists, so it is not
    returned by a collection query either). Any caller that deletes a parent
    document must purge its children through this helper.
    """
    while True:
        docs = list(collection_ref.limit(batch_size).stream())
        if not docs:
            return

        for doc in docs:
            for sub in doc.reference.collections():
                delete_collection_recursive(sub, client=client, batch_size=batch_size)

        batch = client.batch()
        for doc in docs:
            batch.delete(doc.reference)
        batch.commit()

        if len(docs) < batch_size:
            return


def get_users_uid() -> list[str]:
    users_ref = get_firestore_client().collection('users')
    return [str(doc.id) for doc in users_ref.stream()]
