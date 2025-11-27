import json
import os

import firebase_admin
from fastapi import FastAPI

from routers import pusher

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
        # For authorized_user, use default initialization with explicit project ID
        project_id = os.environ.get('GOOGLE_CLOUD_PROJECT') or service_account_info.get('quota_project_id')
        options = {'projectId': project_id} if project_id else None
        firebase_admin.initialize_app(options=options)
else:
    firebase_admin.initialize_app()

app = FastAPI()
app.include_router(pusher.router)


@app.get("/health")
async def health():
    return {"status": "ok"}


paths = ['_temp', '_samples', '_segments', '_speech_profiles']
for path in paths:
    if not os.path.exists(path):
        os.makedirs(path)
