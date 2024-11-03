import json
import os
import sys
import firebase_admin
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from modal import Image, App, asgi_app, Secret, Cron

# Check if we're running tests
TESTING = 'pytest' in sys.modules or os.getenv('TESTING') == 'true'
SKIP_VAD_INIT = os.getenv('SKIP_VAD_INIT') == 'true'
SKIP_HEAVY_INIT = os.getenv('SKIP_HEAVY_INIT') == 'true'

print("\nFastAPI: Starting initialization...")

# Initialize Firebase using application default credentials
if not TESTING:
    firebase_admin.initialize_app()
    print("FastAPI: Firebase initialized")

app = FastAPI()

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

# Include all routers
from routers import workflow, chat, firmware, plugins, memories, transcribe_v2, notifications, \
    speech_profile, agents, facts, users, processing_memories, trends, sdcard, sync

# Include all routers
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

@app.get("/")
async def root():
    return {"message": "API is running"}

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

@app.post('/webhook')
async def webhook(data: dict):
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

if not SKIP_HEAVY_INIT and not TESTING:
    # Add other heavy initialization here
    pass
