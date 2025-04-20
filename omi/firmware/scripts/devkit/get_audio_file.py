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
read_or_clear = 0 # 0 for read, 1 for clear
file_num = 1
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
                        
                        global count
                        global done
                        print(len(data))
                        if (len(data)==1):
                             print(data[0])
                             if (data[0] == 100):
                                  pass
                                #   print('audio transfer done')
                                #   command = bytearray([0,2,0,0,0,0])
                                #   await client.write_gatt_char(storage_uuid, command, response=True)
                             if(data[0] == 0):
                                  print('valid response')
                        else:
                            binary_file.write(data)
                            amount_to_append = data[3]
                            audio_frames.append(data[4:data[3]+4])
                            count +=1
                            print(np.frombuffer(data,dtype=np.uint8))   


                stuff = await client.start_notify(storage_uuid, on_notify)

                # await client.read_gatt_char(storage_read_uuid)
                await asyncio.sleep(1)
                command = bytearray([read_or_clear,file_num ,0,0,0,0])
                await client.write_gatt_char(storage_uuid, command, response=True)
            
                print(stuff)
                await asyncio.sleep(1)   
                while True:
                    await asyncio.sleep(1)

        
if __name__ == "__main__":
    asyncio.run(main())


