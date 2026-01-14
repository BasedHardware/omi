import json
import os

import firebase_admin
from fastapi import FastAPI

from routers import pusher
from database.cache import init_cache, shutdown_cache

if os.environ.get('SERVICE_ACCOUNT_JSON'):
    service_account_info = json.loads(os.environ["SERVICE_ACCOUNT_JSON"])
    credentials = firebase_admin.credentials.Certificate(service_account_info)
    firebase_admin.initialize_app(credentials)
else:
    firebase_admin.initialize_app()

app = FastAPI()
app.include_router(pusher.router)

paths = ['_temp', '_samples', '_segments', '_speech_profiles']
for path in paths:
    if not os.path.exists(path):
        os.makedirs(path)


@app.get('/health')
def health_check():
    return {"status": "healthy"}


@app.on_event("startup")
async def startup_event():
    """Initialize cache managers on startup."""
    try:
        init_cache(max_memory_mb=100)
        print("Cache managers initialized successfully")
    except Exception as e:
        print(f"Failed to initialize cache managers: {e}")
        # Continue startup even if cache managers fail


@app.on_event("shutdown")
async def shutdown_event():
    """Stop cache managers on shutdown."""
    shutdown_cache()
    print("Cache managers stopped")
