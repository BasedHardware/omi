import os
import wave
from datetime import datetime
from typing import Optional
import numpy as np
import uvicorn
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from opuslib import Decoder as OpusDecoder

# Create the FastAPI app
app = FastAPI(title="Omi Audio Processor")

# Create directory for storing received audio
os.makedirs("audio_files", exist_ok=True)

# Opus decoding constants
SAMPLE_RATE = 16000
CHANNELS = 1
FRAME_SIZE = 960  # 60ms of audio at 16kHz (using exact same value as SDK)

def debug_packet(data):
    """Debug an incoming packet"""
    print(f"Packet size: {len(data)} bytes")
    if len(data) > 4:
        first_bytes = [b for b in data[:4]]
        print(f"First 4 bytes: {first_bytes}")

def decode_omi_packet(data: bytes, decoder: OpusDecoder) -> Optional[np.ndarray]:
    """Decode an Omi Opus packet using the same logic as the SDK"""
    if len(data) <= 3:
        return None
    
    # Remove 3-byte header (exactly like SDK)
    # clean_data = data[3:]
    clean_data = data
    
    try:
        # Use exact same parameters as SDK
        pcm = decoder.decode(clean_data, FRAME_SIZE, decode_fec=False)
        return pcm
    except Exception as e:
        print(f"Opus decode error: {e}")
        return None

class ConnectionManager:
    def __init__(self):
        self.active_connections = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)
        return len(self.active_connections)

    def disconnect(self, websocket: WebSocket):
        self.active_connections.remove(websocket)
        return len(self.active_connections)

    async def send_text(self, message: str, websocket: WebSocket):
        await websocket.send_text(message)

manager = ConnectionManager()
@app.get("/")
async def root():
    return {"message": "Omi Audio Processor API. Connect to /ws for WebSocket audio processing."}

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    # Accept the WebSocket connection
    client_id = await manager.connect(websocket)
    print(f"Client #{client_id} connected")
    
    # Create a buffer to store opus data chunks
    opus_buffer = bytearray()
    
    # Generate a unique filename for this session
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    raw_filename = f"audio_files/opus_raw_{timestamp}_{client_id}.opus"
    decoded_filename = f"audio_files/decoded_{timestamp}_{client_id}.wav"
    
    # Initialize opus decoder (matching SDK settings)
    opus_decoder = OpusDecoder(SAMPLE_RATE, CHANNELS)
    pcm_buffer = []
    
    # Track statistics
    packets_received = 0
    packets_decoded = 0
    
    try:
        # Main WebSocket receive loop
        while True:
            # Receive binary data from WebSocket
            data = await websocket.receive_bytes()
            packets_received += 1
            
            
            # Save the raw packet for analysis
            opus_buffer.extend(data)
            
            # Decode using the Omi SDK approach
            pcm_frame = decode_omi_packet(data, opus_decoder)
            
            if pcm_frame is not None:
                # Successfully decoded
                pcm_buffer.append(pcm_frame)
                packets_decoded += 1
                print(f"Success! Decoded {len(data)} bytes into {len(pcm_frame)} PCM samples")
                await manager.send_text(f"Received and decoded {len(data)} bytes", websocket)
            else:

                # Debug packet for analysis
                debug_packet(data)

                # Failed to decode
                print(f"Failed to decode packet #{packets_received}. Data: {len(data)} bytes")
                await manager.send_text(f"Received {len(data)} bytes (decoding failed)", websocket)
            
            # Print stats periodically
            if packets_received % 10 == 0:
                success_rate = (packets_decoded / packets_received) * 100
                print(f"Stats: {packets_decoded}/{packets_received} packets decoded ({success_rate:.1f}%)")
    
    except WebSocketDisconnect:
        # Client disconnected
        remaining = manager.disconnect(websocket)
        print(f"Client #{client_id} disconnected. {remaining} clients remaining.")
        
        # Save the raw opus data
        with open(raw_filename, "wb") as f:
            f.write(opus_buffer)
        print(f"Saved raw opus data to {raw_filename}")
        
        # Print final statistics
        if packets_received > 0:
            success_rate = (packets_decoded / packets_received) * 100
            print(f"Final stats: {packets_decoded}/{packets_received} packets decoded ({success_rate:.1f}%)")
        
        # Save decoded PCM audio if we have any
        if pcm_buffer:
            try:
                # Concatenate all PCM frames
                pcm_data = np.concatenate(pcm_buffer)
                
                # Save as WAV file
                with wave.open(decoded_filename, 'wb') as wf:
                    wf.setnchannels(CHANNELS)
                    wf.setsampwidth(2)  # 2 bytes per sample (16-bit)
                    wf.setframerate(SAMPLE_RATE)
                    wf.writeframes(pcm_data.tobytes())
                
                print(f"Saved decoded audio to {decoded_filename}")
                print(f"Audio stats: {CHANNELS} channels, {SAMPLE_RATE} Hz, {len(pcm_data)/SAMPLE_RATE:.2f} seconds")
            except Exception as e:
                print(f"Error saving decoded audio: {e}")
        else:
            print("No PCM data was successfully decoded")
            
            # Create a placeholder WAV with silence
            silence = np.zeros(16000, dtype=np.int16)  # 1 second of silence at 16kHz
            with wave.open(decoded_filename, 'wb') as wf:
                wf.setnchannels(CHANNELS)
                wf.setsampwidth(2)  # 2 bytes per sample (16-bit)
                wf.setframerate(SAMPLE_RATE)
                wf.writeframes(silence.tobytes())
            print(f"Created placeholder WAV file at {decoded_filename}")

if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8005, reload=True)