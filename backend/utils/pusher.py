import os
import random
import asyncio
import websockets

PusherAPI = os.getenv('HOSTED_PUSHER_API_URL')

async def connect_to_trigger_pusher(uid: str, sample_rate: int = 8000, retries: int = 3):
    print("connect_to_trigger_pusher")
    for attempt in range(retries):
        try:
            return await _connect_to_trigger_pusher(uid, sample_rate)
        except Exception as error:
            print(f'An error occurred: {error}')
            if attempt == retries - 1:
                raise
        backoff_delay = calculate_backoff_with_jitter(attempt)
        print(f"Waiting {backoff_delay:.0f}ms before next retry...")
        await asyncio.sleep(backoff_delay / 1000)

    raise Exception(f'Could not open socket: All retry attempts failed.')

async def _connect_to_trigger_pusher(uid: str, sample_rate: int = 8000):
    try:
        print("Connecting to Pusher transcripts trigger WebSocket...", uid)
        ws_host = PusherAPI.replace("http", "ws")
        socket = await websockets.connect(f"{ws_host}/v1/trigger/listen?uid={uid}&sample_rate={sample_rate}")
        print("Connected to Pusher transcripts trigger WebSocket.", uid)
        return socket
    except Exception as e:
        print(f"Exception in connect_to_transcript_pusher: {e}", uid)
        raise


# Calculate backoff with jitter
def calculate_backoff_with_jitter(attempt, base_delay=1000, max_delay=15000):
    jitter = random.random() * base_delay
    backoff = min(((2 ** attempt) * base_delay) + jitter, max_delay)
    return backoff
