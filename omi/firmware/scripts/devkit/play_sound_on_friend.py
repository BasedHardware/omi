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

remaining_bytes = 0
remaining_bytes_b = bytearray()
packet_size = 400
total_offset = 0
device_id = "3CE1CE0A-A629-2E92-D708-E49E71045D07" #Please enter the id of your device (that is, the device id used to connect to your BT device here)
deepgram_api_id="f2e9ebf2f223ae423c88bf601ce1a157699d3005" #enter your deepgram id here
audio_write_characteristic_uuid = "19B10003-E8F2-537E-4F6C-D104768A1214" #dont change this
MAX_ALLOWED_SAMPLES = 50000

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

    remaining_bytes = np.array([len(f)]).astype(np.uint32)[0]
    remaining_bytes_b = np.array([len(f)]).astype(np.uint32).tobytes()
    if (remaining_bytes> MAX_ALLOWED_SAMPLES):
        print("Array too large to play. Exitting")
        exit()
    print("Number of samples about to be sent: ",remaining_bytes)
    print("about to start...")
    async with BleakClient(device_id) as client:
        print(client.address)
        offset_ = client.mtu_size
        print(offset_)
        temp = client.services
        for service in temp:
            print(service)

        async def on_notify(sender: bleak.BleakGATTCharacteristic, data: bytearray):
            global remaining_bytes
            global total_offset
            global remaining_bytes_b
            global packet_size
            global audio_write_characteristic_uuid
            print(np.frombuffer(data,dtype=np.int16)[0])
            if (remaining_bytes > packet_size):
                
                final_offset = total_offset
                total_offset = packet_size + total_offset
                remaining_bytes = remaining_bytes - packet_size
                print("sending indexes %d to %d",final_offset,final_offset+packet_size)
                await client.write_gatt_char(audio_write_characteristic_uuid, f[final_offset:(final_offset+packet_size)], response=True)
                
            elif (remaining_bytes > 0 and remaining_bytes <= packet_size):
                print('almost done')
                print(remaining_bytes)
                start_idx = total_offset
                total_offset = remaining_bytes+ total_offset
                offset_ = remaining_bytes
                remaining_bytes = 0
                print("sending indexes",start_idx,start_idx+offset_)
                await client.write_gatt_char(audio_write_characteristic_uuid, f[start_idx:(start_idx+offset_)], response=True)
            else:
                print('done')
                print(total_offset)
                print('Shutting down')
                exit()
        await client.start_notify(audio_write_characteristic_uuid, on_notify)
        await asyncio.sleep(1)
        await client.write_gatt_char(audio_write_characteristic_uuid, remaining_bytes_b, response=True)
        await asyncio.sleep(1)   
        while True:
           await asyncio.sleep(1)

if __name__ == "__main__":
    asyncio.run(main())
