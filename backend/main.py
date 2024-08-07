import json
import os
import asyncio
from dotenv import load_dotenv
import firebase_admin
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from modal import Image, App, asgi_app, Secret
from routers import backups, chat, memories, plugins, speech_profile, transcribe, screenpipe

# Load environment variables from .env file
load_dotenv()

# Initialize Firebase Admin SDK using service account credentials from environment variable
service_account_json = os.getenv('SERVICE_ACCOUNT_JSON')
if service_account_json:
    service_account_info = json.loads(service_account_json)
    credentials = firebase_admin.credentials.Certificate(service_account_info)
    firebase_admin.initialize_app(credentials)
else:
    firebase_admin.initialize_app()

# Create a FastAPI application instance
app = FastAPI()

async def websocket_handler(websocket: WebSocket):
    await websocket.accept()
    try:
        while True:
            data = await websocket.receive_text()
            # Process received data
            await websocket.send_text(f"Message received: {data}")

            # Heartbeat mechanism
            await websocket.send_json({"type": "ping"})
            await asyncio.sleep(10)
    except WebSocketDisconnect:
        print("Client disconnected")
    except Exception as e:
        print(f"Unexpected error: {e}")

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket_handler(websocket)

app.include_router(transcribe.router)
app.include_router(memories.router)
app.include_router(chat.router)
app.include_router(plugins.router)
app.include_router(speech_profile.router)
app.include_router(backups.router)
app.include_router(screenpipe.router)

modal_app = App(
    name='api',
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
    memory=(1024, 2048),
    cpu=4,
    allow_concurrent_inputs=5,
)
@asgi_app()
def fastapi_app():
    return app

paths = ['_temp', '_samples', '_segments', '_speaker_profile']
for path in paths:
    if not os.path.exists(path):
        os.makedirs(path)
