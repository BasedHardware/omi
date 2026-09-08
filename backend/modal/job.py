import asyncio
import json
import logging
import os

import firebase_admin

from utils.other.jobs import start_job

logging.basicConfig(level=logging.INFO)

logger = logging.getLogger(__name__)


def main() -> None:
    if os.environ.get('SERVICE_ACCOUNT_JSON'):
        service_account_info = json.loads(os.environ["SERVICE_ACCOUNT_JSON"])
        credentials = firebase_admin.credentials.Certificate(service_account_info)
        firebase_admin.initialize_app(credentials)  # type: ignore[reportUnknownMemberType]  # firebase_admin untyped
    else:
        firebase_admin.initialize_app()  # type: ignore[reportUnknownMemberType]  # firebase_admin untyped

    logger.info('Starting job...')
    asyncio.run(start_job())


if __name__ == '__main__':
    main()
