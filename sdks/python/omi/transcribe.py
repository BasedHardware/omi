import websockets
import json
import asyncio
import time
import os

async def transcribe(audio_queue, api_key):
    url = "wss://api.deepgram.com/v1/listen?punctuate=true&model=nova&language=en-US&encoding=linear16&sample_rate=16000&channels=1"
    headers = {
        "Authorization": f"Token {api_key}"
    }

    # For debugging
    total_audio_bytes = 0
    start_time = time.time()
    packet_count = 0
    response_count = 0
    last_ping_time = 0

    # Test Deepgram API key first
    print(f"Testing Deepgram API key validity...")
    import http.client
    conn = http.client.HTTPSConnection("api.deepgram.com")
    conn.request("GET", "/v1/projects", headers={"Authorization": f"Token {api_key}"})
    response = conn.getresponse()
    if response.status != 200:
        print(f"❌ Deepgram API key validation failed! Status: {response.status}")
        print(f"Response: {response.read().decode()}")
        print("Please check your API key and try again.")
        return
    else:
        print(f"✅ Deepgram API key is valid!")

    while True:
        try:
            async with websockets.connect(url, extra_headers=headers, ping_interval=20) as ws:
                print("\n🎤 Connected to Deepgram WebSocket - Ready for transcription")
                
                # Send an initial empty chunk to test connection
                await ws.send(b'\x00\x00')
                print("✓ Initial test packet sent to Deepgram")

                async def send_audio():
                    nonlocal total_audio_bytes, packet_count, last_ping_time
                    buffer = bytearray()  # Buffer to accumulate audio
                    
                    while True:
                        try:
                            chunk = await audio_queue.get()
                            
                            # Skip empty chunks
                            if len(chunk) == 0:
                                continue
                                
                            # Send ping periodically to verify connection 
                            current_time = time.time()
                            if current_time - last_ping_time > 15:
                                print("⏱️ Ping: Checking Deepgram connection...")
                                try:
                                    pong = await ws.ping()
                                    await asyncio.wait_for(pong, timeout=5)
                                    print("⏱️ Pong: Deepgram connection active")
                                except Exception as e:
                                    print(f"⚠️ WebSocket ping failed: {e}")
                                last_ping_time = current_time
                            
                            # Accumulate audio in buffer (collect ~1 second chunks)
                            buffer.extend(chunk)
                            
                            # Only send when we have enough data (at least 16000 bytes = 0.5 sec at 16kHz/16-bit)
                            # This helps with recognition quality as Deepgram works better with larger chunks
                            if len(buffer) >= 16000:
                                # Track statistics
                                packet_count += 1
                                total_audio_bytes += len(buffer)
                                elapsed = time.time() - start_time
                                
                                # Only log every 5 seconds to reduce noise
                                if elapsed - last_ping_time > 5:
                                    print(f"Audio stats: {packet_count} chunks | {total_audio_bytes/1024:.1f} KB | {total_audio_bytes/elapsed/1024:.1f} KB/sec")
                                    last_ping_time = elapsed
                                
                                # Send the audio buffer to Deepgram and clear it
                                await ws.send(bytes(buffer))
                                buffer = bytearray()
                            
                        except Exception as e:
                            print(f"Error sending audio: {e}")
                            break

                async def receive_transcripts():
                    nonlocal response_count
                    try:
                        async for msg in ws:
                            response_count += 1
                            # Always log the first 5 responses, then every 10th
                            should_log = response_count <= 5 or response_count % 10 == 0
                            
                            try:
                                response = json.loads(msg)
                                if "error" in response:
                                    print(f"❌ Deepgram Error: {response['error']}")
                                    continue
                                
                                # Always log every response to show what we're getting
                                print(f"\n🔍 Deepgram response #{response_count}: {json.dumps(response)[:200]}...")
                                
                                # Extract transcript from the response
                                if "channel" in response and "alternatives" in response["channel"]:
                                    transcript = response["channel"]["alternatives"][0].get("transcript", "")
                                    if transcript and transcript.strip():
                                        # Print transcript with prominent formatting
                                        print("\n" + "=" * 60)
                                        print(f"🗣️  TRANSCRIPT: {transcript.strip()}")
                                        print("=" * 60 + "\n")
                                    elif should_log:
                                        print("🔄 No speech detected in this segment")
                            except json.JSONDecodeError as e:
                                print(f"Error decoding response: {e}")
                                print(f"Raw message: {msg[:100]}...")
                            except Exception as e:
                                print(f"Error processing transcript: {e}")
                    except websockets.exceptions.ConnectionClosed as e:
                        print(f"Connection to Deepgram closed: {e}")
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
