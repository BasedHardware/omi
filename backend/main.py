import asyncio
import json
import logging
import os

from omi_logging import configure_logging
from utils.env_loader import firebase_admin_options, load_backend_env
from utils.firebase_admin_runtime import (
    firebase_verify_only_credential,
    install_firebase_auth_mutation_guard,
    install_google_adc_guard,
)
from config.chat_first_e2e_fixture import is_chat_first_e2e_harness_runtime
from config.listen_quiet_finalization import enabled as quiet_finalization_enabled

load_backend_env()  # No-op if no env files exist (production); stage + local overrides otherwise
install_google_adc_guard()

# Text keeps the INFO-to-stdout / WARNING+-to-stderr split (so GKE does not store
# routine lines as ERROR) and the textPayload that log metrics match, until each
# service's consumers are admitted for JSON (docs/runbooks/structured-logging-rollout.md);
# OMI_LOG_FORMAT=json opts a service in.
configure_logging(os.getenv('K_SERVICE') or 'backend', default_format='text')
logger = logging.getLogger(__name__)

import firebase_admin
from fastapi import FastAPI
from starlette.middleware.cors import CORSMiddleware
from starlette.staticfiles import StaticFiles

from database.google_credentials import prepare_google_credentials
from utils.rollout_cohorts import configure_rollout_runtime
from utils.stt_cap_cohort import refresh_stt_cap_cohort_forever

prepare_google_credentials()
install_firebase_auth_mutation_guard()

from utils.observability.sync_upload import SyncUploadMetricsMiddleware
from utils.observability.external_lists import ExternalListMetricsMiddleware

# app_roles imports every router (the route table) in the original order.
from app_roles import mount_routers, role_from_env
from routers import messaging  # also used directly for the adapter runtime below
from routers.listen.registry import proactive_message_dispatcher

from utils.other.timeout import TimeoutMiddleware
from utils.observability import log_langsmith_status
from utils.subscription import validate_stripe_price_ids
from utils.http_client import close_all_clients
from utils.metrics import start_metrics_sidecar_server, stop_metrics_sidecar_server
from utils.observability.sync_phases import shutdown_sync_metrics
from utils.sync.cap_hold_lifecycle import flush_active
from utils.executors import (
    drain_background_tasks,
    log_executor_health,
    run_blocking,
    db_executor,
)
from utils.executors import start_background_task
from utils.batch_pipeline.serving import start_serving_from_env, stop_serving
from utils.cloud_tasks import validate_account_deletion_dispatch_configuration
from utils.stt.streaming import validate_streaming_stt_env
from utils.stt.soniox_usage import start_if_configured as start_soniox_usage_if_configured
from utils.stt.live_health import health as live_stt_health
from utils.stt.parakeet_window import batch_pressure
from utils.llm.managed_spend_ledger import shutdown_managed_spend_ledger
from services.conversation_finalization import reconcile_abandoned_byok_finalization_jobs
from services.conversation_finalization import reconcile_listen_finalization_jobs
from services.conversation_finalization import reconcile_stale_in_progress_conversations
from services.conversation_finalization import reconcile_stale_processing_conversations
from database.durable_queue_age import publish_all_queue_oldest_ready_ages
from services.users.account_deletion import reconcile_pending_deletion_wipes
from utils.other.local_storage import local_storage_root_from_env

# Log LangSmith tracing status at startup
log_langsmith_status()

# Validate Stripe price IDs so misconfigured plans fail loud
validate_stripe_price_ids()

_auth_emulator_host = os.environ.get("FIREBASE_AUTH_EMULATOR_HOST", "").strip()
_firebase_admin_options = firebase_admin_options()
_verify_only_credential = firebase_verify_only_credential()
if _verify_only_credential is not None:
    firebase_admin.initialize_app(_verify_only_credential, options=_firebase_admin_options)
elif _auth_emulator_host:
    for _adc_key in ("GOOGLE_APPLICATION_CREDENTIALS", "SERVICE_ACCOUNT_JSON", "FIREBASE_AUTH_CREDENTIALS_PATH"):
        os.environ.pop(_adc_key, None)
    _firebase_project_id = (
        os.environ.get("FIREBASE_AUTH_PROJECT_ID") or os.environ.get("FIREBASE_PROJECT_ID") or "demo-omi-local"
    )
    firebase_admin.initialize_app(options={"projectId": _firebase_project_id})  # type: ignore[reportUnknownMemberType]  # firebase_admin untyped
elif os.environ.get("SERVICE_ACCOUNT_JSON"):
    service_account_info = json.loads(os.environ["SERVICE_ACCOUNT_JSON"])
    credentials = firebase_admin.credentials.Certificate(service_account_info)
    firebase_admin.initialize_app(credentials, options=_firebase_admin_options)  # type: ignore[reportUnknownMemberType]  # firebase_admin untyped
else:
    firebase_admin.initialize_app(options=_firebase_admin_options)  # type: ignore[reportUnknownMemberType]  # firebase_admin untyped

# Bind private cohort resolution once at the serving composition root.
configure_rollout_runtime()
app = FastAPI()

_local_storage_root = local_storage_root_from_env()
if _local_storage_root is not None:
    _local_storage_root.mkdir(parents=True, exist_ok=True)
    app.mount('/_local/storage', StaticFiles(directory=_local_storage_root), name='local-storage')

# Explicit, default-deny CORS: this API is Bearer-token authenticated (mobile/
# desktop apps, not ambient browser cookies), so no cross-origin browser
# caller needs to be allowed by default. CORS_ALLOWED_ORIGINS lets an operator
# opt a specific web frontend in (comma-separated exact origins — never "*",
# and never combined with allow_credentials, which would let any site read
# authenticated responses for a signed-in visitor).
_cors_allowed_origins = [o.strip() for o in os.getenv('CORS_ALLOWED_ORIGINS', '').split(',') if o.strip()]
if '*' in _cors_allowed_origins:
    raise RuntimeError('CORS_ALLOWED_ORIGINS must not contain "*" — list explicit origins instead')
app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_allowed_origins,
    allow_credentials=False,
    allow_methods=['*'],
    allow_headers=['*'],
    expose_headers=[
        'X-Omi-Effective-Limit',
        'X-Omi-Has-More',
        'X-Omi-Next-Offset',
        'X-Omi-Next-Cursor',
        'X-Next-Cursor',
        'X-Scan-Truncated',
        'X-Omi-Memory-Canonical-Lifecycle-Exposed',
        'X-Omi-Memory-Default-Delete-Supported',
        'X-Omi-Memory-Device-Scope-Supported',
        'X-Omi-Memory-Next-Cursor',
        'X-Omi-List-Truncated',
    ],
)

# B8: OMI_ROLE selects the routers this process serves (default `all` = every router, today's order).
# The route table and roles live in app_roles.py; the router imports above stay static so the image
# source-closure and import-time checks still see every router. An unknown OMI_ROLE fails startup.
OMI_APP_ROLE = role_from_env()
mount_routers(app, OMI_APP_ROLE, include_harness=is_chat_first_e2e_harness_runtime())

methods_timeout = {
    "GET": os.environ.get('HTTP_GET_TIMEOUT'),
    "POST": os.environ.get('HTTP_POST_TIMEOUT'),
    "PUT": os.environ.get('HTTP_PUT_TIMEOUT'),
    "PATCH": os.environ.get('HTTP_PATCH_TIMEOUT'),
    "DELETE": os.environ.get('HTTP_DELETE_TIMEOUT'),
}

# Keep the in-request Cloud Tasks pipeline cap below its 1800s lock TTL so no lock expires under live work.
paths_timeout = {
    "/v2/cap-hold-recovery/sweep": 1710,  # Await bounded redrive under Scheduler's 1740s deadline.
    "/v2/batch-pipeline/recover-quarantine": 1500,  # Await paid STT and durable settlement within the task request.
    "/v2/sync-jobs/run": os.environ.get('HTTP_SYNC_JOBS_RUN_TIMEOUT', 1500),
    "/v2/dream-agent/sweep": 150,  # Enabled Dream routes use the 1710s cap in TimeoutMiddleware.
    "/v2/candidate-integrations/sweep": 90,  # Sweep stops at 50s; Scheduler allows 120s.
    "/v2/dream-agent/canary": 90,
    "/v1/dream/runs": 90,
    "/v2/sync-backfill-sequencer/sweep": 150,  # Below Scheduler's 180s deadline.
    "/v2/audio-merge-jobs/run": os.environ.get('HTTP_AUDIO_MERGE_RUN_TIMEOUT', 600),
    "/v1/users/account-deletion-wipes/run": os.environ.get('HTTP_ACCOUNT_DELETION_WIPE_RUN_TIMEOUT', 1500),
    "/v1/conversation-finalization-jobs/run": os.environ.get('HTTP_LISTEN_FINALIZATION_RUN_TIMEOUT', 1500),
    # STT proxy: 30s slot wait + 300s parakeet client budget (get_stt_proxy_client)
    # + headroom for auth and the multipart spool read; the default POST timeout
    # would cut long files off mid-transcription.
    "/v1/stt/transcribe": os.environ.get('HTTP_STT_TRANSCRIBE_TIMEOUT', 350),
}

app.add_middleware(TimeoutMiddleware, methods_timeout=methods_timeout, paths_timeout=paths_timeout)

from utils.byok import BYOKMiddleware
from utils.llm.desktop_proxy_lifetime import DesktopProxyDeadlineMiddleware

app.add_middleware(BYOKMiddleware)

from database.firestore_tier_context import FirestoreTierMiddleware

app.add_middleware(FirestoreTierMiddleware)
app.add_middleware(SyncUploadMetricsMiddleware)
app.add_middleware(ExternalListMetricsMiddleware)
app.add_middleware(DesktopProxyDeadlineMiddleware)


def _run_fsr_loop(loop_name, callback, interval_seconds):
    """Run on the DB executor, including Redis admission and origin attribution."""
    from database.firestore_read_origin import read_origin
    from database.durable_queue_age import withdraw_queue_oldest_ready_ages
    from utils.other.fsr_leader_lease import loop_lease

    def attributed():
        with read_origin(f'job:{loop_name}'):
            return callback()

    on_skip = withdraw_queue_oldest_ready_ages if loop_name == 'publish_all_queue_oldest_ready_ages' else None
    return loop_lease(loop_name).run(attributed, interval_seconds, on_skip=on_skip) or {}


# Install while importing on the main thread, after the server's signal setup.
from utils.other.fsr_leader_lease import install_loop_lease_sigterm_handler

install_loop_lease_sigterm_handler()

# Live STT: deaths after SIGTERM are our rolling restart, not provider evidence.
from utils.stt.pod_drain import install_drain_signal_marker

install_drain_signal_marker()


@app.on_event("startup")  # type: ignore[reportDeprecated]  # FastAPI on_event still functional; lifespan migration would change app wiring
async def startup_event():
    from utils.messaging.adapters.runtime import start_adapters

    app.state.messaging_runtime = await start_adapters(messaging.register_adapter)
    start_metrics_sidecar_server()
    start_background_task(refresh_stt_cap_cohort_forever(), name='stt_cap_cohort_refresh')
    start_background_task(live_stt_health.refresh_forever(), name='live_stt_fleet_health')
    from utils.held_content_cohort import refresh_held_content_cohort_forever

    start_background_task(refresh_held_content_cohort_forever(), name='held_content_cohort_refresh')
    batch_pressure.start_from_env()
    app.state.batch_pipeline_serving = start_serving_from_env()
    start_soniox_usage_if_configured(start_background_task)
    validate_account_deletion_dispatch_configuration()
    validate_streaming_stt_env()
    start_background_task(log_executor_health(), name='executor_health')
    # Drain account-deletion wipes orphaned by a previous deploy/restart. Offloaded
    # to db_executor so the blocking Firestore queries don't stall event-loop startup.
    start_background_task(
        run_blocking(db_executor, _drain_pending_deletion_wipes),
        name='startup_deletion_wipe_reconcile',
    )
    # Periodic reconciliation ensures stale retrying claims (worker crashed) and
    # new pending/failed wipes are retried without requiring a restart.
    start_background_task(_periodic_deletion_wipe_reconcile(), name='periodic_deletion_wipe_reconcile')
    start_background_task(
        run_blocking(db_executor, _drain_listen_finalization_jobs),
        name='startup_listen_finalization_reconcile',
    )
    start_background_task(
        run_blocking(db_executor, _drain_stale_processing_conversations),
        name='startup_stale_processing_reconcile',
    )
    start_background_task(
        run_blocking(db_executor, _drain_stale_in_progress_conversations),
        name='startup_stale_in_progress_reconcile',
    )
    start_background_task(
        run_blocking(db_executor, _drain_abandoned_byok_finalization_jobs),
        name='startup_byok_abandonment_reconcile',
    )
    start_background_task(_periodic_listen_finalization_reconcile(), name='periodic_listen_finalization_reconcile')
    start_background_task(_periodic_durable_queue_age_publish(), name='periodic_durable_queue_age_publish')
    start_background_task(
        proactive_message_dispatcher(),
        name='proactive_message_dispatcher',
    )


def _drain_pending_deletion_wipes():
    """Best-effort reconciliation of pending/failed account-deletion wipes on startup."""
    try:
        result = _run_fsr_loop(
            'reconcile_pending_deletion_wipes',
            reconcile_pending_deletion_wipes,
            _deletion_wipe_reconcile_interval_seconds(),
        )
        if result.get('requeued'):
            logger.info(f"Startup deletion-wipe reconciliation: {result}")
    except Exception as e:
        logger.error(f"Startup deletion-wipe reconciliation failed: {e}")


def _deletion_wipe_reconcile_interval_seconds() -> int:
    try:
        seconds = int(os.getenv('DELETION_WIPE_RECONCILE_INTERVAL_SECONDS', '300'))
    except ValueError:
        seconds = 300
    return max(1, seconds)


async def _periodic_deletion_wipe_reconcile(interval_seconds: int | None = None):
    """Periodically reconcile orphaned or failed account-deletion wipes.

    Runs every 5 minutes (default) so stale retrying claims and new
    pending/failed wipes are retried without requiring a restart.
    """
    if interval_seconds is None:
        interval_seconds = _deletion_wipe_reconcile_interval_seconds()
    from utils.other.fsr_leader_lease import poll_delay

    while True:
        await asyncio.sleep(poll_delay(interval_seconds, deletion=True))
        try:
            result = await run_blocking(
                db_executor,
                _run_fsr_loop,
                'reconcile_pending_deletion_wipes',
                reconcile_pending_deletion_wipes,
                interval_seconds,
            )
            if result.get('requeued'):
                logger.info(f"Periodic deletion-wipe reconciliation: {result}")
        except Exception as e:
            logger.error(f"Periodic deletion-wipe reconciliation failed: {e}")


def _drain_listen_finalization_jobs():
    """Best-effort durable finalization recovery after a restart/deploy."""
    try:
        result = _run_fsr_loop(
            'reconcile_listen_finalization_jobs',
            reconcile_listen_finalization_jobs,
            _listen_finalization_reconcile_interval_seconds(),
        )
        if result.get('requeued'):
            logger.info(f"Startup listen-finalization reconciliation: {result}")
    except Exception as e:
        logger.error(f"Startup listen-finalization reconciliation failed: {e}")


def _drain_stale_processing_conversations():
    """Best-effort recovery of bare-`processing` conversations orphaned by a sync-route crash."""
    try:
        result = _run_fsr_loop(
            'reconcile_stale_processing_conversations',
            reconcile_stale_processing_conversations,
            _listen_finalization_reconcile_interval_seconds(),
        )
        if result.get('completed') or result.get('migrated'):
            logger.info(f"Startup stale-processing reconciliation: {result}")
    except Exception as e:
        logger.error(f"Startup stale-processing reconciliation failed: {e}")


def _drain_stale_in_progress_conversations():
    """Best-effort durable admission of content-bearing listen zombies."""
    try:
        result = _run_fsr_loop(
            'reconcile_stale_in_progress_conversations',
            reconcile_stale_in_progress_conversations,
            _listen_finalization_reconcile_interval_seconds(),
        )
        if result.get('enqueued') or result.get('verified'):
            logger.info(f"Startup stale-in-progress reconciliation: {result}")
    except Exception as e:
        logger.error(f"Startup stale-in-progress reconciliation failed: {e}")


def _drain_abandoned_byok_finalization_jobs():
    """Best-effort disposition of BYOK finalization jobs no live session can claim."""
    try:
        result = _run_fsr_loop(
            'reconcile_abandoned_byok_finalization_jobs',
            reconcile_abandoned_byok_finalization_jobs,
            _listen_finalization_reconcile_interval_seconds(),
        )
        if result.get('abandoned'):
            logger.info(f"Startup byok-abandonment reconciliation: {result}")
    except Exception as e:
        logger.error(f"Startup byok-abandonment reconciliation failed: {e}")


def _listen_finalization_reconcile_interval_seconds(*, quiet_checks: bool = True) -> int:
    """Periodic reconcile cadence; overridable for hermetic behavioral tests."""
    default_seconds = 60 if quiet_checks and quiet_finalization_enabled() else 300
    try:
        seconds = int(os.getenv('LISTEN_FINALIZATION_RECONCILE_INTERVAL_SECONDS', str(default_seconds)))
    except ValueError:
        seconds = default_seconds
    return max(1, seconds)


async def _periodic_listen_finalization_reconcile(interval_seconds: int | None = None):
    """Replay stale finalization leases and publish durable backlog metrics."""
    if interval_seconds is None:
        interval_seconds = _listen_finalization_reconcile_interval_seconds()
    from utils.other.fsr_leader_lease import poll_delay, singleton_loops_enabled

    while True:
        await asyncio.sleep(poll_delay(interval_seconds))
        try:
            result = await run_blocking(
                db_executor,
                _run_fsr_loop,
                'reconcile_listen_finalization_jobs',
                reconcile_listen_finalization_jobs,
                interval_seconds,
            )
            if result.get('requeued'):
                logger.info(f"Periodic listen-finalization reconciliation: {result}")
        except Exception as e:
            logger.error(f"Periodic listen-finalization reconciliation failed: {e}")
        try:
            stale_result = await run_blocking(
                db_executor,
                _run_fsr_loop,
                'reconcile_stale_processing_conversations',
                reconcile_stale_processing_conversations,
                interval_seconds,
            )
            if stale_result.get('completed') or stale_result.get('migrated'):
                logger.info(f"Periodic stale-processing reconciliation: {stale_result}")
        except Exception as e:
            logger.error(f"Periodic stale-processing reconciliation failed: {e}")
        try:
            in_progress_result = await run_blocking(
                db_executor,
                _run_fsr_loop,
                'reconcile_stale_in_progress_conversations',
                reconcile_stale_in_progress_conversations,
                interval_seconds,
            )
            if in_progress_result.get('enqueued') or in_progress_result.get('verified'):
                logger.info(f"Periodic stale-in-progress reconciliation: {in_progress_result}")
        except Exception as e:
            logger.error(f"Periodic stale-in-progress reconciliation failed: {e}")
        try:
            byok_result = await run_blocking(
                db_executor,
                _run_fsr_loop,
                'reconcile_abandoned_byok_finalization_jobs',
                reconcile_abandoned_byok_finalization_jobs,
                interval_seconds,
            )
            if byok_result.get('abandoned'):
                logger.info(f"Periodic byok-abandonment reconciliation: {byok_result}")
        except Exception as e:
            logger.error(f"Periodic byok-abandonment reconciliation failed: {e}")
        if singleton_loops_enabled():
            continue  # The alert publisher has an independent takeover clock.
        try:
            await run_blocking(
                db_executor,
                _run_fsr_loop,
                'publish_all_queue_oldest_ready_ages',
                publish_all_queue_oldest_ready_ages,
                interval_seconds,
            )
        except Exception as e:
            logger.error(f"Periodic durable-queue age publish failed: {e}")


async def _periodic_durable_queue_age_publish(interval_seconds: int | None = None):
    """Sample immediately and retry ownership independently of recovery scans."""
    from utils.other.fsr_leader_lease import poll_delay, singleton_loops_enabled

    if interval_seconds is None:
        interval_seconds = _listen_finalization_reconcile_interval_seconds(quiet_checks=False)
    while True:
        if singleton_loops_enabled():
            try:
                await run_blocking(
                    db_executor,
                    _run_fsr_loop,
                    'publish_all_queue_oldest_ready_ages',
                    publish_all_queue_oldest_ready_ages,
                    interval_seconds,
                )
            except Exception as e:
                logger.error(f"Periodic durable-queue age publish failed: {e}")
        await asyncio.sleep(poll_delay(interval_seconds, queue_age=True))


@app.on_event("shutdown")  # type: ignore[reportDeprecated]  # FastAPI on_event still functional; lifespan migration would change app wiring
async def shutdown_event():
    # Keep the shutdown cleanup self-contained for isolated lifecycle callers.
    import logging

    from utils.executors import db_executor, run_blocking

    runtime = getattr(app.state, 'messaging_runtime', None)
    if runtime:
        stop, task = runtime
        stop.set()
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
    if (serving_task := getattr(app.state, 'batch_pipeline_serving', None)) is not None:
        await stop_serving(serving_task)
    await batch_pressure.stop()
    await flush_active(timeout=30.0)
    await drain_background_tasks(timeout=10.0)
    from utils.other.fsr_leader_lease import release_loop_leases
    from utils.other.fsr_leader_lease import singleton_loops_enabled
    from database.durable_queue_age import withdraw_queue_oldest_ready_ages

    try:
        if singleton_loops_enabled():
            await asyncio.to_thread(release_loop_leases)
        else:
            await run_blocking(db_executor, release_loop_leases)
    except Exception:
        logging.getLogger(__name__).warning('fsr_leader_lease release scheduling failed; leases will expire')
    if singleton_loops_enabled():
        withdraw_queue_oldest_ready_ages()
    await shutdown_managed_spend_ledger()
    await shutdown_sync_metrics()
    await close_all_clients()

    stop_metrics_sidecar_server()


paths = ['_temp', '_samples', '_segments', '_speech_profiles']
for path in paths:
    if not os.path.exists(path):
        os.makedirs(path)
