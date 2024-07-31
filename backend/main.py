import json
import os
import subprocess

import firebase_admin
from fastapi import FastAPI

from modal import Image, App, asgi_app, Secret, mount
from routers import backups, chat, memories, plugins, proactivity, speech_profile, transcribe
from utils.redis_utils import migrate_user_plugins_reviews
from utils.storage import retrieve_all_samples
from utils.stt.soniox_util import create_speaker_profile, uid_has_speech_profile

if os.environ.get('SERVICE_ACCOUNT_JSON'):
    service_account_info = json.loads(os.environ["SERVICE_ACCOUNT_JSON"])
    print(service_account_info)
    credentials = firebase_admin.credentials.Certificate(service_account_info)
    firebase_admin.initialize_app(credentials)
else:
    firebase_admin.initialize_app()

app = FastAPI()
app.include_router(transcribe.router)
app.include_router(memories.router)
app.include_router(chat.router)
app.include_router(plugins.router)
app.include_router(proactivity.router)
app.include_router(speech_profile.router)
app.include_router(backups.router)

modal_app = App(
    name='api',
    secrets=[
        Secret.from_name("gcp-credentials"),
        Secret.from_name("huggingface-token"),
        Secret.from_dotenv('.env')
    ],
    mounts=[
        # mount.Mount.from_local_dir('pretrained_models'),
        mount.Mount.from_local_dir('templates/', remote_path='templates/'),
    ]
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
    print('fastapi_app')
    return app


paths = ['_temp', '_samples', '_segments', '_speaker_profile']
for path in paths:
    if not os.path.exists(path):
        os.makedirs(path)


@app.get('/health')
async def health():
    result = subprocess.run(["du -sh _temp"], shell=True, stdout=subprocess.PIPE)
    return result


@app.post('/migrate-user')
def migrate_user(prev_uid: str, new_uid: str):
    migrate_user_plugins_reviews(prev_uid, new_uid)
    has_speech_profile = uid_has_speech_profile(prev_uid)
    if has_speech_profile:
        base_path = retrieve_all_samples(prev_uid)
        count = len(os.listdir(base_path))
        if count > 0:
            print('base_path', base_path, 'count', count)
            create_speaker_profile(new_uid, base_path)
    return {'status': 'ok'}


@app.post('/webhook')
def receive(data: dict):
    print(data)
    return 'ok'
