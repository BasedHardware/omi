import os
import websockets

PusherAPI = os.getenv('HOSTED_PUSHER_API_URL')

async def connect_to_transcript_pusher(uid: str):
    try:
        print("Connecting to Pusher transcripts trigger WebSocket...")
        ws_host = PusherAPI.replace("http", "ws")
        socket = await websockets.connect(f"{ws_host}/v1/trigger/transcript/listen?uid={uid}")
        print("Connected to Pusher transcripts trigger WebSocket.")
        return socket
    except Exception as e:
        print(f"Exception in connect_to_transcript_pusher: {e}")
        raise

async def connect_to_audio_bytes_pusher(uid: str, sample_rate: int = 8000):
    try:
        print("Connecting to Pusher audio bytes trigger WebSocket...")
        ws_host = PusherAPI.replace("http", "ws")
        socket = await websockets.connect(f"{ws_host}/v1/trigger/audio-bytes/listen?uid={uid}&sample_rate={sample_rate}")
        print("Connected to Pusher audio bytes trigger WebSocket.")
        return socket
    except Exception as e:
        print(f"Exception in connect_to_audio_bytes_pusher: {e}")
        raise

async def connect_to_trigger_pusher(uid: str, sample_rate: int = 8000):
    try:
        print("Connecting to Pusher transcripts trigger WebSocket...", uid)
        ws_host = PusherAPI.replace("http", "ws")
        socket = await websockets.connect(f"{ws_host}/v1/trigger/listen?uid={uid}&sample_rate={sample_rate}")
        print("Connected to Pusher transcripts trigger WebSocket.", uid)
        return socket
    except Exception as e:
        print(f"Exception in connect_to_transcript_pusher: {e}", uid)
        raise
