"""Session configuration model."""
from dataclasses import dataclass
from fastapi.websockets import WebSocket


@dataclass
class SessionConfig:
    """Configuration for a transcription session."""
    websocket: WebSocket
    uid: str
    language: str = 'en'
    sample_rate: int = 8000
    codec: str = 'pcm8'
    channels: int = 1
    include_speech_profile: bool = True
    stt_service: str = None
    including_combined_segments: bool = False
    
    def __post_init__(self):
        # Convert 'auto' to 'multi' for consistency
        if self.language == 'auto':
            self.language = 'multi'
            
        # Handle frame size and codec adjustments
        if self.codec == "opus_fs320":
            self.codec = "opus"
            self.frame_size = 320
        else:
            self.frame_size = 160 