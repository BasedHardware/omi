"""Main WebSocket session coordinator for transcription."""
import os
import time
import uuid
import asyncio
from datetime import datetime, timezone
from starlette.websockets import WebSocketState
from fastapi.websockets import WebSocket, WebSocketDisconnect

from models.message_event import MessageServiceStatusEvent
from .handlers.factory import create_stt_handler
from .utils.heartbeat import HeartbeatManager
from .utils.messaging import MessageSender
from .models.config import SessionConfig


class WebSocketTranscribeSession:
    """Main session handler that coordinates everything."""
    
    def __init__(self, websocket: WebSocket, uid: str, **kwargs):
        self.config = SessionConfig(
            websocket=websocket,
            uid=uid,
            **kwargs
        )
        
        # Components
        self.message_sender = MessageSender(websocket)
        self.heartbeat_manager = HeartbeatManager(websocket, uid)
        
        # STT Handler (will be set during initialization)
        self.stt_handler = None
        
        # Session state
        self.websocket_active = True
        self.websocket_close_code = 1001
    
    async def run(self):
        """Main session runner."""
        print(f'🎤 Starting transcribe session for {self.config.uid}')
        
        if not await self._initialize():
            return
            
        try:
            await self._run_main_loop()
        finally:
            await self._cleanup()
    
    async def _initialize(self):
        """Initialize session components."""
        if not self.config.uid or len(self.config.uid) <= 0:
            await self.config.websocket.close(code=1008, reason="Bad uid")
            return False
        
        # Accept WebSocket
        try:
            await self.config.websocket.accept()
            print(f'✅ WebSocket accepted for {self.config.uid}')
        except RuntimeError as e:
            print(f"❌ WebSocket accept error: {e}")
            await self.config.websocket.close(code=1011, reason="Dirty state")
            return False
        
        # Send initial status
        await self.message_sender.send_status("initiating", "Service Starting")
        
        # Create and initialize STT handler
        try:
            self.stt_handler = create_stt_handler(self.config)
            
            await self.message_sender.send_status("stt_connecting", "Connecting to STT Service")
            
            if not await self.stt_handler.initialize():
                await self.message_sender.send_status("error", "STT Service Failed")
                await self.config.websocket.close(code=1011, reason="STT initialization failed")
                return False
                
            await self.message_sender.send_status("ready", "Ready for Audio")
            return True
            
        except Exception as e:
            print(f"❌ STT initialization error: {e}")
            await self.message_sender.send_status("error", f"Initialization failed: {str(e)}")
            return False
    
    async def _run_main_loop(self):
        """Run main processing loop."""
        # Create tasks
        tasks = [
            asyncio.create_task(self._audio_processing_task()),
            asyncio.create_task(self._transcript_processing_task()),
            asyncio.create_task(self.heartbeat_manager.run_heartbeat()),
        ]
        
        print(f'🎯 All tasks started for {self.config.uid} - listening for audio...')
        
        # Wait for completion
        await asyncio.gather(*tasks, return_exceptions=True)
    
    async def _audio_processing_task(self):
        """Process incoming audio data."""
        self.heartbeat_manager.update_audio_time()
        
        try:
            while self.websocket_active:
                data = await self.config.websocket.receive_bytes()
                self.heartbeat_manager.update_audio_time()
                
                # Process through STT handler
                if self.stt_handler:
                    await self.stt_handler.process_audio(data)
                    
        except WebSocketDisconnect:
            print(f"WebSocket disconnected for {self.config.uid}")
        except Exception as e:
            print(f'❌ Could not process audio for {self.config.uid}: {e}')
            self.websocket_close_code = 1011
        finally:
            self.websocket_active = False
    
    async def _transcript_processing_task(self):
        """Process and send transcript segments to client."""
        while self.websocket_active or len(self.stt_handler.realtime_segment_buffers) > 0:
            try:
                await asyncio.sleep(0.3)  # 300ms
                
                if not self.stt_handler.realtime_segment_buffers:
                    continue
                
                segments = self.stt_handler.realtime_segment_buffers.copy()
                self.stt_handler.realtime_segment_buffers = []
                
                print(f"🔄 Processing {len(segments)} transcript segments for {self.config.uid}")
                
                # Format segments for UI
                formatted_segments = []
                for segment in segments:
                    formatted_segment = {
                        'id': str(uuid.uuid4()),
                        'text': segment.get('text', ''),
                        'speaker': segment.get('speaker', 'SPEAKER_1'),
                        'start': segment.get('start', 0),
                        'end': segment.get('end', 0),
                        'is_user': segment.get('is_user', False),
                        'person_id': segment.get('person_id'),
                    }
                    formatted_segments.append(formatted_segment)
                
                # Send to client
                if formatted_segments:
                    await self.config.websocket.send_json(formatted_segments)
                    
            except Exception as e:
                print(f'❌ Could not process transcript for {self.config.uid}: {e}')
    
    async def _cleanup(self):
        """Cleanup session resources."""
        self.websocket_active = False
        
        if self.stt_handler:
            await self.stt_handler.cleanup()
        
        if self.config.websocket.client_state == WebSocketState.CONNECTED:
            try:
                await self.config.websocket.close(code=self.websocket_close_code)
            except Exception:
                pass
        
        print(f'🔚 Transcribe session ended for {self.config.uid}') 