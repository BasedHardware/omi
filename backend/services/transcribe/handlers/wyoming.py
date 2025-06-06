"""Wyoming STT handler implementation."""
import opuslib
from .base import STTHandler
from utils.stt.streaming import process_audio_wyoming


class WyomingSTTHandler(STTHandler):
    """Handler for Wyoming STT service."""
    
    def __init__(self, config):
        super().__init__(config)
        self.wyoming_send_audio = None
        self.wyoming_cleanup = None
        self.decoder = None
        
    async def initialize(self) -> bool:
        """Initialize Wyoming STT service."""
        try:
            print(f'🐍 Initializing Wyoming STT for {self.config.uid}')
            
            # Initialize Opus decoder if needed
            if self.config.codec == 'opus' and self.config.sample_rate == 16000:
                self.decoder = opuslib.Decoder(self.config.sample_rate, 1)
                print(f'🎵 Opus decoder initialized for {self.config.sample_rate}Hz')
            
            # Initialize Wyoming connection
            self.wyoming_send_audio, self.wyoming_cleanup = await process_audio_wyoming(
                self.stream_transcript, 
                self.config.language, 
                self.config.sample_rate, 
                self.config.channels, 
                preseconds=0
            )
            
            print(f'✅ Wyoming STT initialized successfully for {self.config.uid}')
            return True
            
        except Exception as e:
            print(f'❌ Wyoming initialization failed for {self.config.uid}: {e}')
            return False
    
    async def process_audio(self, audio_data: bytes):
        """Process audio through Wyoming STT."""
        try:
            # Decode Opus if needed
            if self.decoder:
                try:
                    audio_data = self.decoder.decode(bytes(audio_data), frame_size=self.config.frame_size)
                except Exception as e:
                    print(f"❌ Opus decode error for {self.config.uid}: {e}")
                    return
            
            # Send to Wyoming STT
            if self.wyoming_send_audio:
                await self.wyoming_send_audio(audio_data)
                
        except Exception as e:
            print(f"❌ Error processing audio in Wyoming for {self.config.uid}: {e}")
            raise
    
    async def cleanup(self):
        """Cleanup Wyoming resources."""
        try:
            if self.wyoming_cleanup:
                await self.wyoming_cleanup()
                print(f"🧹 Wyoming cleanup completed for {self.config.uid}")
        except Exception as e:
            print(f"❌ Error during Wyoming cleanup for {self.config.uid}: {e}") 