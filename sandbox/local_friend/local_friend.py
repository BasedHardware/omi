import asyncio
import pyaudio
from Foundation import NSObject, NSData, NSUUID, NSLog
import objc
from CoreBluetooth import (
    CBPeripheralManager,
    CBPeripheralManagerStatePoweredOn,
    CBMutableService,
    CBMutableCharacteristic,
    CBCharacteristicProperties,
    CBAttributePermissions,
    CBAdvertisementDataLocalNameKey,
    CBAdvertisementDataServiceUUIDsKey
)

# UUIDs for the services and characteristics
BATTERY_SERVICE_UUID = "180F"
BATTERY_CHARACTERISTIC_UUID = "2A19"
AUDIO_SERVICE_UUID = "19B10000-E8F2-537E-4F6C-D104768A1214"
AUDIO_CHARACTERISTIC_UUID = "19B10001-E8F2-537E-4F6C-D104768A1214"
CODEC_CHARACTERISTIC_UUID = "19B10002-E8F2-537E-4F6C-D104768A1214"
DEVICE_NAME = "Friend"

# Define the delegate protocol
CBPeripheralManagerDelegate = objc.protocolNamed('CBPeripheralManagerDelegate')

class PeripheralDelegate(NSObject, protocols=[CBPeripheralManagerDelegate]):
    def peripheralManagerDidUpdateState_(self, peripheral):
        NSLog(f"Peripheral Manager State Updated: {peripheral.state()}")
        if peripheral.state() == CBPeripheralManagerStatePoweredOn:
            NSLog("Peripheral Manager Powered On")
            self.add_services(peripheral)
        else:
            NSLog(f"Peripheral Manager State is not powered on: {peripheral.state()}")

    def add_services(self, peripheral):
        NSLog("Adding Services")

        # Battery Service and Characteristic
        battery_characteristic = CBMutableCharacteristic.alloc().initWithType_properties_value_permissions_(
            NSUUID.UUIDWithString_(BATTERY_CHARACTERISTIC_UUID),
            CBCharacteristicProperties.CBCharacteristicPropertyRead | CBCharacteristicProperties.CBCharacteristicPropertyNotify,
            None,
            CBAttributePermissions.CBAttributePermissionsReadable
        )
        battery_service = CBMutableService.alloc().initWithType_primary_(
            NSUUID.UUIDWithString_(BATTERY_SERVICE_UUID), True
        )
        battery_service.setCharacteristics_([battery_characteristic])
        peripheral.addService_(battery_service)

        # Audio Service and Characteristics
        audio_characteristic = CBMutableCharacteristic.alloc().initWithType_properties_value_permissions_(
            NSUUID.UUIDWithString_(AUDIO_CHARACTERISTIC_UUID),
            CBCharacteristicProperties.CBCharacteristicPropertyNotify,
            None,
            CBAttributePermissions.CBAttributePermissionsReadable
        )
        codec_characteristic = CBMutableCharacteristic.alloc().initWithType_properties_value_permissions_(
            NSUUID.UUIDWithString_(CODEC_CHARACTERISTIC_UUID),
            CBCharacteristicProperties.CBCharacteristicPropertyRead | CBCharacteristicProperties.CBCharacteristicPropertyWrite,
            NSData.dataWithBytes_length_(b'\x01', 1),  # Default to PCM 8-bit, 16kHz, mono
            CBAttributePermissions.CBAttributePermissionsReadable | CBAttributePermissions.CBAttributePermissionsWriteable
        )
        audio_service = CBMutableService.alloc().initWithType_primary_(
            NSUUID.UUIDWithString_(AUDIO_SERVICE_UUID), True
        )
        audio_service.setCharacteristics_([audio_characteristic, codec_characteristic])
        peripheral.addService_(audio_service)

        NSLog("Services Added")
        peripheral.startAdvertising_({
            CBAdvertisementDataLocalNameKey: DEVICE_NAME,
            CBAdvertisementDataServiceUUIDsKey: [NSUUID.UUIDWithString_(BATTERY_SERVICE_UUID), NSUUID.UUIDWithString_(AUDIO_SERVICE_UUID)]
        })
        NSLog("Started Advertising")

    def peripheralManager_didReceiveReadRequest_(self, peripheral, request):
        NSLog("Read Request Received")
        if request.characteristic().UUID() == NSUUID.UUIDWithString_(BATTERY_CHARACTERISTIC_UUID):
            response_data = self.get_battery_level()
        elif request.characteristic().UUID() == NSUUID.UUIDWithString_(CODEC_CHARACTERISTIC_UUID):
            response_data = self.get_codec_type()
        else:
            response_data = NSData.data()
        request.setValue_(response_data)
        peripheral.respondToRequest_withResult_(request, 0)  # 0 means success

    def peripheralManager_didReceiveWriteRequests_(self, peripheral, requests):
        NSLog("Write Request Received")
        for request in requests:
            if request.characteristic().UUID() == NSUUID.UUIDWithString_(CODEC_CHARACTERISTIC_UUID):
                self.set_codec_type(request.value())
        peripheral.respondToRequest_withResult_(requests[0], 0)  # 0 means success

    def peripheralManager_central_didSubscribeToCharacteristic_(self, peripheral, central, characteristic):
        NSLog("Central Subscribed to Characteristic")
        if characteristic.UUID() == NSUUID.UUIDWithString_(AUDIO_CHARACTERISTIC_UUID):
            asyncio.create_task(self.notify_clients(peripheral, characteristic))

    def get_battery_level(self):
        # Simulate battery level (for example, 75%)
        battery_level = 75
        return NSData.dataWithBytes_length_(bytes([battery_level]), 1)

    def get_codec_type(self):
        # Return the default codec type (PCM 8-bit, 16kHz, mono)
        return NSData.dataWithBytes_length_(b'\x01', 1)

    def set_codec_type(self, value):
        # Set the codec type based on the received value
        codec_type = int.from_bytes(value.bytes(), byteorder='little')
        NSLog(f"Codec Type Set: {codec_type}")

    async def notify_clients(self, peripheral, characteristic):
        p = pyaudio.PyAudio()
        stream = p.open(format=pyaudio.paInt16, channels=1, rate=16000, input=True, frames_per_buffer=160)

        try:
            packet_number = 0
            while True:
                audio_data = stream.read(160)
                packet_header = (packet_number.to_bytes(2, 'little') + b'\x00')
                packet_data = packet_header + audio_data
                notify_data = NSData.dataWithBytes_length_(packet_data, len(packet_data))
                characteristic.setValue_(notify_data)
                peripheral.updateValue_forCharacteristic_onSubscribedCentrals_(notify_data, characteristic, None)
                packet_number += 1
                await asyncio.sleep(0.01)  # Adjust this delay as needed for real-time streaming
        finally:
            stream.stop_stream()
            stream.close()
            p.terminate()

async def run_server():
    NSLog("Initializing Peripheral Delegate")
    delegate = PeripheralDelegate.alloc().init()
    
    NSLog("Initializing Peripheral Manager")
    peripheral = CBPeripheralManager.alloc().initWithDelegate_queue_options_(delegate, None, None)
    
    # Wait for state updates
    while peripheral.state() != CBPeripheralManagerStatePoweredOn:
        NSLog(f"Waiting for Peripheral Manager to power on. Current state: {peripheral.state()}")
        await asyncio.sleep(1)

    NSLog("Peripheral Manager is Powered On. Entering Main Loop")
    try:
        while True:
            await asyncio.sleep(1)
    except Exception as e:
        NSLog(f"Exception in main loop: {str(e)}")

if __name__ == "__main__":
    try:
        NSLog("Starting BLE Peripheral Script")
        asyncio.run(run_server())
    except Exception as e:
        NSLog(f"Exception in asyncio run: {str(e)}")
