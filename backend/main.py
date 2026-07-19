import asyncio
import json
import logging
import os

from utils.env_loader import load_backend_env

load_backend_env()  # No-op if no env files exist (production); stage + local overrides otherwise

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

import firebase_admin
from fastapi import FastAPI

from database.google_credentials import prepare_google_credentials

prepare_google_credentials()

from routers import (
    chat,
    firmware,
    transcribe,
    omni_relay,
    auto_model,
    notifications,
    speech_profile,
    agents,
    users,
    trends,
    sync,
    apps,
    payment,
    integration,
    conversations,
    memories,
    api_key_management,
    mcp,
    mcp_sse,
    oauth,
    auth,
    action_items,
    candidates,
    task_integrations,
    integrations,
    x_connector,
    other,
    developer,
    updates,
    calendar_meetings,
    google_calendar,
    calendar_onboarding,
    imports,
    knowledge_graph,
    wrapped,
    folders,
    goals,
    workstreams,
    announcements,
    phone_calls,
    agent_tools,
    tools,
    metrics,
    fair_use_admin,
    staged_tasks,
    focus_sessions,
    advice,
    chat_sessions,
    scores,
    tts,
    memory_admin,
    memory_product,
    llm_usage,
    task_recommendations,
    conversation_finalization,
)

from utils.other.timeout import TimeoutMiddleware
from utils.observability import log_langsmith_status
from utils.subscription import validate_stripe_price_ids
from utils.http_client import close_all_clients
from utils.executors import (
    drain_background_tasks,
    log_executor_health,
    run_blocking,
    db_executor,
)
from utils.executors import start_background_task
from utils.cloud_tasks import validate_account_deletion_dispatch_configuration
from services.conversation_finalization import reconcile_listen_finalization_jobs
from services.users.account_deletion import reconcile_pending_deletion_wipes

# Log LangSmith tracing status at startup
log_langsmith_status()

# Validate Stripe price IDs so misconfigured plans fail loud
validate_stripe_price_ids()

_auth_emulator_host = os.environ.get("FIREBASE_AUTH_EMULATOR_HOST", "").strip()
if _auth_emulator_host:
    for _adc_key in ("GOOGLE_APPLICATION_CREDENTIALS", "SERVICE_ACCOUNT_JSON"):
        os.environ.pop(_adc_key, None)
    _firebase_project_id = (
        os.environ.get("FIREBASE_AUTH_PROJECT_ID") or os.environ.get("FIREBASE_PROJECT_ID") or "demo-omi-local"
    )
    firebase_admin.initialize_app(options={"projectId": _firebase_project_id})  # type: ignore[reportUnknownMemberType]  # firebase_admin untyped
elif os.environ.get("SERVICE_ACCOUNT_JSON"):
    service_account_info = json.loads(os.environ["SERVICE_ACCOUNT_JSON"])
    credentials = firebase_admin.credentials.Certificate(service_account_info)
    firebase_admin.initialize_app(credentials)  # type: ignore[reportUnknownMemberType]  # firebase_admin untyped
else:
    firebase_admin.initialize_app()  # type: ignore[reportUnknownMemberType]  # firebase_admin untyped

app = FastAPI()

app.include_router(transcribe.router)
app.include_router(omni_relay.router)
app.include_router(auto_model.router)
app.include_router(conversations.router)
app.include_router(action_items.router)
app.include_router(candidates.router)
app.include_router(task_integrations.router)
app.include_router(integrations.router)
app.include_router(x_connector.router)
app.include_router(memories.router)
app.include_router(chat.router)
app.include_router(speech_profile.router)
# app.include_router(screenpipe.router)
app.include_router(notifications.router)
app.include_router(integration.router)
app.include_router(agents.router)
app.include_router(users.router)
app.include_router(conversation_finalization.router)
app.include_router(trends.router)

app.include_router(other.router)

app.include_router(firmware.router)
app.include_router(updates.router)
app.include_router(sync.router)

app.include_router(apps.router)
app.include_router(calendar_meetings.router)
app.include_router(google_calendar.router)
app.include_router(calendar_onboarding.router)
app.include_router(oauth.router)  # Added oauth router (for Omi Apps)
app.include_router(auth.router)  # Added auth router (for the main Omi App, this is the core auth router)


app.include_router(payment.router)
app.include_router(api_key_management.mcp_router)
app.include_router(mcp.router)
app.include_router(mcp_sse.router)
app.include_router(api_key_management.developer_router)
app.include_router(developer.router)
app.include_router(imports.router)
app.include_router(wrapped.router)
app.include_router(folders.router)
app.include_router(knowledge_graph.router)
app.include_router(goals.router)
app.include_router(workstreams.router)
app.include_router(announcements.router)
app.include_router(phone_calls.router)
app.include_router(agent_tools.router)
app.include_router(tools.router)
app.include_router(metrics.router)
app.include_router(fair_use_admin.router)
app.include_router(staged_tasks.router)
app.include_router(focus_sessions.router)
app.include_router(advice.router)
app.include_router(chat_sessions.router)
app.include_router(scores.router)
app.include_router(tts.router)
app.include_router(memory_admin.router)
app.include_router(memory_product.router)
app.include_router(llm_usage.router)
app.include_router(task_recommendations.router)


methods_timeout = {
    "GET": os.environ.get('HTTP_GET_TIMEOUT'),
    "POST": os.environ.get('HTTP_POST_TIMEOUT'),
    "PUT": os.environ.get('HTTP_PUT_TIMEOUT'),
    "PATCH": os.environ.get('HTTP_PATCH_TIMEOUT'),
    "DELETE": os.environ.get('HTTP_DELETE_TIMEOUT'),
}

# The Cloud Tasks sync-job handler runs the whole pipeline inside the request,
# so it needs a much higher cap than the default. Must stay below the job run
# lock TTL (1800s) so a lock can never expire under a live run.
paths_timeout = {
    "/v2/sync-jobs/run": os.environ.get('HTTP_SYNC_JOBS_RUN_TIMEOUT', 1500),
    "/v2/audio-merge-jobs/run": os.environ.get('HTTP_AUDIO_MERGE_RUN_TIMEOUT', 600),
    "/v1/users/account-deletion-wipes/run": os.environ.get('HTTP_ACCOUNT_DELETION_WIPE_RUN_TIMEOUT', 1500),
    "/v1/conversation-finalization-jobs/run": os.environ.get('HTTP_LISTEN_FINALIZATION_RUN_TIMEOUT', 1500),
}

app.add_middleware(TimeoutMiddleware, methods_timeout=methods_timeout, paths_timeout=paths_timeout)

from utils.byok import BYOKMiddleware

app.add_middleware(BYOKMiddleware)


@app.on_event("startup")  # type: ignore[reportDeprecated]  # FastAPI on_event still functional; lifespan migration would change app wiring
async def startup_event():
    validate_account_deletion_dispatch_configuration()
    asyncio.create_task(log_executor_health())
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
    start_background_task(_periodic_listen_finalization_reconcile(), name='periodic_listen_finalization_reconcile')


def _drain_pending_deletion_wipes():
    """Best-effort reconciliation of pending/failed account-deletion wipes on startup."""
    try:
        result = reconcile_pending_deletion_wipes()
        if result.get('requeued'):
            logger.info(f"Startup deletion-wipe reconciliation: {result}")
    except Exception as e:
        logger.error(f"Startup deletion-wipe reconciliation failed: {e}")


async def _periodic_deletion_wipe_reconcile(interval_seconds: int = 300):
    """Periodically reconcile orphaned or failed account-deletion wipes.

    Runs every 5 minutes (default) so stale retrying claims and new
    pending/failed wipes are retried without requiring a restart.
    """
    while True:
        await asyncio.sleep(interval_seconds)
        try:
            result = await run_blocking(db_executor, reconcile_pending_deletion_wipes)
            if result.get('requeued'):
                logger.info(f"Periodic deletion-wipe reconciliation: {result}")
        except Exception as e:
            logger.error(f"Periodic deletion-wipe reconciliation failed: {e}")


def _drain_listen_finalization_jobs():
    """Best-effort durable finalization recovery after a restart/deploy."""
    try:
        result = reconcile_listen_finalization_jobs()
        if result.get('requeued'):
            logger.info(f"Startup listen-finalization reconciliation: {result}")
    except Exception as e:
        logger.error(f"Startup listen-finalization reconciliation failed: {e}")


async def _periodic_listen_finalization_reconcile(interval_seconds: int = 300):
    """Replay stale finalization leases and publish durable backlog metrics."""
    while True:
        await asyncio.sleep(interval_seconds)
        try:
            result = await run_blocking(db_executor, reconcile_listen_finalization_jobs)
            if result.get('requeued'):
                logger.info(f"Periodic listen-finalization reconciliation: {result}")
        except Exception as e:
            logger.error(f"Periodic listen-finalization reconciliation failed: {e}")


@app.on_event("shutdown")  # type: ignore[reportDeprecated]  # FastAPI on_event still functional; lifespan migration would change app wiring
async def shutdown_event():
    await drain_background_tasks(timeout=10.0)
    await close_all_clients()


paths = ['_temp', '_samples', '_segments', '_speech_profiles']
for path in paths:
    if not os.path.exists(path):
        os.makedirs(path)
