import json
import os
from contextlib import asynccontextmanager

import firebase_admin
from fastapi import FastAPI
from modal import App, Image, Secret, asgi_app

# MCP tools
from utils.llm.mcp_client import mcp_manager
from utils.retrieval.graph import create_agent_graph

# MCP tools will be initialized in the lifespan function
# This is the single, clean import for our tool logic
from utils.other.timeout import TimeoutMiddleware

# Import all your application routers
from routers import (
    action_items,
    agents,
    apps,
    auth,
    chat,
    conversations,
    custom_auth,
    firmware,
    integration,
    mcp,
    memories,
    notifications,
    oauth,
    other,
    payment,
    plugins,
    speech_profile,
    sync,
    transcribe,
    trends,
    users,
    workflow,
)

# Initialize Firebase
if os.environ.get('SERVICE_ACCOUNT_JSON'):
    service_account_info = json.loads(os.environ["SERVICE_ACCOUNT_JSON"])
    credentials = firebase_admin.credentials.Certificate(service_account_info)
    firebase_admin.initialize_app(credentials)
else:
    firebase_admin.initialize_app()


# A dictionary to hold our application's state
app_state = {}


@asynccontextmanager
async def lifespan(app: FastAPI):
    # --- Code to run ONCE on startup ---
    print("🚀 Application starting up...")

    # Initialize MCP client and tools
    tools = await mcp_manager.initialize()
    app_state["mcp_tools"] = tools

    # Create the graph
    agent_graph, agent_graph_stream = create_agent_graph()  # ← Unpack the tuple
    app_state["agent_graph"] = agent_graph
    app_state["agent_graph_stream"] = agent_graph_stream

    print("✅ Application is ready.")
    yield

    # --- Code to run ONCE on shutdown ---
    print("👋 Application shutting down.")
    await mcp_manager.cleanup()


app = FastAPI(lifespan=lifespan)

# Include all the API routers
app.include_router(transcribe.router)
app.include_router(conversations.router)
app.include_router(action_items.router)
app.include_router(memories.router)
app.include_router(chat.router)
app.include_router(plugins.router)
app.include_router(speech_profile.router)
app.include_router(notifications.router)
app.include_router(workflow.router)
app.include_router(integration.router)
app.include_router(agents.router)
app.include_router(users.router)
app.include_router(trends.router)
app.include_router(other.router)
app.include_router(firmware.router)
app.include_router(sync.router)
app.include_router(apps.router)
app.include_router(custom_auth.router)
app.include_router(oauth.router)
app.include_router(auth.router)
app.include_router(payment.router)
app.include_router(mcp.router)

# Add timeout middleware
methods_timeout = {
    "GET": os.environ.get('HTTP_GET_TIMEOUT'),
    "PUT": os.environ.get('HTTP_PUT_TIMEOUT'),
    "PATCH": os.environ.get('HTTP_PATCH_TIMEOUT'),
    "DELETE": os.environ.get('HTTP_DELETE_TIMEOUT'),
}
app.add_middleware(TimeoutMiddleware, methods_timeout=methods_timeout)


# --- Modal Setup ---
modal_app = App(
    name='backend',
    secrets=[Secret.from_name("gcp-credentials"), Secret.from_name('envs')],
)
image = Image.debian_slim().apt_install('ffmpeg', 'git', 'unzip').pip_install_from_requirements('requirements.txt')


@modal_app.function(
    image=image,
    keep_warm=0,
    memory=(512, 1024),
    cpu=2,
    allow_concurrent_inputs=10,
    timeout=60 * 10,
)
@asgi_app()
def api():
    return app


# Ensure necessary local directories exist
paths = ['_temp', '_samples', '_segments', '_speech_profiles']
for path in paths:
    if not os.path.exists(path):
        os.makedirs(path)
