"""Factory for creating STT handlers."""
from utils.stt.streaming import get_stt_service_for_language, STTService
from .wyoming import WyomingSTTHandler
from .traditional import TraditionalSTTHandler


def create_stt_handler(config):
    """Create appropriate STT handler based on configuration."""
    stt_service_enum, _, _ = get_stt_service_for_language(config.language)
    
    print(f'🎯 Creating STT handler: {stt_service_enum} for {config.uid}')
    
    if stt_service_enum == STTService.wyoming:
        return WyomingSTTHandler(config)
    else:
        return TraditionalSTTHandler(config) 