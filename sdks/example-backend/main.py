import asyncio
import io
import os
import wave
from datetime import datetime

import numpy as np
import soundfile as sf
import uvicorn
from fastapi import FastAPI, File, Response, UploadFile, WebSocket, WebSocketDisconnect
from opuslib import Decoder as OpusDecoder

# Create the FastAPI app
app = FastAPI(title="Omi Audio Processor")

# Create directory for storing received audio
os.makedirs("audio_files", exist_ok=True)

# Opus decoding constants
SAMPLE_RATE = 16000
CHANNELS = 1
FRAME_SIZE = 960  # 60ms of audio at 16kHz (typical Opus frame size)
MAX_FRAME_SIZE = 6 * 960  # Maximum size for opus frame at 48kHz

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
    
    # Initialize opus decoder
    opus_decoder = OpusDecoder(SAMPLE_RATE, CHANNELS)
    pcm_buffer = []
    
    try:
        # Main WebSocket receive loop
        while True:
            # Receive binary data from WebSocket
            data = await websocket.receive_bytes()
            
            # Debug packet for analysis
            debug_packet(data)
            
            # If we received the first 3 bytes as header, remove them
            # Based on the Omi SDK which trims the first 3 bytes (header)
            if len(data) > 3:
                # Skip the 3-byte header
                audio_data = data[3:]
                opus_buffer.extend(audio_data)
                
                # Try to decode the frame
                try:
                    # Try different frame sizes instead of a fixed size
                    frame_sizes = [960, 1920, 2880]  # Standard Opus frame sizes
                    success = False
                    
                    for size in frame_sizes:
                        try:
                            pcm_frame = opus_decoder.decode(audio_data, size)
                            pcm_buffer.append(pcm_frame)
                            print(f"Success! Decoded {len(audio_data)} bytes of Opus data into {len(pcm_frame)} PCM samples using frame size {size}")
                            success = True
                            break
                        except Exception as decode_err:
                            # Continue trying different sizes
                            pass
                    
                    if not success:
                        print(f"Warning: Couldn't decode frame with any size: corrupted stream?")
                        # Debug the raw data further
                        print(f"Frame data summary: first 4 bytes: {[b for b in audio_data[:4]]}, size: {len(audio_data)}")
                
                except Exception as e:
                    print(f"Warning: Error in decoding process: {e}")
                
                # Log received data size
                print(f"Received {len(data)} bytes, added {len(audio_data)} bytes to buffer")
                
                # Acknowledge receipt
                await manager.send_text(f"Received {len(data)} bytes", websocket)
            else:
                # If we receive a small packet, just add it to the buffer
                opus_buffer.extend(data)
                print(f"Received small packet: {len(data)} bytes")
                await manager.send_text(f"Received small packet: {len(data)} bytes", websocket)
    
    except WebSocketDisconnect:
        # Client disconnected
        remaining = manager.disconnect(websocket)
        print(f"Client #{client_id} disconnected. {remaining} clients remaining.")
        
        # Save the raw opus data
        with open(raw_filename, "wb") as f:
            f.write(opus_buffer)
        print(f"Saved raw opus data to {raw_filename}")
        
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

# File upload endpoint for Opus files
@app.post("/decode_opus/")
async def decode_opus(file: UploadFile = File(...)):
    # Read uploaded file into memory
    data = await file.read()
    
    # Generate output filename
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_filename = f"audio_files/uploaded_{timestamp}.wav"
    
    try:
        # Initialize opus decoder
        opus_decoder = OpusDecoder(SAMPLE_RATE, CHANNELS)
        pcm_buffer = []
        
        # Process the opus data in chunks - we'll try to detect frame boundaries
        # This is a simplified approach and may not work for all opus files
        offset = 0
        frames_decoded = 0
        
        # Save the raw file for analysis
        raw_filename = f"audio_files/raw_upload_{timestamp}.opus"
        with open(raw_filename, "wb") as f:
            f.write(data)
        print(f"Saved raw uploaded data to {raw_filename}")
        
        # Define common Opus frame sizes to try
        frame_sizes = [960, 1920, 2880]
        
        while offset < len(data) and frames_decoded < 1000:  # Limit to prevent infinite loops
            # Debug the current chunk
            if offset < len(data):
                chunk_info = f"Chunk at offset {offset}: "
                if offset + 16 <= len(data):
                    chunk_info += f"hex: {data[offset:offset+16].hex()[:24]}..."
                else:
                    chunk_info += f"hex: {data[offset:].hex()[:24]}..."
                print(chunk_info)
            
            # Try all frame sizes
            decoded = False
            for frame_size in frame_sizes:
                try:
                    if offset + frame_size <= len(data):
                        frame = data[offset:offset+frame_size]
                        pcm_frame = opus_decoder.decode(frame, frame_size)
                        pcm_buffer.append(pcm_frame)
                        offset += frame_size
                        frames_decoded += 1
                        if frames_decoded % 10 == 0:  # Log every 10 frames
                            print(f"Decoded {frames_decoded} frames so far, current size: {frame_size}")
                        decoded = True
                        break
                except Exception as e:
                    # Try next size
                    continue
            
            if not decoded:
                # If no size worked, move forward by one byte and try again
                offset += 1
                if offset % 100 == 0:  # Don't log too much
                    print(f"Skipped to offset {offset}, no valid frame found")
        
        # If we successfully decoded any frames
        if pcm_buffer:
            # Concatenate all PCM frames
            pcm_data = np.concatenate(pcm_buffer)
            
            # Save as WAV file
            with wave.open(output_filename, 'wb') as wf:
                wf.setnchannels(CHANNELS)
                wf.setsampwidth(2)  # 2 bytes per sample (16-bit)
                wf.setframerate(SAMPLE_RATE)
                wf.writeframes(pcm_data.tobytes())
            
            # Return the WAV file
            with open(output_filename, 'rb') as f:
                wav_data = f.read()
            
            return Response(content=wav_data, media_type="audio/wav")
        else:
            return {"error": "No frames could be decoded"}
    except Exception as e:
        return {"error": f"Decoding failed: {e}"}

# Add this to your WebSocket handler to inspect packet structure
def debug_packet(data):
    hex_str = data[:16].hex()  # First 16 bytes as hex
    print(f"Packet header hex: {hex_str}")
    print(f"Packet size: {len(data)} bytes")
    
    # Try to identify patterns
    if len(data) > 4:
        first_bytes = [b for b in data[:4]]
        print(f"First 4 bytes: {first_bytes}")

if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)