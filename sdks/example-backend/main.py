import os
import wave
import time
from datetime import datetime
from typing import Optional
import numpy as np
import uvicorn
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from opuslib import Decoder as OpusDecoder
import json
import asyncio

# Create the FastAPI app
app = FastAPI(title="Omi Audio Processor")

# Create directory for storing received audio
os.makedirs("audio_files", exist_ok=True)

# Opus decoding constants
SAMPLE_RATE = 16000
CHANNELS = 1
FRAME_SIZE = 960  # 60ms of audio at 16kHz (using exact same value as SDK)
SAVE_INTERVAL = 5  # Save WAV file every 5 seconds

def debug_packet(data):
    """Debug an incoming packet"""
    print(f"Packet size: {len(data)} bytes")
    first_bytes = []
    if len(data) > 4:
        first_bytes = [b for b in data[:4]]
        print(f"First 4 bytes: {first_bytes}")
    return {
        "size": len(data),
        "first_bytes": first_bytes if len(data) > 4 else [],
        "hex_preview": data[:8].hex() if len(data) >= 8 else data.hex()
    }

def decode_omi_packet(data: bytes, decoder: OpusDecoder) -> Optional[np.ndarray]:
    """Decode an Omi Opus packet using the same logic as the SDK"""
    if len(data) <= 3:
        return None
    
    try:
        # Use exact same parameters as SDK
        pcm = decoder.decode(data, FRAME_SIZE, decode_fec=False)
        return np.frombuffer(pcm, dtype=np.int16)  # Ensure we return an ndarray to fix type error
    except Exception as e:
        print(f"Opus decode error: {e}")
        return None

def save_wav_file(pcm_data: np.ndarray, filename: str) -> None:
    """Save PCM data to a WAV file"""
    try:
        with wave.open(filename, 'wb') as wf:
            wf.setnchannels(CHANNELS)
            wf.setsampwidth(2)  # 2 bytes per sample (16-bit)
            wf.setframerate(SAMPLE_RATE)
            wf.writeframes(pcm_data.tobytes())
        print(f"Saved audio to {filename}")
    except Exception as e:
        print(f"Error saving audio: {e}")

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
    
    # Generate a unique base filename for this session
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    base_filename = f"audio_files/client_{client_id}_{timestamp}"
    raw_filename = f"{base_filename}_opus_raw.opus"
    decoded_filename = f"{base_filename}_final.wav"
    packet_log_filename = f"{base_filename}_packet_log.json"
    
    # Initialize opus decoder (matching SDK settings)
    opus_decoder = OpusDecoder(SAMPLE_RATE, CHANNELS)
    pcm_buffer = []
    
    # Track statistics
    packets_received = 0
    packets_decoded = 0
    
    # Time tracking for periodic saves
    last_save_time = time.time()
    chunk_counter = 0
    session_start_time = time.time()
    last_log_write_time = time.time()
    
    # Packet tracking for debugging - limit to last 1000 packets to avoid memory issues
    packet_log = []
    MAX_PACKET_LOG_SIZE = 1000
    write_log_interval = 5  # seconds
    
    # Send session info back to client for correlation
    await manager.send_text(json.dumps({
        "event": "session_start",
        "session_id": f"client_{client_id}_{timestamp}",
        "start_time": session_start_time
    }), websocket)
    
    try:
        # Main WebSocket receive loop
        while True:
            # Receive binary data from WebSocket
            data = await websocket.receive_bytes()
            packet_time = time.time()
            packets_received += 1
            relative_time = packet_time - session_start_time
            
            # Save the raw packet for analysis
            opus_buffer.extend(data)
            
            # Log packet info - only keep specific information to reduce memory usage
            packet_info = {
                "packet_number": packets_received,
                "size": len(data),
                "relative_time": round(relative_time, 3),
                "hex_preview": data[:4].hex() if len(data) >= 4 else data.hex()
            }
            
            # Add to packet log with size limit
            if len(packet_log) >= MAX_PACKET_LOG_SIZE:
                # Keep the first 100 and last 900 packets if we exceed the limit
                packet_log = packet_log[:100] + packet_log[-(MAX_PACKET_LOG_SIZE-100):]
            packet_log.append(packet_info)
            
            # Decode using the Omi SDK approach
            pcm_frame = decode_omi_packet(data, opus_decoder)
            
            if pcm_frame is not None:
                # Successfully decoded
                pcm_buffer.append(pcm_frame)
                packets_decoded += 1
                packet_info["decoded"] = True
                
                # Send back receipt confirmation with packet number for correlation
                await manager.send_text(json.dumps({
                    "event": "packet_received",
                    "packet_number": packets_received,
                    "relative_time": round(relative_time, 3),
                    "size": len(data),
                    "decoded": True
                }), websocket)
                
                # Check if it's time to save a chunk (every 5 seconds)
                current_time = time.time()
                if current_time - last_save_time >= SAVE_INTERVAL and pcm_buffer:
                    # Calculate total audio duration so far
                    total_samples = sum(frame.size for frame in pcm_buffer)
                    audio_duration = total_samples / SAMPLE_RATE
                    
                    # Concatenate all PCM frames
                    try:
                        pcm_data = np.concatenate(pcm_buffer)
                        
                        # Save as WAV file with chunk number
                        chunk_wav_filename = f"{base_filename}_chunk_{chunk_counter}.wav"
                        save_wav_file(pcm_data, chunk_wav_filename)
                        
                        print(f"Saved audio chunk {chunk_counter} ({audio_duration:.2f} seconds)")
                        await manager.send_text(json.dumps({
                            "event": "chunk_saved",
                            "chunk_number": chunk_counter,
                            "duration": round(audio_duration, 2),
                            "filename": chunk_wav_filename
                        }), websocket)
                        
                        chunk_counter += 1
                        
                        # Clear the PCM buffer after saving
                        pcm_buffer = []
                        
                        last_save_time = current_time
                    except Exception as e:
                        print(f"Error saving audio chunk: {e}")
            else:
                # Failed to decode
                packet_info["decoded"] = False
                
                # Send back receipt confirmation with packet number for correlation
                await manager.send_text(json.dumps({
                    "event": "packet_received",
                    "packet_number": packets_received,
                    "relative_time": round(relative_time, 3),
                    "size": len(data),
                    "decoded": False
                }), websocket)
            
            # Print stats periodically
            if packets_received % 50 == 0:
                success_rate = (packets_decoded / packets_received) * 100
                print(f"Stats: {packets_decoded}/{packets_received} packets decoded ({success_rate:.1f}%)")
                
            # Write packet log to file periodically to avoid constant disk I/O
            current_time = time.time()
            if current_time - last_log_write_time >= write_log_interval:
                # Use async to avoid blocking the WebSocket during file I/O
                asyncio.create_task(write_packet_log(packet_log_filename, packet_log))
                last_log_write_time = current_time
    
    except WebSocketDisconnect:
        # Client disconnected
        remaining = manager.disconnect(websocket)
        print(f"Client #{client_id} disconnected. {remaining} clients remaining.")
        
        # Save the raw opus data
        with open(raw_filename, "wb") as f:
            f.write(opus_buffer)
        print(f"Saved raw opus data to {raw_filename}")
        
        # Write packet log to JSON file
        with open(packet_log_filename, "w") as f:
            json.dump(packet_log, f, indent=2, default=str)
        print(f"Saved packet log to {packet_log_filename}")
        
        # Calculate packet metrics
        packet_loss = 0
        if packets_received > 1:
            # Check for gaps in packet sequence numbers
            print(f"Total packets received: {packets_received}")
            print(f"Packet metrics saved to log file")
        
        # Print final statistics
        if packets_received > 0:
            success_rate = (packets_decoded / packets_received) * 100
            print(f"Final stats: {packets_decoded}/{packets_received} packets decoded ({success_rate:.1f}%)")
            
            # Calculate average gap between packets
            if len(packet_log) > 1:
                time_diffs = []
                for i in range(1, min(len(packet_log), 100)):  # Only sample up to 100 packets for performance
                    if "relative_time" in packet_log[i] and "relative_time" in packet_log[i-1]:
                        diff = packet_log[i]["relative_time"] - packet_log[i-1]["relative_time"]
                        time_diffs.append(diff)
                if time_diffs:
                    avg_gap = sum(time_diffs) / len(time_diffs)
                    print(f"Average time between packets: {avg_gap*1000:.2f}ms")
                    
                    # Check for outliers (packets that arrived much later than expected)
                    outliers = [diff for diff in time_diffs if diff > avg_gap * 2]
                    if outliers:
                        print(f"Found {len(outliers)} timing outliers (potential packet delays)")
                        # Only log up to 5 outliers to avoid console spam
                        for i, diff in enumerate(outliers[:5]):
                            print(f"  Gap: {diff*1000:.2f}ms")
                        if len(outliers) > 5:
                            print(f"  ... and {len(outliers)-5} more outliers")
        
            # Save decoded PCM audio if we have any
            if pcm_buffer:
                try:
                    # Concatenate all PCM frames
                    pcm_data = np.concatenate(pcm_buffer)
                    
                    # Save as WAV file
                    save_wav_file(pcm_data, decoded_filename)
                    
                    print(f"Saved final decoded audio to {decoded_filename}")
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

# Helper function for async writing of packet logs to avoid blocking the WebSocket
async def write_packet_log(filename, packet_log):
    try:
        with open(filename, "w") as f:
            json.dump(packet_log, f, default=str)
    except Exception as e:
        print(f"Error writing packet log: {e}")

if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)