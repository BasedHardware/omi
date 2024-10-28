import uuid
import os
from datetime import datetime, timezone, timedelta
from enum import Enum

import opuslib
import webrtcvad
from fastapi import APIRouter
from fastapi.websockets import WebSocketDisconnect, WebSocket
from pydub import AudioSegment
from starlette.websockets import WebSocketState

import database.memories as memories_db
from database import redis_db
from database.redis_db import get_cached_user_geolocation
from models.memory import Memory, TranscriptSegment, MemoryStatus, Structured, Geolocation
from models.message_event import MemoryEvent, MessageEvent
from utils.memories.location import get_google_maps_location
from utils.memories.process_memory import process_memory
from utils.plugins import trigger_external_integrations, trigger_realtime_integrations
from utils.stt.streaming import *
from utils.webhooks import send_audio_bytes_developer_webhook, realtime_transcript_webhook, \
    get_audio_bytes_webhook_seconds

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
