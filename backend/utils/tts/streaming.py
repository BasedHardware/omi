import json
import os
import threading
import asyncio

import websockets
from websockets.sync.client import connect

# TTS Websocket
TIMEOUT = 0.050
CHANNELS = 1
RATE = 48000
CHUNK = 8000
VOICE="aura-angus-en"
DEFAULT_URL = f"wss://api.deepgram.com/v1/speak?encoding=linear16&sample_rate={RATE}&voice={VOICE}"
DEEPGRAM_API_KEY = os.environ.get("DEEPGRAM_API_KEY", None)
_socket = None

def connect_to_deepgram(on_message, on_error, language: str, sample_rate: int, channels: int):
    global _socket
    print(f"Connecting to {DEFAULT_URL}")

    _socket = connect(
        DEFAULT_URL, additional_headers={"Authorization": f"Token {DEEPGRAM_API_KEY}"}
    )

def speak_dg():

    _story = [
        "The sun had just begun to rise over the sleepy town of Millfield.",
        "Emily a young woman in her mid-twenties was already awake and bustling about.",
    ]

    async def receiver():
        try:
            while True:
                message = _socket.recv()
                if message is None:
                    continue

                if type(message) is str:
                    # Websocket Lifecycle Messages
                    print(message)
                # TODO send to device
                # elif type(message) is bytes:
                    # audio is in message as binary audio
        except Exception as e:
            print(f"receiver: {e}")

    _receiver_thread = threading.Thread(target=asyncio.run, args=(receiver(),))
    _receiver_thread.start()

    for text_input in _story:
        print(f"Sending: {text_input}")
        _socket.send(json.dumps({"type": "Speak", "text": text_input}))

    print("Flushing...")
    _socket.send(json.dumps({"type": "Flush"}))
    _socket.send(json.dumps({"type": "Close"}))
    _socket.close()
# END TTS Websocket
