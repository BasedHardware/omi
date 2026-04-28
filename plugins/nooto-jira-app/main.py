"""nooto-jira-app — FastAPI entry point.

Routers are split by slice owner so parallel implementation can proceed without
file-level conflicts:

    routes.auth         OAuth 2.0 (3LO)             slice B
    routes.tools        7 chat tool endpoints       slice C
    routes.manifest     /.well-known/omi-tools.json slice C
    routes.proactive    /webhook, /memory_created   slice D
    routes.settings     /settings, /settings/...    slice D
"""

import asyncio
import logging
import os
from contextlib import asynccontextmanager

from dotenv import load_dotenv
from fastapi import FastAPI

from routes import auth, manifest, proactive, settings, tools

load_dotenv()

logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO"),
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
log = logging.getLogger("nooto-jira-app")


@asynccontextmanager
async def lifespan(app: FastAPI):
    task = asyncio.create_task(proactive.idle_flush_worker())
    try:
        yield
    finally:
        task.cancel()


app = FastAPI(title="nooto-jira-app", version="0.1.0", lifespan=lifespan)

app.include_router(auth.router, tags=["auth"])
app.include_router(tools.router, tags=["tools"])
app.include_router(manifest.router, tags=["manifest"])
app.include_router(proactive.router, tags=["proactive"])
app.include_router(settings.router, tags=["settings"])


@app.get("/health", tags=["health"])
async def health() -> dict:
    return {"status": "healthy", "service": "nooto-jira-app"}
