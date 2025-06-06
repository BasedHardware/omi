#!/usr/bin/env python3
"""
Fixed Omi Wyoming Client - Based on working test client pattern
"""
import asyncio
import logging
from asyncio import Queue
import time
import threading
from typing import Optional

# Wyoming imports
from wyoming.asr import Transcribe, Transcript
from wyoming.audio import AudioStart, AudioStop, AudioChunk
from wyoming.info import Describe, Info
from wyoming.client import AsyncTcpClient

# Omi imports
from omi.bluetooth import listen_to_omi
from omi.decoder import OmiOpusDecoder

OMI_MAC = "machere"
OMI_CHAR_UUID = "19B10001-E8F2-537E-4F6C-D104768A1214"

class OmiAudioBuffer:
    """Audio buffer for Omi streaming - based on test client pattern"""
    
    def __init__(self, interval_seconds=4):
        self.interval_frames = int(interval_seconds * 16000 / 2)  # 16kHz, 16-bit
        self.audio_buffer = []
        self.frame_count = 0
        self.lock = threading.Lock()
        
    def add_audio(self, pcm_data):
        """Add PCM audio data"""
        with self.lock:
            self.audio_buffer.append(pcm_data)
            self.frame_count += len(pcm_data) // 2  # 16-bit samples
            
    def should_extract(self):
        """Check if ready to extract"""
        with self.lock:
            return self.frame_count >= self.interval_frames
            
    def extract_if_ready(self):
        """Extract audio if ready"""
        with self.lock:
            if self.frame_count >= self.interval_frames:
                # Join all audio data
                audio_data = b''.join(self.audio_buffer)
                
                # Keep some overlap (last 25%)
                overlap_size = len(self.audio_buffer) // 4
                self.audio_buffer = self.audio_buffer[-overlap_size:] if overlap_size > 0 else []
                self.frame_count = sum(len(chunk) // 2 for chunk in self.audio_buffer)
                
                return audio_data
        return None

class OmiWyomingTranscriber:
    """Omi transcriber using Wyoming protocol - matches test client pattern"""
    
    def __init__(self, host="localhost", port=10300):
        self.host = host
        self.port = port
        self.audio_buffer = OmiAudioBuffer(interval_seconds=3)
        self.transcription_queue = asyncio.Queue(maxsize=5)
        self.is_running = False
        self.processing_tasks = []
        self.segments_processed = 0
        
    async def start(self):
        """Start the transcriber"""
        print(f"🚀 Starting Omi Wyoming Transcriber")
        
        # Test Wyoming connection first (like test client)
        try:
            print(f"Testing connection to {self.host}:{self.port}...")
            client = AsyncTcpClient(self.host, self.port)
            await asyncio.wait_for(client.connect(), timeout=5)
            
            # Send describe event
            await client.write_event(Describe().event())
            event = await asyncio.wait_for(client.read_event(), timeout=5)
            
            if hasattr(event, 'asr') and event.asr:
                print(f"✅ Connected to Wyoming server: {event.asr[0].name}")
            else:
                print("✅ Connected to Wyoming server")
                
            await client.disconnect()
            
        except Exception as e:
            print(f"❌ Failed to connect to Wyoming service at {self.host}:{self.port}")
            print(f"Error: {e}")
            print("\nMake sure your Wyoming server is running:")
            print("python -m wyoming_universal_stt --uri tcp://0.0.0.0:10300 --model base --backend faster-whisper --data-dir ./models")
            return False
            
        self.is_running = True
        
        # Start transcription processors (like test client)
        for i in range(2):
            task = asyncio.create_task(self._transcription_processor(f"Proc-{i+1}"))
            self.processing_tasks.append(task)
            
        # Start extraction timer
        self.extraction_task = asyncio.create_task(self._extraction_timer())
        
        print("🎤 Omi transcriber ready - listening for audio...")
        return True
        
    def stop(self):
        """Stop the transcriber"""
        print(f"\n🛑 Stopping transcriber (processed {self.segments_processed} segments)")
        self.is_running = False
        
        for task in self.processing_tasks:
            task.cancel()
            
        if hasattr(self, 'extraction_task'):
            self.extraction_task.cancel()
            
    def add_audio_chunk(self, pcm_data):
        """Add audio chunk from Omi"""
        if self.is_running and pcm_data:
            self.audio_buffer.add_audio(pcm_data)
            
    async def _extraction_timer(self):
        """Extract audio at regular intervals"""
        try:
            while self.is_running:
                await asyncio.sleep(1)  # Check every second
                
                try:
                    audio_data = self.audio_buffer.extract_if_ready()
                    if audio_data and len(audio_data) > 16000:  # At least 0.5 seconds
                        try:
                            self.transcription_queue.put_nowait(audio_data)
                            duration = len(audio_data) / (16000 * 2)
                            print(f"📦 Extracted {duration:.1f}s audio segment for transcription")
                        except asyncio.QueueFull:
                            print("⚠️  Transcription queue full, dropping segment")
                except Exception as e:
                    print(f"Extraction error: {e}")
                    
        except asyncio.CancelledError:
            pass
            
    async def _transcription_processor(self, processor_name):
        """Process transcriptions - exactly like test client"""
        try:
            while self.is_running:
                try:
                    audio_data = await asyncio.wait_for(
                        self.transcription_queue.get(), timeout=3.0
                    )
                    
                    await self._transcribe_audio(audio_data, processor_name)
                    self.segments_processed += 1
                    
                except asyncio.TimeoutError:
                    continue
                except Exception as e:
                    print(f"{processor_name} error: {e}")
        except asyncio.CancelledError:
            pass
            
    async def _transcribe_audio(self, audio_data, processor_name):
        """Transcribe audio - copied from working test client"""
        try:
            client = AsyncTcpClient(self.host, self.port)
            await asyncio.wait_for(client.connect(), timeout=5)
            
            # Send transcription request (exact pattern from test client)
            await client.write_event(Transcribe().event())
            await client.write_event(AudioStart(rate=16000, width=2, channels=1).event())
            
            # Send audio in chunks
            chunk_size = 2048
            for i in range(0, len(audio_data), chunk_size):
                chunk_data = audio_data[i:i + chunk_size]
                chunk = AudioChunk(rate=16000, width=2, channels=1, audio=chunk_data)
                await client.write_event(chunk.event())
                
            await client.write_event(AudioStop().event())
            
            # Get result with timeout handling
            timeout_count = 0
            while timeout_count < 8:  # 8 second total timeout
                try:
                    event = await asyncio.wait_for(client.read_event(), timeout=1.0)
                    if event and Transcript.is_type(event.type):
                        transcript = Transcript.from_event(event)
                        text = transcript.text.strip()
                        if text:
                            duration = len(audio_data) / (16000 * 2)
                            print(f"🗣️  [{processor_name}] ({duration:.1f}s): {text}")
                        break
                except asyncio.TimeoutError:
                    timeout_count += 1
                    continue
                    
            await client.disconnect()
            
        except Exception as e:
            print(f"[{processor_name}] Transcription failed: {e}")

async def main():
    """Main function"""
    print("🎙️  OMI WYOMING TRANSCRIBER")
    print("=" * 30)
    
    # Configuration
    WYOMING_HOST = "localhost"
    WYOMING_PORT = 10300
    
    print(f"Wyoming Server: {WYOMING_HOST}:{WYOMING_PORT}")
    print(f"Omi Device: {OMI_MAC}")
    print("=" * 30)
    
    # Create transcriber
    transcriber = OmiWyomingTranscriber(WYOMING_HOST, WYOMING_PORT)
    
    # Test connection first
    if not await transcriber.start():
        print("\n❌ Failed to start transcriber")
        return
        
    # Setup Omi audio handling
    audio_queue = Queue()
    decoder = OmiOpusDecoder()
    
    def handle_ble_data(sender, data):
        """Handle BLE data from Omi"""
        decoded_pcm = decoder.decode_packet(data)
        if decoded_pcm:
            transcriber.add_audio_chunk(decoded_pcm)
            
    print("\n🔄 Starting Omi BLE listener...")
    
    try:
        # Run both Omi listener and transcriber
        await asyncio.gather(
            listen_to_omi(OMI_MAC, OMI_CHAR_UUID, handle_ble_data),
        )
    except KeyboardInterrupt:
        print("\n\n⏹️  Interrupted by user")
    except Exception as e:
        print(f"\n❌ Error: {e}")
    finally:
        transcriber.stop()
        print("👋 Goodbye!")

if __name__ == '__main__':
    # Set up logging
    logging.basicConfig(level=logging.WARNING)
    
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n👋 Goodbye!")