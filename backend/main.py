import json
import os

import firebase_admin
from fastapi import FastAPI

from modal import Image, App, asgi_app, Secret
from routers import backups, chat, memories, plugins, speech_profile, transcribe, screenpipe

if os.environ.get('SERVICE_ACCOUNT_JSON'):
    service_account_info = json.loads(os.environ["SERVICE_ACCOUNT_JSON"])
    credentials = firebase_admin.credentials.Certificate(service_account_info)
    firebase_admin.initialize_app(credentials)
else:
    firebase_admin.initialize_app()

app = FastAPI()
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
    timeout=24 * 60 * 60,  # avoid timeout with websocket
)
@asgi_app()
def fastapi_app():
    print('fastapi_app')
    return app


paths = ['_temp', '_samples', '_segments', '_speaker_profile']
for path in paths:
    if not os.path.exists(path):
        os.makedirs(path)
