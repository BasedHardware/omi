
import os
from dotenv import load_dotenv
import asyncio
import bleak
import numpy as np
from bleak import BleakClient
load_dotenv()
audio_frames = []

device_id = "3C71D8C0-B1AF-5976-A47F-5D7A96267F67" #Please enter the id of your device (that is, the device id used to connect to your BT device here)
button_uuid = "23BA7924-0000-1000-7450-346EAC492E92" #dont change this
button_read_uuid = "23BA7925-0000-1000-7450-346EAC492E92"
read_or_clear = 0 # 0 for read, 1 for clear
file_num = 1
count = 1
async def main():
        
        global device_uuid
        global storage_uuid
        global count

        async with BleakClient(device_id) as client:

                async def on_notify(sender: bleak.BleakGATTCharacteristic, data: bytearray):
                        print(data)
                stuff = await client.start_notify(button_read_uuid, on_notify)
                await asyncio.sleep(1)   
                while True:
                    await asyncio.sleep(1)

        
if __name__ == "__main__":
    asyncio.run(main())
