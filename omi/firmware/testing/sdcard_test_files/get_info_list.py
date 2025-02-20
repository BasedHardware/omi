import asyncio
import bleak
import numpy as np
from bleak import BleakClient

device_id = "8C8ED9F9-8A05-F50F-AECE-E89674761304" #Please enter the id of your device (that is, the device id used to connect to your BT device here)
storage_uuid = "30295782-4301-EABD-2904-2849ADFEAE43" #dont change this

async def main():
        async with BleakClient(device_id) as client:

            r = await client.read_gatt_char(storage_uuid)
            await asyncio.sleep(2.0)

            while(True):
                 await asyncio.sleep(2.0)
                 print(np.frombuffer(r,dtype=np.uint32))

        
if __name__ == "__main__":
    asyncio.run(main())


