import argparse
import os
from dotenv import load_dotenv

import asyncio
import bleak
import numpy as np
from bleak import BleakClient

load_dotenv()

device_id = "3CE1CE0A-A629-2E92-D708-E49E71045D07" #Please enter the id of your device (that is, the device id used to connect to your BT device here)
storage_uuid = "00001541-1212-EFDE-1523-785FEABCD123" #dont change this


async def main():
        
        global device_uuid
        global storage_uuid
        async with BleakClient(device_id) as client:
            result = bytearray()
            print('a')
            async def on_notify(sender: bleak.BleakGATTCharacteristic, data: bytearray):
                print('done')
                print(np.frombuffer(data,dtype=np.uint8))
            await client.start_notify(storage_uuid, on_notify)
            print('b')
            await asyncio.sleep(1)
            await client.write_gatt_char(storage_uuid, b'd', response=True)
            print('c')
            await asyncio.sleep(1)   
            while True:
                await asyncio.sleep(1)

        
if __name__ == "__main__":
    asyncio.run(main())


