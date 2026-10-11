import asyncio
import json
import logging
import os
from pathlib import Path
import time

from prometheus_client import start_http_server

import firebase_admin

from utils.env_loader import firebase_admin_options
from utils.other.jobs import start_job

logging.basicConfig(level=logging.INFO)

logger = logging.getLogger(__name__)


def main() -> None:
    metrics_server = None
    if os.environ.get('PROMETHEUS_SIDECAR_PORT'):
        metrics_server, _thread = start_http_server(int(os.environ['PROMETHEUS_SIDECAR_PORT']), addr='127.0.0.1')
    try:
        if os.environ.get('SERVICE_ACCOUNT_JSON'):
            service_account_info = json.loads(os.environ["SERVICE_ACCOUNT_JSON"])
            credentials = firebase_admin.credentials.Certificate(service_account_info)
            firebase_admin.initialize_app(credentials, options=firebase_admin_options())  # type: ignore[reportUnknownMemberType]  # firebase_admin untyped
        else:
            firebase_admin.initialize_app(options=firebase_admin_options())  # type: ignore[reportUnknownMemberType]  # firebase_admin untyped

        logger.info('Starting job...')
        asyncio.run(start_job())
    finally:
        if metrics_server is not None:
            # Keep loopback alive for a final 30s scrape before the collector's
            # graceful shutdown. The shared marker also lets the sidecar exit.
            done_file = os.environ.get('PROMETHEUS_SIDECAR_DONE_FILE')
            if done_file:
                Path(done_file).touch()
                time.sleep(45)
            metrics_server.shutdown()
            metrics_server.server_close()


if __name__ == '__main__':
    main()
