"""Traditional STT handlers (Deepgram, Soniox, Speechmatics)."""
import time
import opuslib
from pydub import AudioSegment

from .base import STTHandler
from utils.stt.streaming import (
    get_stt_service_for_language, STTService,
    process_audio_dg, process_audio_soniox, process_audio_speechmatics,
    send_initial_file_path
)
from utils.other.storage import get_profile_audio_if_exists
from utils.other.task import safe_create_task


class TraditionalSTTHandler(STTHandler):
    """Handler for traditional STT services (Deepgram, Soniox, Speechmatics)."""
    
    def __init__(self, config):
        super().__init__(config)
        # STT sockets
        self.soniox_socket = None
        self.soniox_socket2 = None
        self.speechmatics_socket = None
        self.deepgram_socket = None
        self.deepgram_socket2 = None
        
        # Audio processing
        self.decoder = None
        self.speech_profile_duration = 0
        self.timer_start = time.time()
        
        # Service info
        self.stt_service = None
        self.stt_model = None
        
    async def initialize(self) -> bool:
        """Initialize traditional STT services."""
        try:
            # Get STT service details
            self.stt_service, stt_language, self.stt_model = STTService.deepgram, 'multi', 'nova-3'
            
            if not self.stt_service or not stt_language:
                print(f"❌ STT service not available for language {self.config.language}")
                return False
            
            print(f'🔄 Initializing {self.stt_service} STT for {self.config.uid}')
            
            # Initialize decoder if needed
            if self.config.codec == 'opus' and self.config.sample_rate == 16000:
                self.decoder = opuslib.Decoder(self.config.sample_rate, 1)
                print(f'🎵 Opus decoder initialized for {self.config.sample_rate}Hz')
            
            # Handle speech profile
            file_path = await self._setup_speech_profile()
            
            # Initialize specific service
            if self.stt_service == STTService.deepgram:
                await self._init_deepgram(stt_language, file_path)
            elif self.stt_service == STTService.soniox:
                await self._init_soniox(stt_language, file_path)
            elif self.stt_service == STTService.speechmatics:
                await self._init_speechmatics(stt_language, file_path)
                
            print(f'✅ {self.stt_service} STT initialized successfully for {self.config.uid}')
            return True
            
        except Exception as e:
            print(f'❌ Traditional STT initialization failed for {self.config.uid}: {e}')
            return False
    
    async def _setup_speech_profile(self):
        """Setup speech profile if needed."""
        file_path = None
        if (self.config.language in ['en', 'auto'] and 
            self.config.codec in ['opus', 'pcm16'] and 
            self.config.include_speech_profile):
            
            file_path = get_profile_audio_if_exists(self.config.uid)
            self.speech_profile_duration = (
                AudioSegment.from_wav(file_path).duration_seconds + 5 
                if file_path else 0
            )
            print(f'📄 Speech profile duration: {self.speech_profile_duration}s for {self.config.uid}')
        
        return file_path
    
    async def _init_deepgram(self, stt_language, file_path):
        """Initialize Deepgram STT."""
        print(f"🎯 Initializing Deepgram with language: {stt_language}")
        
        self.deepgram_socket = await process_audio_dg(
            self.stream_transcript, 
            stt_language, 
            self.config.sample_rate, 
            1, 
            preseconds=self.speech_profile_duration, 
            model=self.stt_model
        )
        
        if self.speech_profile_duration and file_path:
            self.deepgram_socket2 = await process_audio_dg(
                self.stream_transcript, 
                stt_language, 
                self.config.sample_rate, 
                1, 
                model=self.stt_model
            )
            
            async def deepgram_socket_send(data):
                return self.deepgram_socket.send(data)
            
            safe_create_task(send_initial_file_path(file_path, deepgram_socket_send))
            print(f'📄 Deepgram speech profile loaded for {self.config.uid}')
    
    async def _init_soniox(self, stt_language, file_path):
        """Initialize Soniox STT."""
        print(f"🎯 Initializing Soniox with language: {stt_language}")
        
        # For multi-language detection, provide language hints if available
        hints = None
        if stt_language == 'multi' and self.config.language != 'multi':
            hints = [self.config.language]
            print(f"🔍 Soniox language hints: {hints}")
        
        self.soniox_socket = await process_audio_soniox(
            self.stream_transcript, 
            self.config.sample_rate, 
            stt_language,
            self.config.uid if self.config.include_speech_profile else None,
            preseconds=self.speech_profile_duration,
            language_hints=hints
        )
        
        if self.speech_profile_duration and file_path:
            self.soniox_socket2 = await process_audio_soniox(
                self.stream_transcript, 
                self.config.sample_rate, 
                stt_language,
                self.config.uid if self.config.include_speech_profile else None,
                language_hints=hints
            )
            safe_create_task(send_initial_file_path(file_path, self.soniox_socket.send))
            print(f'📄 Soniox speech profile loaded for {self.config.uid}')
    
    async def _init_speechmatics(self, stt_language, file_path):
        """Initialize Speechmatics STT."""
        print(f"🎯 Initializing Speechmatics with language: {stt_language}")
        
        self.speechmatics_socket = await process_audio_speechmatics(
            self.stream_transcript, 
            self.config.sample_rate, 
            stt_language, 
            preseconds=self.speech_profile_duration
        )
        
        if self.speech_profile_duration and file_path:
            safe_create_task(send_initial_file_path(file_path, self.speechmatics_socket.send))
            print(f'📄 Speechmatics speech profile loaded for {self.config.uid}')
    
    async def process_audio(self, audio_data: bytes):
        """Process audio through traditional STT services."""
        try:
            # Decode Opus if needed
            if self.decoder:
                try:
                    audio_data = self.decoder.decode(bytes(audio_data), frame_size=self.config.frame_size)
                except Exception as e:
                    print(f"❌ Opus decode error for {self.config.uid}: {e}")
                    return
            
            # Determine which socket to use based on speech profile timing
            elapsed_seconds = time.time() - self.timer_start
            
            # Send to appropriate STT service
            if self.soniox_socket:
                await self._send_to_soniox(audio_data, elapsed_seconds)
            elif self.speechmatics_socket:
                await self.speechmatics_socket.send(audio_data)
            elif self.deepgram_socket:
                self._send_to_deepgram(audio_data, elapsed_seconds)
                    
        except Exception as e:
            print(f"❌ Error processing audio in traditional STT for {self.config.uid}: {e}")
            raise
    
    async def _send_to_soniox(self, audio_data: bytes, elapsed_seconds: float):
        """Send audio to Soniox sockets."""
        if elapsed_seconds > self.speech_profile_duration or not self.soniox_socket2:
            await self.soniox_socket.send(audio_data)
            if self.soniox_socket2:
                print(f'🔄 Switching to main Soniox socket for {self.config.uid}')
                await self.soniox_socket2.close()
                self.soniox_socket2 = None
        else:
            await self.soniox_socket2.send(audio_data)
    
    def _send_to_deepgram(self, audio_data: bytes, elapsed_seconds: float):
        """Send audio to Deepgram sockets."""
        if elapsed_seconds > self.speech_profile_duration or not self.deepgram_socket2:
            self.deepgram_socket.send(audio_data)
            if self.deepgram_socket2:
                print(f'🔄 Switching to main Deepgram socket for {self.config.uid}')
                self.deepgram_socket2.finish()
                self.deepgram_socket2 = None
        else:
            self.deepgram_socket2.send(audio_data)
    
    async def cleanup(self):
        """Cleanup traditional STT resources."""
        try:
            if self.deepgram_socket:
                self.deepgram_socket.finish()
            if self.deepgram_socket2:
                self.deepgram_socket2.finish()
            if self.soniox_socket:
                await self.soniox_socket.close()
            if self.soniox_socket2:
                await self.soniox_socket2.close()
            if self.speechmatics_socket:
                await self.speechmatics_socket.close()
                
            print(f"🧹 Traditional STT cleanup completed for {self.config.uid}")
        except Exception as e:
            print(f"❌ Error during traditional STT cleanup for {self.config.uid}: {e}")