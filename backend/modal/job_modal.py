import json
import os

import firebase_admin

from modal import Image, App, Secret, Cron
from utils.other.notifications import start_cron_job

if os.environ.get('SERVICE_ACCOUNT_JSON'):
    json_str = os.environ["SERVICE_ACCOUNT_JSON"]
    try:
        service_account_info = json.loads(json_str)
    except json.JSONDecodeError:
        # Handle escaped JSON from Coolify (quotes are escaped as \")
        cleaned = json_str.replace('\\', '')
        service_account_info = json.loads(cleaned)

    # Check credential type - Firebase Certificate() only works with service_account
    cred_type = service_account_info.get('type')
    if cred_type == 'service_account':
        credentials = firebase_admin.credentials.Certificate(service_account_info)
        firebase_admin.initialize_app(credentials)
    else:
        # For authorized_user, use default initialization (reads from GOOGLE_APPLICATION_CREDENTIALS)
        firebase_admin.initialize_app()
else:
    firebase_admin.initialize_app()

app = App(
    name='job',
    secrets=[Secret.from_name("gcp-credentials"), Secret.from_name('envs')],
)
image = Image.debian_slim().apt_install('ffmpeg', 'git', 'unzip').pip_install_from_requirements('requirements.txt')


@app.function(image=image, schedule=Cron('* * * * *'))
async def notifications_cronjob():
    await start_cron_job()
