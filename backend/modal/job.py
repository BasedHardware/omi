import json
import os

import firebase_admin
import asyncio

from utils.other.notifications import start_cron_job

if os.environ.get('SERVICE_ACCOUNT_JSON'):
    json_str = os.environ["SERVICE_ACCOUNT_JSON"]
    try:
        service_account_info = json.loads(json_str)
    except json.JSONDecodeError:
        # Handle escaped JSON from Coolify (quotes are escaped as \")
        cleaned = json_str.replace('\\', '')
        service_account_info = json.loads(cleaned)
    credentials = firebase_admin.credentials.Certificate(service_account_info)
    firebase_admin.initialize_app(credentials)
else:
    firebase_admin.initialize_app()

print('Starting cron job...')
asyncio.run(start_cron_job())
