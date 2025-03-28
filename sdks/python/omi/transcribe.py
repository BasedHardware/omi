import websockets
import json
import asyncio

async def transcribe(audio_queue, api_key):
    url = "wss://api.beta.deepgram.com/v1/listen?model=nova-3&language=multi&smart_format=true&punctuate=true&encoding=linear16&sample_rate=16000&channels=1"
    headers = {
        "Authorization": f"Token {api_key}"
    }

    while True:
        try:
            async with websockets.connect(url, extra_headers=headers) as ws:
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
