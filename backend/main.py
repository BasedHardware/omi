import json
import logging
import os

from dotenv import load_dotenv

load_dotenv()  # No-op if .env doesn't exist (production); loads local dev secrets otherwise

logging.basicConfig(level=logging.INFO)

import firebase_admin
from fastapi import FastAPI

from routers import (
    chat,
    firmware,
    transcribe,
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
    mcp,
    mcp_sse,
    oauth,
    auth,
    action_items,
    task_integrations,
    integrations,
    other,
    developer,
    updates,
    calendar_meetings,
    imports,
    knowledge_graph,
    wrapped,
    folders,
    goals,
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
)

from utils.other.timeout import TimeoutMiddleware
from utils.observability import log_langsmith_status
from utils.subscription import validate_stripe_price_ids
from utils.http_client import close_all_clients

# Log LangSmith tracing status at startup
log_langsmith_status()

# Validate Stripe price IDs so misconfigured plans fail loud
validate_stripe_price_ids()

if os.environ.get('SERVICE_ACCOUNT_JSON'):
    service_account_info = json.loads(os.environ["SERVICE_ACCOUNT_JSON"])
    credentials = firebase_admin.credentials.Certificate(service_account_info)
    firebase_admin.initialize_app(credentials)
else:
    firebase_admin.initialize_app()

# starlette 0.40 added a default 1 MB cap per multipart form part. Voice
# messages, audio uploads, and persona/app images legitimately exceed that.
# Match the existing per-request PCM ceiling.
from starlette.formparsers import MultiPartParser

MultiPartParser.max_part_size = 200 * 1024 * 1024  # 200 MB

app = FastAPI()

app.include_router(transcribe.router)
app.include_router(conversations.router)
app.include_router(action_items.router)
app.include_router(task_integrations.router)
app.include_router(integrations.router)
app.include_router(memories.router)
app.include_router(chat.router)
app.include_router(speech_profile.router)
# app.include_router(screenpipe.router)
app.include_router(notifications.router)
app.include_router(integration.router)
app.include_router(agents.router)
app.include_router(users.router)
app.include_router(trends.router)

app.include_router(other.router)

app.include_router(firmware.router)
app.include_router(updates.router)
app.include_router(sync.router)

app.include_router(apps.router)
app.include_router(calendar_meetings.router)
app.include_router(oauth.router)  # Added oauth router (for Omi Apps)
app.include_router(auth.router)  # Added auth router (for the main Omi App, this is the core auth router)


app.include_router(payment.router)
app.include_router(mcp.router)
app.include_router(mcp_sse.router)
app.include_router(developer.router)
app.include_router(imports.router)
app.include_router(wrapped.router)
app.include_router(folders.router)
app.include_router(knowledge_graph.router)
app.include_router(goals.router)
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


methods_timeout = {
    "GET": os.environ.get('HTTP_GET_TIMEOUT'),
    "POST": os.environ.get('HTTP_POST_TIMEOUT'),
    "PUT": os.environ.get('HTTP_PUT_TIMEOUT'),
    "PATCH": os.environ.get('HTTP_PATCH_TIMEOUT'),
    "DELETE": os.environ.get('HTTP_DELETE_TIMEOUT'),
}

app.add_middleware(TimeoutMiddleware, methods_timeout=methods_timeout)

from utils.byok import BYOKMiddleware

app.add_middleware(BYOKMiddleware)


@app.on_event("shutdown")
async def shutdown_event():
    await close_all_clients()


paths = ['_temp', '_samples', '_segments', '_speech_profiles']
for path in paths:
    if not os.path.exists(path):
        os.makedirs(path)
