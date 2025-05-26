import asyncio
import bleak
import numpy as np
from bleak import BleakClient
import time

audio_frames = []
device_id = "3C71D8C0-B1AF-5976-A47F-5D7A96267F67" #Please enter the id of your device (that is, the device id used to connect to your BT device here)
storage_uuid = "30295781-4301-EABD-2904-2849ADFEAE43" #dont change this
storage_read_uuid = "30295782-4301-EABD-2904-2849ADFEAE43" 
read_or_clear = 0 # 0 for read, 1 for clear
file_num = 1
count = 0
pcm_data=bytearray()
done =False
start_time = time.time()
total = 0
async def main():
        
        global device_uuid
        global storage_uuid
        global count
        global pcm_data
        global done
        global decoder
        global start_time
        global total
        async with BleakClient(device_id) as client:
            with open("my_file.txt", "wb") as binary_file:
                result = bytearray()

                async def on_notify(sender: bleak.BleakGATTCharacteristic, data: bytearray):
                        # Write bytes to file
                        global start_time
                        global count
                        global done
                        global total
          
                        if (len(data)==1):
                             if (data[0] == 100):
                                  print('total bandwidth in bytes/second')
                                  result = total / (time.time()-start_time)
                                  print(result)
                                  print('audio transfer done')
                             if(data[0] == 0):
                                  print('valid response')
                        else:
                                              
                             if (len(data) == 83):
                                  total +=83
                                #   audio_frames.append(data)
                                  binary_file.write(data)
                                #   print('current rate')
                                #   f = total / (time.time()-start_time)
                                #   print(f)

                stuff = await client.start_notify(storage_uuid, on_notify)
                await asyncio.sleep(1)
                command = bytearray([read_or_clear,file_num ,0,0,0,0])
                await client.write_gatt_char(storage_uuid, command, response=True)
            
                print(stuff)
                await asyncio.sleep(1)   
                while True:
                    await asyncio.sleep(1)

        
if __name__ == "__main__":
    asyncio.run(main())


