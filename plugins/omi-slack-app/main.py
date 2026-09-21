from fastapi import FastAPI

from .routes.auth import router as auth_router
from .routes.update_channel import router as update_channel_router
from .routes.refresh_channels import router as refresh_channels_router
from .routes.logout import router as logout_router
from .routes.webhook import router as webhook_router
from .routes.chat_tool import router as chat_tool_router

app = FastAPI(title="OMI Slack App")

# Register routers
app.include_router(auth_router)
app.include_router(update_channel_router)
app.include_router(refresh_channels_router)
app.include_router(logout_router)
app.include_router(webhook_router)
app.include_router(chat_tool_router)
