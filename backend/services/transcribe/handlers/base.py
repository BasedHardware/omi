"""Abstract base class for STT handlers."""
from abc import ABC, abstractmethod
from typing import List, Dict, Any
from ..models.config import SessionConfig


class STTHandler(ABC):
    """Abstract base class for STT handlers."""
    
    def __init__(self, config: SessionConfig):
        self.config = config
        self.realtime_segment_buffers = []
        
    @abstractmethod
    async def initialize(self) -> bool:
        """Initialize the STT service. Returns True if successful."""
        pass
    
    @abstractmethod
    async def process_audio(self, audio_data: bytes):
        """Process incoming audio data."""
        pass
    
    @abstractmethod
    async def cleanup(self):
        """Cleanup resources."""
        pass
    
    def stream_transcript(self, segments: List[Dict[str, Any]]):
        """Common method to buffer transcript segments."""
        self.realtime_segment_buffers.extend(segments) 