import asyncio
import json
import logging
import os
import time
import traceback
import wave
from contextlib import suppress
from datetime import datetime
from typing import Optional

import numpy as np
import uvicorn
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from opuslib import Decoder as OpusDecoder
from websockets.exceptions import (
    ConnectionClosedError,
    ConnectionClosedOK,
    WebSocketException,
)
from wyoming.asr import Transcribe
from wyoming.audio import AudioChunk, AudioStart, AudioStop
from wyoming.client import AsyncClient
from wyoming.event import Event

logging.basicConfig(level=logging.DEBUG)

logger = logging.getLogger(__name__)

# Create the FastAPI app
app = FastAPI(title="Omi Audio Processor")

# Create directory for storing received audio
os.makedirs("audio_files", exist_ok=True)

# Opus decoding constants
SAMPLE_RATE = 16000
CHANNELS = 1
FRAME_SIZE = 960  # 60ms of audio at 16kHz (using exact same value as SDK)
SAVE_INTERVAL = 5  # Save WAV file every 5 seconds

# Wyoming client configuration
WYOMING_HOST = os.environ.get("WYOMING_HOST", "whisper")
# WYOMING_HOST = os.environ.get("WYOMING_HOST", "localhost")
WYOMING_PORT = int(os.environ.get("WYOMING_PORT", "10300"))

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
    logger.info(f"Client #{client_id} connected")
    
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
    pcm_to_process = []
    
    # Track statistics
    packets_received = 0
    packets_decoded = 0
    connection_start_time = time.time()
    
    # Time tracking for periodic saves
    last_save_time = time.time()
    last_stt_time = time.time()  # Track when we last performed STT
    stt_interval = 5.0  # Process speech recognition every 5 seconds
    stt_read_timeout = 10.0 # Timeout for reading transcript after AudioStop
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
        # Create a queue for websocket messages
        message_queue = asyncio.Queue()

        # Background task to receive websocket messages without blocking
        async def websocket_receiver():
            try:
                while True:
                    try:
                        data = await websocket.receive_bytes()
                        await message_queue.put(data)
                    except WebSocketDisconnect:
                        logger.info("WebSocket disconnected in receiver.")
                        await message_queue.put(None) # Signal disconnect
                        break
                    except Exception as e:
                        logger.error(f"Error in websocket receiver: {e}")
                        await message_queue.put(None) # Signal error
                        break
            except asyncio.CancelledError:
                logger.info("Websocket receiver task cancelled")

        # Start the websocket receiver task
        receiver_task = asyncio.create_task(websocket_receiver())

        # Set up a ping task to keep the connection alive
        async def ping_client():
            try:
                while True:
                    await asyncio.sleep(15)  # Send ping every 15 seconds
                    await websocket.send_text(json.dumps({"event": "ping", "timestamp": time.time()}))
                    logger.debug("Ping sent to client")
            except asyncio.CancelledError:
                logger.info("Ping task cancelled")
            except Exception as e:
                # Catch specific exception if possible, e.g., ConnectionClosed
                logger.error(f"Error in ping task (client likely disconnected): {e}")

        ping_task = asyncio.create_task(ping_client())

        # Main WebSocket receive loop
        while True:
            # Receive binary data from WebSocket via the queue
            try:
                connection_duration = time.time() - connection_start_time
                # Get data from the queue with a timeout
                data = await asyncio.wait_for(message_queue.get(), timeout=30.0)
                if data is None:
                    # Error signaled from receiver task
                    raise WebSocketDisconnect(code=1008)
                
                packet_time = time.time()
                packets_received += 1
                print(f"packet received {packets_received}")
                relative_time = packet_time - session_start_time
                
                # Log detailed connection statistics every 100 packets
                if packets_received % 100 == 0:
                    logger.info(f"Connection stats: Duration: {connection_duration:.1f}s, Packets: {packets_received}, Rate: {packets_received/connection_duration:.1f} pkts/sec")
                
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
                    logger.info(f"Decoded packet {packets_received}")

                    # Successfully decoded
                    pcm_buffer.append(pcm_frame)
                    pcm_to_process.append(pcm_frame)
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
                            
                            logger.info(f"Saved audio chunk {chunk_counter} ({audio_duration:.2f} seconds)")
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
                            logger.error(f"Error saving audio chunk: {e}")
                            
                    # Check if it's time to process speech-to-text
                    if current_time - last_stt_time >= stt_interval and pcm_to_process:
                            logger.info(f"STT interval reached. Processing {len(pcm_to_process)} frames.")

                            # --- Start of Per-Segment STT Logic ---
                            stt_client = None
                            try:
                                # 1. Connect for this segment
                                logger.info(f"Connecting to Wyoming for STT ({WYOMING_HOST}:{WYOMING_PORT})...")
                                stt_client = AsyncClient.from_uri(f"tcp://{WYOMING_HOST}:{WYOMING_PORT}")
                                await stt_client.connect()
                                logger.info("Connected to Wyoming for STT.")

                                # 2. Send Transcribe Intent
                                logger.debug("Wyoming: Sending Transcribe intent...")
                                await stt_client.write_event(Transcribe(name="default", language="en").event()) # Use appropriate model name if needed
                                logger.debug("Wyoming: Transcribe intent sent.")

                                # 3. Send AudioStart
                                logger.debug("Wyoming: Sending AudioStart...")
                                await stt_client.write_event(AudioStart(rate=SAMPLE_RATE, width=2, channels=CHANNELS).event())
                                logger.debug("Wyoming: AudioStart sent.")

                                # 4. Send Audio Chunks
                                logger.debug(f"Wyoming: Sending {len(pcm_to_process)} audio frames...")
                                for frame in pcm_to_process:
                                    chunk = AudioChunk(audio=frame.tobytes(), rate=SAMPLE_RATE, width=2, channels=CHANNELS)
                                    await stt_client.write_event(chunk.event())
                                logger.debug("Wyoming: All audio frames sent.")

                                # 5. Send AudioStop
                                logger.debug("Wyoming: Sending AudioStop...")
                                await stt_client.write_event(AudioStop().event())
                                logger.debug("Wyoming: AudioStop sent.")

                                # 6. Read Transcript
                                logger.debug(f"Wyoming: Reading transcript (timeout={stt_read_timeout}s)...")
                                transcript = ""
                                try:
                                    while True:
                                        event = await asyncio.wait_for(stt_client.read_event(), timeout=stt_read_timeout)
                                        if event is None:
                                            logger.warning("Wyoming connection closed while waiting for transcript.")
                                            break

                                        logger.debug(f"Wyoming: Received event type: {type(event)}")
                                        if isinstance(event, Event) and event.type == 'transcript' and 'text' in event.data:
                                            transcript = event.data['text']
                                            if transcript and transcript.strip():
                                                logger.info(f"Transcription: {transcript.strip()}")
                                                # Send transcription back to client
                                                await manager.send_text(json.dumps({
                                                    "event": "transcription",
                                                    "text": transcript.strip(),
                                                    "timestamp": time.time() - session_start_time,
                                                    "segment_processed": True # Indicate it's from segment processing
                                                }), websocket)
                                            # Assume one transcript per segment
                                            break
                                        elif isinstance(event, Event) and event.type == 'error':
                                            logger.error(f"Wyoming server error event: {event.data}")
                                            break # Stop reading on error
                                        else:
                                            logger.debug("Received non-transcript/non-error event.")

                                except asyncio.TimeoutError:
                                    logger.warning(f"Timeout waiting for transcript after {stt_read_timeout}s.")
                                except (ConnectionClosedOK, ConnectionClosedError, ConnectionResetError) as close_err:
                                    logger.info(f"Wyoming connection closed as expected: {close_err}")
                                except Exception as read_err:
                                    logger.error(f"Error reading transcript event: {read_err}", exc_info=True)

                            except (ConnectionRefusedError, ConnectionResetError, ConnectionError, WebSocketException) as conn_err:
                                logger.error(f"Wyoming connection error during STT segment: {conn_err}")
                            except Exception as stt_err:
                                logger.error(f"Unexpected error during STT segment processing: {stt_err}", exc_info=True)
                            finally:
                                if stt_client:
                                    logger.info("Disconnecting STT client...")
                                    with suppress(Exception):
                                        await stt_client.disconnect()
                                    logger.info("STT client disconnected.")
                            # --- End of Per-Segment STT Logic ---

                            # Clear the processing buffer after sending for transcription
                            pcm_to_process = []
                            last_stt_time = current_time
                
                else:
                    logger.error(f"Failed to decode packet {packets_received}")
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
                    logger.info(f"Stats: {packets_decoded}/{packets_received} packets decoded ({success_rate:.1f}%)")
                    
                # Write packet log to file periodically to avoid constant disk I/O
                current_time = time.time()
                if current_time - last_log_write_time >= write_log_interval:
                    # Use async to avoid blocking the WebSocket during file I/O
                    asyncio.create_task(write_packet_log(packet_log_filename, packet_log))
                    last_log_write_time = current_time
            
            except (asyncio.CancelledError, ConnectionResetError) as e:
                logger.error(f"Connection error during audio streaming: {e}")
                # Immediately reconnect and restart streaming
                asr_client = AsyncClient.from_uri(f"tcp://{WYOMING_HOST}:{WYOMING_PORT}")
                await asr_client.connect()
                await asr_client.write_event(AudioStart(rate=SAMPLE_RATE, width=2, channels=CHANNELS).event())
                logger.info("Reconnected after connection closed")

            except asyncio.TimeoutError:
                logger.warning("WebSocket receive timeout. Connection may be stalled.")
                # Optionally add logic to reconnect or send ping to test connection
                try:
                    # Send a ping to check if connection is still alive
                    await websocket.send_text(json.dumps({"event": "ping", "timestamp": time.time()}))
                    logger.info("Ping sent to client to verify connection")
                except Exception as ping_error:
                    logger.error(f"Error sending ping: {ping_error}")
                    # Use 1008 code (Policy Violation) as a reasonable code for connection timeout
                    # Signal disconnect by putting None in queue, let main loop handle it
                    await message_queue.put(None)
                    break # Exit the receive loop
    
    except WebSocketDisconnect:
        # Client disconnected
        remaining = manager.disconnect(websocket)
        logger.info(f"Client #{client_id} disconnected. {remaining} clients remaining.")
        
        # Cancel all background tasks
        for task in [receiver_task, ping_task]:
            if task and not task.done():
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass
        
        # Save the raw opus data
        with open(raw_filename, "wb") as f:
            f.write(opus_buffer)
        logger.info(f"Saved raw opus data to {raw_filename}")
        
        # Write packet log to JSON file
        with open(packet_log_filename, "w") as f:
            json.dump(packet_log, f, indent=2, default=str)
        logger.info(f"Saved packet log to {packet_log_filename}")
        
        # Calculate packet metrics
        if packets_received > 1:
            # Check for gaps in packet sequence numbers
            logger.info(f"Total packets received: {packets_received}")
            logger.info(f"Packet metrics saved to log file")
        
        # Print final statistics
        if packets_received > 0:
            success_rate = (packets_decoded / packets_received) * 100
            logger.info(f"Final stats: {packets_decoded}/{packets_received} packets decoded ({success_rate:.1f}%)")
            
            # Calculate average gap between packets
            if len(packet_log) > 1:
                time_diffs = []
                for i in range(1, min(len(packet_log), 100)):  # Only sample up to 100 packets for performance
                    if "relative_time" in packet_log[i] and "relative_time" in packet_log[i-1]:
                        diff = packet_log[i]["relative_time"] - packet_log[i-1]["relative_time"]
                        time_diffs.append(diff)
                if time_diffs:
                    avg_gap = sum(time_diffs) / len(time_diffs)
                    logger.info(f"Average time between packets: {avg_gap*1000:.2f}ms")
                    
                    # Check for outliers (packets that arrived much later than expected)
                    outliers = [diff for diff in time_diffs if diff > avg_gap * 2]
                    if outliers:
                        logger.info(f"Found {len(outliers)} timing outliers (potential packet delays)")
                        # Only log up to 5 outliers to avoid console spam
                        for i, diff in enumerate(outliers[:5]):
                            logger.info(f"  Gap: {diff*1000:.2f}ms")
                        if len(outliers) > 5:
                            logger.info(f"  ... and {len(outliers)-5} more outliers")
        
            # Save decoded PCM audio if we have any
            if pcm_buffer:
                try:
                    # Concatenate all PCM frames
                    pcm_data = np.concatenate(pcm_buffer)
                    
                    # Save as WAV file
                    save_wav_file(pcm_data, decoded_filename)
                    
                    logger.info(f"Saved final decoded audio to {decoded_filename}")
                    logger.info(f"Audio stats: {CHANNELS} channels, {SAMPLE_RATE} Hz, {len(pcm_data)/SAMPLE_RATE:.2f} seconds")
                except Exception as e:
                    logger.error(f"Error saving decoded audio: {e}")
            else:
                logger.info("No PCM data was successfully decoded")
                
                # Create a placeholder WAV with silence
                silence = np.zeros(16000, dtype=np.int16)  # 1 second of silence at 16kHz
                with wave.open(decoded_filename, 'wb') as wf:
                    wf.setnchannels(CHANNELS)
                    wf.setsampwidth(2)  # 2 bytes per sample (16-bit)
                    wf.setframerate(SAMPLE_RATE)
                    wf.writeframes(silence.tobytes())
                logger.info(f"Created placeholder WAV file at {decoded_filename}")

    except ConnectionRefusedError as e:
        raise e

    except Exception as e:
        traceback.print_exc()
        logger.error(f"Error: {e}")
        # Optionally re-raise or handle differently
    finally:
        # Disconnection now happens per-segment in the finally block above
        # Ensure background tasks are properly awaited if cancelled earlier
        for task in [receiver_task, ping_task]:
            if task and not task.done() and task.cancelled():
                try:
                    await task
                except asyncio.CancelledError:
                    pass
        logger.info(f"Cleaned up tasks for client #{client_id}")

# Helper function for async writing of packet logs to avoid blocking the WebSocket
async def write_packet_log(filename, packet_log):
    try:
        with open(filename, "w") as f:
            json.dump(packet_log, f, default=str)
    except Exception as e:
        logger.error(f"Error writing packet log: {e}")

if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)