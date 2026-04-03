"""ProactiveAI gRPC server entrypoint."""

import asyncio
import json
import logging
import os

import firebase_admin
import grpc

from proactive.v1 import proactive_pb2_grpc as pb2_grpc

from proactive.service import ProactiveAIServicer

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s %(levelname)s %(name)s: %(message)s',
)
logger = logging.getLogger(__name__)

GRPC_PORT = int(os.environ.get('GRPC_PORT', '50051'))
MAX_MESSAGE_SIZE = 10 * 1024 * 1024  # 10 MB — screenshots can be large


def _init_firebase():
    """Initialize Firebase Admin SDK (same pattern as pusher/main.py)."""
    if firebase_admin._apps:
        return
    if os.environ.get('SERVICE_ACCOUNT_JSON'):
        service_account_info = json.loads(os.environ['SERVICE_ACCOUNT_JSON'])
        credentials = firebase_admin.credentials.Certificate(service_account_info)
        firebase_admin.initialize_app(credentials)
    else:
        firebase_admin.initialize_app()


async def serve():
    """Start the async gRPC server."""
    _init_firebase()

    server = grpc.aio.server(
        options=[
            ('grpc.max_receive_message_length', MAX_MESSAGE_SIZE),
            ('grpc.max_send_message_length', MAX_MESSAGE_SIZE),
            ('grpc.keepalive_time_ms', 30000),
            ('grpc.keepalive_timeout_ms', 10000),
            ('grpc.keepalive_permit_without_calls', True),
        ],
    )
    pb2_grpc.add_ProactiveAIServicer_to_server(ProactiveAIServicer(), server)
    server.add_insecure_port(f'[::]:{GRPC_PORT}')

    logger.info('ProactiveAI gRPC server starting on port %d', GRPC_PORT)
    await server.start()

    try:
        await server.wait_for_termination()
    except KeyboardInterrupt:
        logger.info('Shutting down...')
        await server.stop(grace=5)


if __name__ == '__main__':
    asyncio.run(serve())
