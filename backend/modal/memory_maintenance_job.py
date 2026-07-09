import asyncio
import json
import logging
import os

import firebase_admin

from utils.memory.canonical_short_term_maintenance_cron import (
    run_canonical_short_term_maintenance_cron,
)

logging.basicConfig(level=logging.INFO)

logger = logging.getLogger(__name__)

if os.environ.get('SERVICE_ACCOUNT_JSON'):
    service_account_info = json.loads(os.environ["SERVICE_ACCOUNT_JSON"])
    credentials = firebase_admin.credentials.Certificate(service_account_info)
    firebase_admin.initialize_app(credentials)  # type: ignore[reportUnknownMemberType]  # firebase_admin untyped
else:
    firebase_admin.initialize_app()  # type: ignore[reportUnknownMemberType]  # firebase_admin untyped

logger.info('Starting memory-maintenance-job...')
asyncio.run(run_canonical_short_term_maintenance_cron())
