import websockets
import json
import asyncio
from typing import Any, Dict, Callable, Optional
from asyncio import Queue

async def transcribe(
    audio_queue: Queue[bytes], 
    api_key: str,
    on_transcript: Optional[Callable[[str], None]] = None
) -> None:
    """
    Real-time audio transcription using Deepgram WebSocket API.
    
    Args:
        audio_queue: Queue containing PCM audio chunks
        api_key: Deepgram API key
        on_transcript: Optional callback function to handle transcript results.
                      If None, prints to console (for backward compatibility).
    """
    url = "wss://api.deepgram.com/v1/listen?punctuate=true&model=nova&language=en-US&encoding=linear16&sample_rate=16000&channels=1"

    while True:
        try:
            async with websockets.connect(
                url, 
                additional_headers={"Authorization": f"Token {api_key}"}
            ) as ws:
                print("Connected to Deepgram WebSocket")

                async def send_audio() -> None:
                    """Send audio chunks from queue to WebSocket."""
                    while True:
                        try:
                            chunk: bytes = await audio_queue.get()
                            await ws.send(chunk)
                        except Exception as e:
                            print(f"Error sending audio: {e}")
                            break

                async def receive_transcripts() -> None:
                    """Receive and process transcription results from WebSocket."""
                    try:
                        async for msg in ws:
                            try:
                                response: Dict[str, Any] = json.loads(msg)
                                if "error" in response:
                                    print(f"Deepgram Error: {response['error']}")
                                    continue
                                    
                                # Extract transcript from the response
                                if "channel" in response and "alternatives" in response["channel"]:
                                    transcript = response["channel"]["alternatives"][0].get("transcript", "")
                                    if transcript and transcript.strip():
                                        # Call user callback or fallback to print
                                        if on_transcript:
                                            on_transcript(transcript.strip())
                                        else:
                                            print("\nTranscript:", transcript.strip())
                            except json.JSONDecodeError as e:
                                print(f"Error decoding response: {e}")
                            except Exception as e:
                                print(f"Error processing transcript: {e}")
                    except websockets.exceptions.ConnectionClosed:
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
