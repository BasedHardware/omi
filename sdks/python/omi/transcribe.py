import asyncio
import json
import logging  # Add logging import
import time  # Import time for windowing
from asyncio import Queue
from contextlib import suppress

import websockets
from websockets.exceptions import (  # Correct import
    ConnectionClosedError,
    ConnectionClosedOK,
    WebSocketException,
)
from wyoming.asr import Transcribe  # Added import
from wyoming.audio import (  # Import Wyoming audio events
    AudioChunk,
    AudioStart,
    AudioStop,
)
from wyoming.client import AsyncClient  # Import Wyoming client
from wyoming.event import Event

logger = logging.getLogger(__name__)

# Constants (assuming standard values, adjust if needed)
SAMPLE_RATE = 16000
SAMPLE_WIDTH = 2  # Bytes per sample (16-bit)
CHANNELS = 1
WINDOW_SECONDS = 10 # Send stop/start every 10 seconds
READ_TIMEOUT_SECONDS = 15.0 # Timeout for waiting for transcript after AudioStop # Edited value

async def transcribe(audio_queue: Queue, api_key: str):
    url = "wss://api.deepgram.com/v1/listen?punctuate=true&model=nova&language=en-US&encoding=linear16&sample_rate=16000&channels=1"
    headers = {
        "Authorization": f"Token {api_key}"
    }

    while True:
        try:
            async with websockets.connect(url, extra_headers=headers) as ws: # type: ignore
                print("Connected to Deepgram WebSocket")

                async def send_audio():
                    while True:
                        try:
                            chunk = await audio_queue.get()
                            await ws.send(chunk)
                        except Exception as e:
                            print(f"Error sending audio: {e}")
                            break

                async def receive_transcripts():
                    try:
                        async for msg in ws:
                            try:
                                response = json.loads(msg)
                                if "error" in response:
                                    print(f"Deepgram Error: {response['error']}")
                                    continue
                                    
                                # Extract transcript from the response
                                if "channel" in response and "alternatives" in response["channel"]:
                                    transcript = response["channel"]["alternatives"][0].get("transcript", "")
                                    if transcript and transcript.strip():
                                        print("\nTranscript:", transcript.strip())
                            except json.JSONDecodeError as e:
                                print(f"Error decoding response: {e}")
                            except Exception as e:
                                print(f"Error processing transcript: {e}")
                    except websockets.exceptions.ConnectionClosed: # type: ignore
                        print("Connection to Deepgram closed")
                    except Exception as e:
                        print(f"Error in receive_transcripts: {e}")

                try:
                    await asyncio.gather(send_audio(), receive_transcripts())
                except Exception as e:
                    print(f"Error in transcribe: {e}")
                    
        except Exception as e:
            print(f"Connection error: {e}")
            print("Retrying connection in 5 seconds...")
            await asyncio.sleep(5)

async def transcribe_wyoming(audio_queue: Queue, wyoming_url: str):
    """
    Connects to a Wyoming server, sends audio from a queue, handles transcripts per segment.
    Connects and disconnects for each audio segment (window).
    """
    while True: # Loop for handling audio segments (and potential queue termination)
        client = None
        segment_has_audio = False
        chunk = None # Initialize chunk to handle potential early exit

        try:
            # 1. Connect for this segment
            logger.info(f"Attempting to connect to Wyoming server at {wyoming_url} for new segment...")
            client = AsyncClient.from_uri(wyoming_url)
            await client.connect()
            logger.info(f"Connected to Wyoming server at {wyoming_url}")

            # 2. Tell the server what we intend to do
            logger.debug("Wyoming: Sending Transcribe intent...")
            await client.write_event(
                Transcribe(name="large-v3", language="en").event()   # or name="large-v3"
            )
            logger.debug("Wyoming: Transcribe intent sent.")

            # 3. Start Audio Segment
            logger.debug("Wyoming: Sending AudioStart for new segment...")
            await client.write_event(AudioStart(rate=SAMPLE_RATE, width=SAMPLE_WIDTH, channels=CHANNELS).event())
            logger.debug("Wyoming: AudioStart sent.")
            last_start_time = time.monotonic()

            # 4. Send Audio Chunks for WINDOW_SECONDS
            logger.debug(f"Wyoming: Sending audio chunks for {WINDOW_SECONDS} seconds...")
            while True:
                current_time = time.monotonic()
                time_elapsed = current_time - last_start_time

                # Check if window duration passed
                if time_elapsed >= WINDOW_SECONDS:
                    logger.debug(f"Window time ({WINDOW_SECONDS}s) elapsed.")
                    break

                try:
                    # Calculate remaining time in window for timeout
                    timeout = max(0.1, WINDOW_SECONDS - time_elapsed) # Use small minimum timeout
                    # Get chunk with timeout to prevent blocking indefinitely if queue is empty
                    chunk = await asyncio.wait_for(audio_queue.get(), timeout=timeout)

                    if chunk is None: # Handle queue termination signal
                        logger.info("Audio queue finished during chunk sending. Exiting.")
                        # No need to send AudioStop if queue ended before window completion
                        return # Exit the entire function if queue is done

                    # Send audio chunk
                    logger.debug(f"Wyoming: Sending AudioChunk ({len(chunk)} bytes)...")
                    await client.write_event(AudioChunk(audio=chunk, rate=SAMPLE_RATE, width=SAMPLE_WIDTH, channels=CHANNELS).event())
                    segment_has_audio = True # Mark that we sent audio in this segment
                    logger.debug("Wyoming: AudioChunk sent.")

                except asyncio.TimeoutError:
                    # Expected if no audio comes within the window's remaining time
                    logger.debug("Timeout waiting for audio chunk, window likely finished.")
                    break # Exit chunk sending loop
                except asyncio.CancelledError:
                    logger.info("Chunk sending task cancelled.")
                    raise # Re-raise cancellation
                except Exception as e:
                    logger.error(f"Error getting/sending audio chunk: {e}", exc_info=True)
                    raise # Re-raise other exceptions to break segment processing

            # 5. Stop Audio Segment (only if audio was sent in this window)
            if segment_has_audio:
                logger.debug(f"Wyoming: Sending AudioStop...")
                await client.write_event(AudioStop().event())
                logger.debug("Wyoming: AudioStop sent.")

                # 6. Read Transcript for the Segment
                logger.debug(f"Wyoming: Reading events for transcript (timeout={READ_TIMEOUT_SECONDS}s)...")
                try:
                    while True: # Loop to read events until transcript or timeout/error
                        event = await asyncio.wait_for(client.read_event(), timeout=READ_TIMEOUT_SECONDS)

                        if event is None:
                            logger.warning("Wyoming connection closed by server unexpectedly while waiting for transcript.")
                            # Server might close connection after sending transcript/error, treat as end of segment read
                            break

                        logger.debug(f"Wyoming: Received event raw: {event}") # DEBUG
                        logger.debug(f"Wyoming: Received event type: {type(event)}") # DEBUG
                        if hasattr(event, 'data'):
                           logger.debug(f"Wyoming: Received event data: {event.data}") # DEBUG

                        # Check for transcription event
                        if isinstance(event, Event) and event.type == 'transcript' and 'text' in event.data:
                            transcript = event.data['text']
                            if transcript and transcript.strip():
                                logger.info(f"Transcript: {transcript.strip()}")
                            # Assume one transcript per segment, break after receiving it
                            logger.debug("Breaking read loop after receiving transcript.")
                            break
                        elif isinstance(event, Event) and event.type == 'error':
                            logger.error(f"Wyoming server error event: {event.data}")
                            # Break on error, segment finished (with error)
                            break
                        else:
                            logger.debug(f"Received non-transcript/non-error event: type={type(event)}")
                            # Continue reading other events until transcript/error or timeout

                except asyncio.TimeoutError:
                    logger.warning(f"Timeout waiting for transcript after {READ_TIMEOUT_SECONDS}s.")
                    # Continue to the next segment even if no transcript was received
                except (ConnectionClosedOK, ConnectionClosedError, ConnectionResetError) as close_err:
                     logger.info(f"Wyoming connection closed gracefully/expectedly after sending audio: {close_err}")
                     # This is expected if the server closes after sending the transcript/error
                except asyncio.CancelledError:
                     logger.info("Transcript reading task cancelled.")
                     raise # Re-raise cancellation
                except Exception as e:
                    logger.error(f"Error reading transcript event: {e}", exc_info=True)
                    # Depending on the error, might want to raise or just log and continue
                    # For now, log and continue to the finally block/next segment
            else:
                logger.info("Skipping AudioStop and transcript read as no audio was sent in this window.")

        except (ConnectionRefusedError, ConnectionResetError, ConnectionError, WebSocketException) as conn_err:
            logger.error(f"Wyoming connection/websocket error during segment: {conn_err}")
            # Connection error for a segment, wait before retrying the *next* segment
            await asyncio.sleep(5)
        except asyncio.CancelledError:
             logger.info("Main transcription task cancelled during segment processing.")
             break # Exit outer loop if cancelled
        except Exception as e:
            logger.error(f"Unexpected error during segment processing: {e}", exc_info=True)
            # Log unexpected error and wait before next segment attempt
            await asyncio.sleep(5)
        finally:
            if client: # Check if client was successfully created
                logger.info("Attempting to disconnect from Wyoming server for this segment...")
                with suppress(Exception): # Suppress errors during cleanup disconnect
                    await client.disconnect()
                    logger.info("Disconnected from Wyoming server for this segment.")
            client = None # Ensure client is reset for the next loop iteration

        # Check if the task was cancelled before potentially sleeping/looping
        task = asyncio.current_task()
        if task and task.cancelled():
            logger.info("Task cancelled, exiting transcribe_wyoming loop.")
            break

    logger.info("Exiting transcribe_wyoming function.")

# Ensure logging is configured if this module is run directly or imported early
# logging.basicConfig(level=logging.DEBUG) 
