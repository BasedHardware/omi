import logging
from threading import Lock
from typing import Any

import os
from google.api_core.exceptions import InvalidArgument
from google.cloud import firestore

from database.document_ids import document_id_from_seed
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
    "get_customer_firestore_client",
    "get_data_plane_firestore_client",
    "get_firestore_client",
    "get_users_uid",
    "is_document_size_limit_error",
    "is_expired_transaction_error",
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
    """Count every Firestore document read by collection pattern and hit/miss.

    Same lazy-import discipline as the query retry shim above: the probe wraps
    SDK classes that do not exist under the unit-test import stubs.
    """
    try:
        from database.firestore_document_probe import install_document_read_probe
    except ImportError:
        return

    install_document_read_probe()


_install_document_read_probe()

_firestore_client = None
_firestore_client_lock = Lock()
_customer_firestore_client = None
_customer_firestore_client_lock = Lock()


def _firestore_database_id() -> str | None:
    """Resolve the optional named database, with a hard QA-only fence.

    The isolated JIT plane owns ``jit-qa`` in the development project.  A
    named database must never be accepted as an ambient production override:
    ordinary services retain the default database when this variable is absent,
    while a misconfigured QA process fails before constructing a client.
    """

    database = (os.getenv("FIRESTORE_DATABASE_ID") or "").strip()
    qa_auth_only = (os.getenv("OMI_JIT_QA_AUTH_ONLY") or "").strip().casefold() in {"1", "true", "yes", "on"}
    if qa_auth_only:
        if database != "jit-qa":
            raise RuntimeError("isolated JIT QA requires FIRESTORE_DATABASE_ID=jit-qa")
        if (
            (os.getenv("OMI_ENV_STAGE") or "").strip().casefold() != "dev"
            or (os.getenv("GOOGLE_CLOUD_PROJECT") or "").strip() != "based-hardware-dev"
            or (os.getenv("OMI_FIRESTORE_DATA_PLANE_PROJECT") or "").strip() != "based-hardware-dev"
        ):
            raise RuntimeError("FIRESTORE_DATABASE_ID=jit-qa requires the isolated development JIT QA fence")
        return database
    if not database or database == "(default)":
        return None
    if database == "jit-qa":
        raise RuntimeError("FIRESTORE_DATABASE_ID=jit-qa requires the isolated development JIT QA fence")
    raise RuntimeError("FIRESTORE_DATABASE_ID is restricted to the isolated JIT QA database")


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
        database = _firestore_database_id()
        if database and project_id != "based-hardware-dev":
            raise RuntimeError("jit-qa cannot use a mounted customer-data service account")
        customer_kwargs: dict[str, Any] = {"credentials": credentials, "project": project_id}
        if database:
            customer_kwargs["database"] = database
        return firestore.Client(**customer_kwargs)

    prepare_google_credentials()
    database = _firestore_database_id()
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
        database = _firestore_database_id()
        if database and project_id != "based-hardware-dev":
            raise RuntimeError("jit-qa cannot use a mounted customer-entitlement service account")
        kwargs: dict[str, Any] = {"credentials": credentials, "project": project_id}
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
    Firestore data — the memory ledger, JIT proactivity state, screen-activity
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
    database = _firestore_database_id()
    if not data_plane_project:
        service = (os.getenv("K_SERVICE") or os.getenv("APP_NAME") or "").strip().casefold()
        if "desktop-backend" in service:
            raise RuntimeError("OMI_FIRESTORE_DATA_PLANE_PROJECT is required on desktop-backend")
        return get_firestore_client()

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
        if database and sa_project != "based-hardware-dev":
            raise RuntimeError("jit-qa cannot use a mounted customer-entitlement service account")
        kwargs: dict[str, Any] = {"credentials": credentials, "project": data_plane_project}
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
    """True for the Firestore 400 that retires a transaction id mid-flight."""
    return isinstance(error, InvalidArgument) and _EXPIRED_TRANSACTION_MARKER in str(error).lower()


_DOCUMENT_SIZE_LIMIT_MARKER = "exceeds the maximum allowed size"


def is_document_size_limit_error(error: BaseException) -> bool:
    """True for the Firestore 400 rejecting a write that would exceed the 1 MiB document ceiling.

    Unlike contention or an expired transaction, this is permanent: retrying the
    same growing write can never succeed, so callers must take a different path
    rather than loop.
    """
    return isinstance(error, InvalidArgument) and _DOCUMENT_SIZE_LIMIT_MARKER in str(error).lower()


def run_transactional(client: Any, transactional_callable: Any, *args: Any, attempts: int = 3, **kwargs: Any) -> Any:
    """Run a ``@firestore.transactional`` callable, restarting it on an expired transaction.

    ``_Transactional.__call__`` retries contention by replaying the *same* transaction id,
    which is exactly what cannot work once Firestore has retired that id: the commit comes
    back ``400 The referenced transaction has expired or is no longer valid`` and nothing
    was written. The SDK treats that as fatal, so recovery requires a brand-new transaction
    and belongs to this boundary rather than to every caller — callers that own a live
    WebSocket session have no way to distinguish it from a real write failure.
    """
    for attempt in range(1, max(1, attempts) + 1):
        try:
            return transactional_callable(client.transaction(), *args, **kwargs)
        except InvalidArgument as error:
            if attempt >= attempts or not is_expired_transaction_error(error):
                raise
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
