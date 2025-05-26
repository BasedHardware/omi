import asyncio
import bleak
import numpy as np
from bleak import BleakClient

device_id = "3C71D8C0-B1AF-5976-A47F-5D7A96267F67" #Please enter the id of your device (that is, the device id used to connect to your BT device here)
storage_uuid = "30295781-4301-EABD-2904-2849ADFEAE43" #dont change this
storage_read_uuid = "30295782-4301-EABD-2904-2849ADFEAE43" 
read_or_clear = 0 # 0 for read, 1 for clear
file_num = 1
command_num = 1
count = 1
async def main():
        
        global device_uuid
        global storage_uuid
        global count

        async with BleakClient(device_id) as client:


                async def on_notify(sender: bleak.BleakGATTCharacteristic, data: bytearray):
                        global count
                        # Write bytes to file
                        if (len(data)==1):
                             print(data[0])
                             if (data[0] == 200):                                
                                print('done')

                stuff = await client.start_notify(storage_uuid, on_notify)

                await asyncio.sleep(1)
                command = bytearray([command_num,file_num ,0,0,0,0])
                await client.write_gatt_char(storage_uuid, command, response=True)
                await asyncio.sleep(1)   
                while True:
                    await asyncio.sleep(1)

        
if __name__ == "__main__":
    asyncio.run(main())

