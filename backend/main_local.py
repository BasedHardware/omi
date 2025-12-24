"""Minimal local server - runs without .env or AI keys"""
import json
import os

try:
    import firebase_admin
    FIREBASE_AVAILABLE = True
except ImportError:
    FIREBASE_AVAILABLE = False
    print("⚠️  Firebase not available - continuing without it")

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

# Try to import routers, but handle gracefully if dependencies are missing
routers_to_load = []

try:
    from routers import (
        workflow,
        chat,
        firmware,
        plugins,
        transcribe,
        notifications,
        speech_profile,
        agents,
        users,
        trends,
        sync,
        apps,
        custom_auth,
        payment,
        integration,
        conversations,
        memories,
        mcp,
        oauth,
        action_items,
    )
    
    routers_to_load = [
        ("transcribe", transcribe),
        ("conversations", conversations),
        ("action_items", action_items),
        ("memories", memories),
        ("chat", chat),
        ("plugins", plugins),
        ("speech_profile", speech_profile),
        ("notifications", notifications),
        ("workflow", workflow),
        ("integration", integration),
        ("agents", agents),
        ("users", users),
        ("trends", trends),
        ("firmware", firmware),
        ("sync", sync),
        ("apps", apps),
        ("custom_auth", custom_auth),
        ("oauth", oauth),
        ("payment", payment),
        ("mcp", mcp),
    ]
except ImportError as e:
    print(f"⚠️  Some routers not available: {e}")
    print("Server will start with minimal functionality")

try:
    from utils.other.timeout import TimeoutMiddleware
    TIMEOUT_MIDDLEWARE_AVAILABLE = True
except ImportError:
    TIMEOUT_MIDDLEWARE_AVAILABLE = False
    print("⚠️  Timeout middleware not available")

# Initialize Firebase if available
if FIREBASE_AVAILABLE:
    try:
        if os.environ.get('SERVICE_ACCOUNT_JSON'):
            service_account_info = json.loads(os.environ["SERVICE_ACCOUNT_JSON"])
            credentials = firebase_admin.credentials.Certificate(service_account_info)
            firebase_admin.initialize_app(credentials)
        else:
            # Try to initialize with default credentials
            try:
                firebase_admin.initialize_app()
            except Exception as e:
                print(f"⚠️  Firebase initialization failed: {e}")
                print("   Continuing without Firebase...")
    except Exception as e:
        print(f"⚠️  Firebase setup error: {e}")
        print("   Continuing without Firebase...")

app = FastAPI(title="Omi Backend (Local)", version="1.0.0")

# Add CORS middleware to allow requests from anywhere (for local dev)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Load routers that are available
for router_name, router_module in routers_to_load:
    try:
        if hasattr(router_module, 'router'):
            app.include_router(router_module.router)
            print(f"✅ Loaded router: {router_name}")
        else:
            print(f"⚠️  Router {router_name} doesn't have 'router' attribute")
    except Exception as e:
        print(f"⚠️  Failed to load router {router_name}: {e}")

# Add timeout middleware if available
if TIMEOUT_MIDDLEWARE_AVAILABLE:
    methods_timeout = {
        "GET": os.environ.get('HTTP_GET_TIMEOUT'),
        "PUT": os.environ.get('HTTP_PUT_TIMEOUT'),
        "PATCH": os.environ.get('HTTP_PATCH_TIMEOUT'),
        "DELETE": os.environ.get('HTTP_DELETE_TIMEOUT'),
    }
    app.add_middleware(TimeoutMiddleware, methods_timeout=methods_timeout)

# Create required directories
paths = ['_temp', '_samples', '_segments', '_speech_profiles']
for path in paths:
    if not os.path.exists(path):
        os.makedirs(path)
        print(f"📁 Created directory: {path}")

@app.get("/")
async def root():
    return {
        "message": "Omi Backend Server (Local Mode)",
        "status": "running",
        "mode": "local",
        "firebase": "available" if FIREBASE_AVAILABLE else "not available"
    }

@app.get("/health")
async def health():
    return {"status": "healthy"}

if __name__ == "__main__":
    import uvicorn
    print("🚀 Starting Omi Backend Server (Local Mode)")
    print("📍 Server will be available at http://localhost:8000")
    print("📱 For phone access, use your computer's IP address")
    uvicorn.run(app, host="0.0.0.0", port=8000, log_level="info")
