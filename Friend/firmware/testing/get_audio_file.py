import argparse
import os
from dotenv import load_dotenv
import wave
import asyncio
import bleak
import numpy as np
from bleak import BleakClient
import opuslib
load_dotenv()
audio_frames = []
decoder=opuslib.Decoder(16000, 1)
device_id = "3CE1CE0A-A629-2E92-D708-E49E71045D07" #Please enter the id of your device (that is, the device id used to connect to your BT device here)
storage_uuid = "30295781-4301-EABD-2904-2849ADFEAE43" #dont change this
storage_read_uuid = "30295782-4301-EABD-2904-2849ADFEAE43" 
count = 0
pcm_data=bytearray()
done =False
async def main():
        
        global device_uuid
        global storage_uuid
        global count
        global pcm_data
        global done
        global decoder
        async with BleakClient(device_id) as client:
            with open("my_file.txt", "wb") as binary_file:
                result = bytearray()
                print('a')


                async def on_notify(sender: bleak.BleakGATTCharacteristic, data: bytearray):
                        # Write bytes to file
                        binary_file.write(data)
                        global count
                        global done
                        print(len(data))
                        amount_to_append = data[3]
                        audio_frames.append(data[4:data[3]+4])
                        count +=1
                        print(np.frombuffer(data,dtype=np.uint8))   


                stuff = await client.start_notify(storage_uuid, on_notify)
                print('b')
                # await client.read_gatt_char(storage_read_uuid)
                await asyncio.sleep(1)
                await client.write_gatt_char(storage_uuid, b'd', response=True)
                print('c')
                print(stuff)
                await asyncio.sleep(1)   
                while True:
                    await asyncio.sleep(1)

        
if __name__ == "__main__":
    asyncio.run(main())


