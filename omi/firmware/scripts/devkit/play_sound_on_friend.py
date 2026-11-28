import argparse
import os
from dotenv import load_dotenv
import wave
from deepgram import( DeepgramClient,SpeakOptions,)

import asyncio
import bleak
import numpy as np
from bleak import BleakClient

load_dotenv()

filename = "output2.wav"

PACKET_SIZE = 400
# <= 7 blocks * 5000 mono bytes/block = 2.1875 s @ 8 kHz mono int16. The
# queue-before-START firmware accepts one continuous stream per transmission up
# to this window; longer audio must be split, or the driver's TX queue overflows
# and every block past the window is dropped (-EAGAIN). Sentence-boundary
# splitting of the *source text* (synthesize per sentence) would land the gaps
# on natural pauses; this reference script chunks the PCM at the size limit.
MAX_MONO_BYTES_PER_TRANSMISSION = 35000

device_id = "3CE1CE0A-A629-2E92-D708-E49E71045D07" #Please enter the id of your device (that is, the device id used to connect to your BT device here)
deepgram_api_id="f2e9ebf2f223ae423c88bf601ce1a157699d3005" #enter your deepgram id here
audio_write_characteristic_uuid = "19B10003-E8F2-537E-4F6C-D104768A1214" #dont change this

gain = 5

async def main():
    global remaining_bytes
    global audio_write_characteristic_uuid
    parser = argparse.ArgumentParser(description="Accept a string and print it")
    parser.add_argument("input_string", type=str, help="The string to be printed")
    args = parser.parse_args()
    print(args.input_string) #stage one: get the input string
    SPEAK_OPTIONS = {"text": args.input_string}

    try:
    # STEP 1: Create a Deepgram client using the API key from environment variables
        deepgram = DeepgramClient(api_key=deepgram_api_id) #INSERT YOUT DEEPGRAM KEY HERE

        # STEP 2: Configure the options (such as model choice, audio configuration, etc.)
        options = SpeakOptions(
            model="aura-stella-en",
            encoding="linear16",
            container="wav"
        )

        # STEP 3: Call the save method on the speak property
        response = deepgram.speak.v("1").save(filename, SPEAK_OPTIONS, options)
        print(response.to_json(indent=4))

    except Exception as e:
        print(f"Exception: {e}")

    file_path = 'output2.wav'

# Open the wav file
    with wave.open(file_path, 'rb') as wav_file:
        # Extract raw audio frames
        frames = wav_file.readframes(wav_file.getnframes())
        # Get the number of channels
        num_channels = wav_file.getnchannels()
        # Get the sample width in bytes
        sample_width = wav_file.getsampwidth()
        # Get the frame rate (samples per second)
        frame_rate = wav_file.getframerate()
        # Convert the audio frames to a numpy array
        audio_data = np.frombuffer(frames, dtype=np.int16)
        # one channel, 16 bit, 24000
        print("Channels:", num_channels)
        print("Sample Width (bytes):", sample_width)
        print("Frame Rate (samples per second):", frame_rate)
        print("Audio Data:", audio_data)
        print("Audio length: ", len(audio_data))

    # Select every third sample for down-sampling
    third_samples = audio_data[::3] * gain

    # New sample rate (original rate divided by 3)
    new_sample_rate = frame_rate // 3

    # Convert third_samples to bytes for writing to a new wav file
    third_samples_bytes = third_samples.tobytes()

    # Write the resampled audio data to a new WAV file
    new_file_path = 'output_80002.wav'
    with wave.open(new_file_path, 'wb') as new_wav_file:
        new_wav_file.setnchannels(num_channels)
        new_wav_file.setsampwidth(sample_width)
        new_wav_file.setframerate(new_sample_rate)
        new_wav_file.writeframes(third_samples_bytes)

    print(f"Resampled audio written to {new_file_path}")

    # Write the third samples to a text file
    output_file_path = 'every_third_sample2.txt'
    with open(output_file_path, 'w') as f_:
        for samples in third_samples:
            if samples != '':
                f_.write(f"{samples}\n")

    print(f"Every third sample written to {output_file_path}")
    f = open('every_third_sample2.txt','r').read()
    f = np.array(list(map(int,f.split('\n')[:-1]))).astype(np.int16).tobytes()

    def pad_for_firmware(pcm: bytes) -> bytes:
        # The firmware's handler stalls on a total that's a multiple of PACKET_SIZE
        # and misreads a 4-byte tail as a new length header; pad with silence to
        # escape both cases (same rule the phone client uses).
        r = len(pcm) % PACKET_SIZE
        add = 8 if r == 0 else (2 if r == 4 else 0)
        return pcm + (b"\x00" * add) if add else pcm

    pcm = bytes(f)
    transmissions = [
        pad_for_firmware(pcm[o:o + MAX_MONO_BYTES_PER_TRANSMISSION])
        for o in range(0, len(pcm), MAX_MONO_BYTES_PER_TRANSMISSION)
    ]
    print(f"Mono PCM bytes: {len(pcm)} -> {len(transmissions)} transmission(s)")

    async with BleakClient(device_id) as client:
        print(client.address)
        print(f"MTU: {client.mtu_size}")
        for service in client.services:
            print(service)

        pump = asyncio.Event()

        async def on_notify(sender: bleak.BleakGATTCharacteristic, data: bytearray):
            pump.set()

        await client.start_notify(audio_write_characteristic_uuid, on_notify)
        await asyncio.sleep(0.5)

        for i, mono in enumerate(transmissions, 1):
            header = np.array([len(mono)], dtype="<u4").tobytes()
            pump.clear()
            await client.write_gatt_char(audio_write_characteristic_uuid, header, response=True)
            await asyncio.wait_for(pump.wait(), timeout=10)
            print(f"[{i}/{len(transmissions)}] {len(mono)} bytes")
            for off in range(0, len(mono), PACKET_SIZE):
                chunk = mono[off:off + PACKET_SIZE]
                pump.clear()
                await client.write_gatt_char(audio_write_characteristic_uuid, chunk, response=True)
                if len(chunk) < PACKET_SIZE:
                    break  # final chunk; no pump notify follows a short write
                await asyncio.wait_for(pump.wait(), timeout=10)
            # Let the device drain this stream before starting the next
            # transmission (each stream DRAINs itself; back-to-back headers re-arm
            # cleanly, and the gap is a natural pause between chunks).
            await asyncio.sleep(0.4)

        await client.stop_notify(audio_write_characteristic_uuid)
        print("done")

if __name__ == "__main__":
    asyncio.run(main())
