#!/usr/bin/env python3
"""
Simple test script to verify ElevenLabs Scribe STT integration
"""
import os
import asyncio
from io import BytesIO
from utils.stt.streaming import process_audio_elevenlabs, get_stt_service_for_language

async def test_elevenlabs_stt():
    """Test ElevenLabs Scribe STT service"""
    print("Testing ElevenLabs Scribe STT integration...")
    
    # Check if API key is set
    api_key = os.getenv('ELEVENLABS_API_KEY')
    if not api_key:
        print("ERROR: ELEVENLABS_API_KEY environment variable is not set")
        return False
    
    # Test service selection
    service, language, model = get_stt_service_for_language('en')
    print(f"Selected STT service: {service}, language: {language}, model: {model}")
    
    if service != 'elevenlabs':
        print("WARNING: ElevenLabs is not the primary STT service")
        print("Make sure STT_SERVICE_MODELS environment variable includes 'el-scribe' first")
    
    # Test creating ElevenLabs socket
    segments_received = []
    
    def stream_transcript(segments):
        print(f"Received segments: {segments}")
        segments_received.extend(segments)
    
    try:
        # Create ElevenLabs socket
        socket = await process_audio_elevenlabs(
            stream_transcript, 
            sample_rate=16000, 
            language='eng', 
            preseconds=0,
            model='scribe_v1'
        )
        
        print("ElevenLabs socket created successfully")
        
        # Test sending some dummy audio data
        dummy_audio = b'\x00' * 3200  # 100ms of silence at 16kHz
        await socket.send(dummy_audio)
        
        # Close the socket
        await socket.close()
        
        print("ElevenLabs socket closed successfully")
        return True
        
    except Exception as e:
        print(f"ERROR: Failed to test ElevenLabs STT: {e}")
        return False

if __name__ == "__main__":
    # Set default values for testing if not present
    if not os.getenv('STT_SERVICE_MODELS'):
        os.environ['STT_SERVICE_MODELS'] = 'el-scribe'
    
    result = asyncio.run(test_elevenlabs_stt())
    if result:
        print("\n✅ ElevenLabs Scribe STT integration test PASSED")
    else:
        print("\n❌ ElevenLabs Scribe STT integration test FAILED")