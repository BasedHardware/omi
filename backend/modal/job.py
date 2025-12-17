import json
import os

import firebase_admin
import asyncio

from utils.other.jobs import start_job

if os.environ.get('SERVICE_ACCOUNT_JSON'):
    service_account_info = json.loads(os.environ["SERVICE_ACCOUNT_JSON"])
    credentials = firebase_admin.credentials.Certificate(service_account_info)
    firebase_admin.initialize_app(credentials)
else:
    firebase_admin.initialize_app()

print('Starting job...')
asyncio.run(start_job())
