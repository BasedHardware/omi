import json
import os

import firebase_admin

from modal import Image, App, Secret, Cron
from utils.other.notifications import start_cron_job

if os.environ.get('SERVICE_ACCOUNT_JSON'):
    service_account_info = json.loads(os.environ["SERVICE_ACCOUNT_JSON"])
    credentials = firebase_admin.credentials.Certificate(service_account_info)
    firebase_admin.initialize_app(credentials)
else:
    firebase_admin.initialize_app()

app = App(
    name='job',
    secrets=[Secret.from_name("gcp-credentials"), Secret.from_name('envs')],
)
image = (
    Image.debian_slim()
    .apt_install('ffmpeg', 'git', 'unzip')
    .pip_install_from_requirements('requirements.txt')
)

@app.function(image=image, schedule=Cron('* * * * *'))
async def notifications_cronjob():
    await start_cron_job()
