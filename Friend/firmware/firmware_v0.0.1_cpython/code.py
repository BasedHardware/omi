from _bleio import adapter
from board import IMU_PWR, IMU_SCL, IMU_SDA, TX, RX
from busio import I2C, UART
from digitalio import DigitalInOut, Direction
from time import sleep
from adafruit_ble import BLERadio
from adafruit_lsm6ds.lsm6ds3 import LSM6DS3
from adafruit_ble.services.nordic import UARTService

ble = BLERadio()

# Customize the device behavior here
DEVICE_NAME = "XIAO nRF52840 Sense"
INTERVAL = 2
SENSITIVITY = 0.01

# Turn on IMU and wait 50 ms
imu_pwr = DigitalInOut(IMU_PWR)
imu_pwr.direction = Direction.OUTPUT
imu_pwr.value = True
sleep(0.2)
print('imu turned on')
# Set up I2C bus and initialize IMU
i2c_bus = I2C(IMU_SCL, IMU_SDA)
sensor = LSM6DS3(i2c_bus)
uart = UARTService()

class BTHomeAdvertisement:
    _ADV_FLAGS = [0x02, 0x01, 0x06]
    _ADV_SVC_DATA = [0x06, 0x16, 0xD2, 0xFC, 0x40, 0x22, 0x00]

    def _name2adv(self, local_name):
        adv_element = bytearray([len(local_name) + 1, 0x09])
        adv_element.extend(bytes(local_name, "utf-8"))
        return adv_element

    def __init__(self, local_name=None):
        if local_name:
            self.adv_local_name = self._name2adv(local_name)
        else:
            self.adv_local_name = self._name2adv(adapter.name)

    def adv_data(self, movement):
        adv_data = bytearray(self._ADV_FLAGS)
        adv_svc_data = bytearray(self._ADV_SVC_DATA)
        adv_svc_data[-1] = movement
        adv_data.extend(adv_svc_data)
        adv_data.extend(self.adv_local_name)
        return adv_data


bthome = BTHomeAdvertisement(DEVICE_NAME)
print('advert started')
while True:
    # print('running')
    while ble.connected:
        print('connected')
        uart.write('hi')
        while True:
            gyro_x, gyro_y, gyro_z = sensor.gyro
            moving = gyro_x**2 + gyro_y**2 + gyro_z**2
            if moving > SENSITIVITY:
                print("Moving")
                uart.write(f"[{gyro_x},{gyro_y},{gyro_z}]".encode('utf8'))
                sleep(0.01)
                adv_data = bthome.adv_data(1)
            else:
                adv_data = bthome.adv_data(0)
            sleep(INTERVAL)
            adapter.stop_advertising()

