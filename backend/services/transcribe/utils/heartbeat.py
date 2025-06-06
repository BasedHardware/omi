"""Heartbeat management for WebSocket connections."""
import time
import asyncio
from fastapi.websockets import WebSocket


class HeartbeatManager:
    """Manages WebSocket heartbeat to keep connections alive."""
    
    def __init__(self, websocket: WebSocket, uid: str):
        self.websocket = websocket
        self.uid = uid
        self.last_audio_time = time.time()
        self.last_heartbeat_time = time.time()
        self.heartbeat_interval = 30  # seconds
        self.audio_timeout = 60  # seconds
        
    def update_audio_time(self):
        """Update the last audio activity timestamp."""
        self.last_audio_time = time.time()
        
    async def run_heartbeat(self):
        """Run the heartbeat loop."""
        while True:
            try:
                current_time = time.time()
                
                # Check for audio timeout
                if current_time - self.last_audio_time > self.audio_timeout:
                    print(f"⚠️ Audio timeout for {self.uid}")
                    await self.websocket.close(code=1000, reason="Audio timeout")
                    break
                
                # Send heartbeat if needed
                if current_time - self.last_heartbeat_time > self.heartbeat_interval:
                    try:
                        await self.websocket.send_json({"type": "heartbeat"})
                        self.last_heartbeat_time = current_time
                    except Exception as e:
                        print(f"❌ Heartbeat failed for {self.uid}: {e}")
                        break
                
                await asyncio.sleep(1)
                
            except Exception as e:
                print(f"❌ Heartbeat error for {self.uid}: {e}")
                break 