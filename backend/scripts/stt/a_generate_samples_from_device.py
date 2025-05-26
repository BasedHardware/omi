# import asyncio
# import os
# import wave
# from datetime import datetime
#
# import numpy as np
# from bleak import BleakClient, discover
#
# DEVICE_NAME = "Friend"
# SERVICE_UUID = "19B10000-E8F2-537E-4F6C-D104768A1214"
# CHARACTERISTIC_UUID = "19B10001-E8F2-537E-4F6C-D104768A1214"
#
# CODEC = "pcm"  # "pcm" or "mulaw"
# SAMPLE_RATE = 8000  # Sample rate for the audio
# SAMPLE_WIDTH = 2  # 16-bit audio
# CHANNELS = 1  # Mono audio
#
#
# def ulaw2linear(ulaw_byte):
#     """Convert a µ-law byte to a 16-bit linear PCM value."""
#     EXPONENT_LUT = [0, 132, 396, 924, 1980, 4092, 8316, 16764]
#     ulaw_byte = ~ulaw_byte
#     sign = (ulaw_byte & 0x80)
#     exponent = (ulaw_byte >> 4) & 0x07
#     mantissa = ulaw_byte & 0x0F
#     sample = EXPONENT_LUT[exponent] + (mantissa << (exponent + 3))
#     if sign != 0:
#         sample = -sample
#
#     return sample
#
#
# def ulaw_bytes_to_pcm16(ulaw_data):
#     """Convert a sequence of µ-law encoded bytes to a list of 16-bit PCM values."""
#     return [ulaw2linear(byte) for byte in ulaw_data]
#
#
# def filter_audio_data(audio_data):
#     if CODEC == "mulaw":
#         pcm16_samples = ulaw_bytes_to_pcm16(audio_data)
#         audio_data = np.array(pcm16_samples, dtype=np.int16)
#
#     if CODEC == "pcm":
#         audio_data = audio_data[:len(audio_data) - len(audio_data) % 2]
#         audio_data = np.frombuffer(audio_data, dtype=np.int16)
#
#     return audio_data
#
#
# def export_audio_data(filtered_audio_data, raw_file, file_extension):
#     if not os.path.exists(recordings_dir):
#         os.makedirs(recordings_dir)
#     filename = os.path.join(recordings_dir, datetime.now().strftime("%H-%M-%S-%f") + file_extension)
#     print(filename)
#     if file_extension == ".txt":
#         with open(filename, "w") as file:
#             file.write(str(list(raw_file)))
#     else:
#         with wave.open(filename, "wb") as wav_file:
#             wav_file.setnchannels(CHANNELS)
#             wav_file.setsampwidth(SAMPLE_WIDTH)
#             wav_file.setframerate(SAMPLE_RATE)
#             wav_file.writeframes(filtered_audio_data.tobytes())
#
#
# async def process_audio(audio_data):
#     if len(audio_data) == 0:
#         print("Warning: Received empty audio data array.")
#         return
#
#     filtered_audio_data = filter_audio_data(audio_data)
#     export_audio_data(filtered_audio_data, audio_data, ".wav")
#     # export_audio_data(filtered_audio_data, audio_data, ".txt")
#
#
# async def main():
#     print("Discovering AudioRecorder...")
#     devices = await discover(timeout=2.0)
#     audio_recorder = None
#     for device in devices:
#         if device.name:
#             print(device.name, device.address)
#         if device.name == DEVICE_NAME:
#             audio_recorder = device
#             break
#
#     if not audio_recorder:
#         print("AudioRecorder not found")
#         return
#
#     def handle_ble_disconnect(client):
#         print("Disconnected from AudioRecorder")
#
#     async with BleakClient(audio_recorder.address, services=[SERVICE_UUID],
#                            disconnect_callback=handle_ble_disconnect) as client:
#         print("Connected to AudioRecorder")
#         services = await client.get_services()
#         audio_service = services.get_service(SERVICE_UUID)
#         audio_characteristic = audio_service.get_characteristic(CHARACTERISTIC_UUID)
#
#         audio_data = bytearray()
#         is_recording = False
#
#         def handle_audio_data(sender, data):
#             audio_data.extend(data[3:])
#
#         async def start_recording():
#             nonlocal is_recording
#             is_recording = True
#             audio_data.clear()
#             await client.start_notify(audio_characteristic.uuid, handle_audio_data)
#             print("Recording audio...")
#
#         async def stop_recording():
#             nonlocal is_recording
#             is_recording = False
#             await client.stop_notify(audio_characteristic.uuid)
#             print("Recording stopped")
#             asyncio.ensure_future(process_audio(audio_data.copy()))
#             audio_data.clear()
#
#         async def monitor_keyboard():
#             while True:
#                 if input('Record') == '':
#                     if not is_recording:
#                         await start_recording()
#                     else:
#                         await stop_recording()
#                 await asyncio.sleep(0.1)
#
#         print("Press Tab to start/stop recording.")
#         await monitor_keyboard()
#
#
# recordings_dir = 'data/'
# asyncio.run(main())  # sudo
#
# # Phonetic Diversity Phrases
# # "The quick brown fox jumps over the lazy dog."
# # "She sells seashells by the seashore every sunny day."
# # "How much wood would a woodchuck chuck if a woodchuck could chuck wood?"
# # "Peter Piper picked a peck of pickled peppers."
# # "A big black bear sat on a big black rug."
# # "I scream, you scream, we all scream for ice cream."
# # "Pack my box with five dozen liquor jugs."
# # "The five boxing wizards jump quickly and quietly."
# # "Bright blue birds fly above the green grassy hills."
# # "Fred’s friends fried Fritos for Friday's food festival."
#
# # Natural Conversation Phrases
# # "Hey, can you pass me that book?"
# # "It's really nice to meet you today."
# # "What time is our meeting scheduled for?"
# # "Could you please repeat that last pa`1   rt?"
# # "I'm heading to the grocery store, do you need anything?"
# # "Let's discuss the project details later."
# # "How was your weekend? Did you do anything fun?"
# # "I think the weather is going to be great tomorrow."
# # "Are you free for a quick call this afternoon?"
# # "I heard there's a new cafe opening downtown."
#
#
# ### ----
#
# # "The curious cat chased the mouse through the house."
# # "Yesterday, I saw a beautiful rainbow after the rain."
# # "My favorite hobby is reading mystery novels on weekends."
# # "Can you believe how fast this year has gone by?"
# # "The large elephant walked slowly through the tall grass."
# # "Please make sure to lock the door when you leave."
# # "I need to buy some groceries, like milk, eggs, and bread."
# # "He quickly ran to catch the bus before it left."
# # "Technology is evolving rapidly, changing our daily lives."
# # "She whispered a secret to her best friend in class."
