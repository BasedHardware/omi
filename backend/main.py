import json
import os
import firebase_admin
from fastapi import FastAPI

from modal import Image, App, asgi_app, Secret, Cron
from routers import workflow, chat, firmware, plugins, memories, transcribe_v2, notifications, \
    speech_profile, agents, facts, users, processing_memories, trends, sdcard, sync
from utils.other.notifications import start_cron_job

print("\nFastAPI: Starting initialization...")

# Initialize Firebase using application default credentials
firebase_admin.initialize_app()
print("FastAPI: Firebase initialized")

app = FastAPI()

# Include routers with logging
print("FastAPI: Registering routes")
routers = [
    (transcribe_v2.router, "transcribe_v2"),
    (memories.router, "memories"),
    (facts.router, "facts"),
    (chat.router, "chat"),
    (plugins.router, "plugins"),
    (speech_profile.router, "speech_profile"),
    (workflow.router, "workflow"),
    (notifications.router, "notifications"),
    (agents.router, "agents"),
    (users.router, "users"),
    (processing_memories.router, "processing_memories"),
    (trends.router, "trends"),
    (firmware.router, "firmware"),
    (sdcard.router, "sdcard"),
    (sync.router, "sync")
]

for router, name in routers:
    print(f"FastAPI: Including router - {name}")
    app.include_router(router)

print("FastAPI: All routes registered")

modal_app = App(
    name='backend',
    secrets=[Secret.from_name("gcp-credentials"), Secret.from_name('envs')],
)
image = (
    Image.debian_slim()
    .apt_install('ffmpeg', 'git', 'unzip')
    .pip_install_from_requirements('requirements.txt')
)

# Create required directories
paths = ['_temp', '_samples', '_segments', '_speech_profiles']
for path in paths:
    if not os.path.exists(path):
        os.makedirs(path)
print("FastAPI: Created required directories")

print("\n" + "="*50)
print("🚀 Backend ready and running!")
print("="*50 + "\n")

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
    # openn scripts/stt/diarization.json, get jobId=memoryId, delete but get memoryId, and save memoryId=joined
    with open('scripts/stt/diarization.json', 'r') as f:
        diarization_data = json.loads(f.read())

    memory_id = diarization_data.get(data['jobId'])
    if memory_id:
        diarization_data[memory_id] = joined
        del diarization_data[data['jobId']]
        with open('scripts/stt/diarization.json', 'w') as f:
            json.dump(diarization_data, f, indent=2)
    return 'ok'

# opuslib not found? brew install opus &
# DYLD_LIBRARY_PATH=/opt/homebrew/lib:$DYLD_LIBRARY_PATH
