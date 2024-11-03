import json
import os
import sys
import firebase_admin
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import HTMLResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles
from modal import Image, App, asgi_app, Secret, Cron
import plistlib
from pathlib import Path

# Check if we're running tests
TESTING = 'pytest' in sys.modules or os.getenv('TESTING') == 'true'
SKIP_VAD_INIT = os.getenv('SKIP_VAD_INIT') == 'true'
SKIP_HEAVY_INIT = os.getenv('SKIP_HEAVY_INIT') == 'true'
ENABLE_SWAGGER = os.getenv('ENABLE_SWAGGER', '').lower() == 'true'
ENABLE_RATE_LIMIT = os.getenv('ENABLE_RATE_LIMIT', '').lower() == 'true'

# Only import OpenAPI components if Swagger is enabled and not testing
if ENABLE_SWAGGER and not TESTING:
    from fastapi.openapi.docs import get_swagger_ui_html
    from fastapi.openapi.utils import get_openapi

print("\nFastAPI: Starting initialization...")

# Initialize Firebase using application default credentials
if not TESTING:
    firebase_admin.initialize_app()
    print("FastAPI: Firebase initialized")

# Move the router imports before using them
# Include all routers
from routers import workflow, chat, firmware, plugins, memories, transcribe_v2, notifications, \
    speech_profile, agents, facts, users, processing_memories, trends, sdcard, sync, auth

# Create FastAPI app with custom configuration
app = FastAPI(
    title="Omi API",
    description="API for Omi backend services",
    version="1.0.0",
    # Only enable Swagger endpoints if enabled and not testing
    docs_url="/docs" if (ENABLE_SWAGGER and not TESTING) else None,
    redoc_url="/redoc" if (ENABLE_SWAGGER and not TESTING) else None,
    openapi_url="/openapi.json" if (ENABLE_SWAGGER and not TESTING) else None
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Add Gzip compression
app.add_middleware(GZipMiddleware, minimum_size=1000)

# Add rate limiting if enabled
if ENABLE_RATE_LIMIT:
    print("FastAPI: Rate limiting enabled")
    app.add_middleware(RateLimitMiddleware, requests_per_minute=60)

# Include all routers with tags
app.include_router(transcribe_v2.router, prefix="/transcribe_v2", tags=["transcribe_v2"])
app.include_router(memories.router, prefix="/memories", tags=["memories"])
app.include_router(facts.router, prefix="/facts", tags=["facts"])
app.include_router(chat.router, prefix="/chat", tags=["chat"])
app.include_router(plugins.router, prefix="/plugins", tags=["plugins"])
app.include_router(speech_profile.router, prefix="/speech_profile", tags=["speech_profile"])
app.include_router(workflow.router, prefix="/workflow", tags=["workflow"])
app.include_router(notifications.router, prefix="/notifications", tags=["notifications"])
app.include_router(agents.router, prefix="/agents", tags=["agents"])
app.include_router(users.router, prefix="/users", tags=["users"])
app.include_router(processing_memories.router, prefix="/processing_memories", tags=["processing_memories"])
app.include_router(trends.router, prefix="/trends", tags=["trends"])
app.include_router(firmware.router, prefix="/firmware", tags=["firmware"])
app.include_router(sdcard.router, prefix="/sdcard", tags=["sdcard"])
app.include_router(sync.router, prefix="/sync", tags=["sync"])
app.include_router(auth.router, prefix="/auth", tags=["auth"])

@app.get("/", tags=["health"])
async def root():
    """Health check endpoint"""
    return {"message": "API is running"}

@app.get("/robots.txt", response_class=PlainTextResponse)
async def robots():
    """Serve robots.txt to disallow all crawlers"""
    return f"""User-agent: *\nDisallow: /"""

# Custom OpenAPI schema with security schemes if Swagger is enabled and not testing
if ENABLE_SWAGGER and not TESTING:
    def custom_openapi():
        if app.openapi_schema:
            return app.openapi_schema
            
        openapi_schema = get_openapi(
            title="Omi API",
            version="1.0.0",
            description="API for Omi backend services",
            routes=app.routes,
        )
        
        # Add security schemes
        openapi_schema["components"]["securitySchemes"] = {
            "BearerAuth": {
                "type": "http",
                "scheme": "bearer",
                "bearerFormat": "JWT",
                "description": """
                Enter your Firebase ID token.
                Format: `Bearer your_token`
                
                To get a token, use the Firebase Authentication flow described in the API description.
                Head to <a href="/auth/login">/auth/login</a> to get started.
                """
            }
        }
        
        # Add global security requirement
        openapi_schema["security"] = [{"BearerAuth": []}]
        
        # Add tag descriptions
        openapi_schema["tags"] = [
            {"name": "transcribe_v2", "description": "Real-time and batch transcription services"},
            {"name": "memories", "description": "Memory storage and retrieval management"},
            {"name": "facts", "description": "User facts and knowledge base management"},
            {"name": "chat", "description": "Chat and conversation endpoints"},
            {"name": "plugins", "description": "External integrations and plugin management"},
            {"name": "speech_profile", "description": "Voice profile and speaker recognition"},
            {"name": "workflow", "description": "Workflow and process automation"},
            {"name": "notifications", "description": "User notifications and alerts"},
            {"name": "agents", "description": "AI agents and automated assistants"},
            {"name": "users", "description": "User account and profile management"},
            {"name": "processing_memories", "description": "Memory processing and analysis"},
            {"name": "trends", "description": "Analytics and trend analysis"},
            {"name": "firmware", "description": "Device firmware management"},
            {"name": "sdcard", "description": "SD card data management"},
            {"name": "sync", "description": "Data synchronization services"},
            {"name": "health", "description": "API health check endpoints"},
            {"name": "webhooks", "description": "Webhook endpoints for external integrations"},
            {"name": "auth", "description": "Authentication endpoints"},
        ]
        
        app.openapi_schema = openapi_schema
        return app.openapi_schema

    app.openapi = custom_openapi

# Only create Modal app if not testing
if not TESTING:
    modal_app = App(
        name='backend',
        secrets=[Secret.from_name("gcp-credentials"), Secret.from_name('envs')],
    )
    image = (
        Image.debian_slim()
        .apt_install('ffmpeg', 'git', 'unzip')
        .pip_install_from_requirements('requirements.txt')
    )

    @modal_app.function(
        image=image,
        keep_warm=2,
        memory=(512, 1024),
        cpu=2,
        allow_concurrent_inputs=10,
        timeout=60 * 10,
    )
    @asgi_app()
    def api():
        return app

    @modal_app.function(image=image, schedule=Cron('* * * * *'))
    async def notifications_cronjob():
        await start_cron_job()

# Create required directories
paths = ['_temp', '_samples', '_segments', '_speech_profiles']
for path in paths:
    if not os.path.exists(path):
        os.makedirs(path)
print("FastAPI: Created required directories")

if not TESTING:
    print("\n" + "="*50)
    print("🚀 Backend ready and running!")
    print("="*50 + "\n")

@app.post('/webhook', tags=["webhooks"])
async def webhook(data: dict):
    """
    Webhook endpoint for processing diarization results
    
    Args:
        data: Dictionary containing diarization output
        
    Returns:
        str: Confirmation message
    """
    diarization = data['output']['diarization']
    joined = []
    for speaker in diarization:
        if not joined:
            joined.append(speaker)
        else:
            if speaker['speaker'] == joined[-1]['speaker']:
                joined[-1]['end'] = speaker['end']
            else:
                joined.append(speaker)

    print(data['jobId'], json.dumps(joined))
    with open('scripts/stt/diarization.json', 'r') as f:
        diarization_data = json.loads(f.read())

    memory_id = diarization_data.get(data['jobId'])
    if memory_id:
        diarization_data[memory_id] = joined
        del diarization_data[data['jobId']]
        with open('scripts/stt/diarization.json', 'w') as f:
            json.dump(diarization_data, f, indent=2)
    return 'ok'

# Conditional initialization
if not SKIP_VAD_INIT and not TESTING:
    try:
        from utils.stt import vad
        if hasattr(vad, 'init_vad'):
            vad.init_vad()
    except (ImportError, AttributeError):
        print("Warning: VAD initialization skipped")

