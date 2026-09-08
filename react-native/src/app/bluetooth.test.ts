import {emptyDeviceListHint} from './bluetooth';

test.each([
  [null, 'poweredOn', 'No Omi device was discovered.'],
  ['', 'poweredOn', 'No Omi device was discovered.'],
  ['Bluetooth is poweredOn', 'poweredOn', 'No Omi device was discovered.'],
  ['Bluetooth is powered on', 'poweredOn', 'No Omi device was discovered.'],
  ['Bluetooth is poweredOff', 'poweredOff', 'Bluetooth off'],
  ['', 'poweredOff', 'Bluetooth off'],
  ['Bluetooth is unauthorized', 'unauthorized', 'Bluetooth permission needed'],
  ['Bluetooth is unknown', 'unknown', 'Bluetooth status unknown'],
  ['Bluetooth is not powered on', 'poweredOff', 'Bluetooth is not powered on'],
  [
    'Bluetooth permission is required',
    'unauthorized',
    'Bluetooth permission is required',
  ],
  ['Bluetooth is unavailable', 'unknown', 'Bluetooth is unavailable'],
  ['No Omi devices found', 'poweredOn', 'No Omi devices found'],
  ['BLE scan failed: 2', 'poweredOn', 'Bluetooth scan failed.'],
  ['Omi connection failed: 133', 'poweredOn', 'Omi connection failed.'],
  [
    'Omi service discovery failed: 8',
    'poweredOn',
    'Omi service discovery failed.',
  ],
  ['Omi codec read failed: 257', 'poweredOn', 'Omi codec read failed.'],
  [
    'Omi notification subscription failed: 133',
    'poweredOn',
    'Omi notification subscription failed.',
  ],
] as const)('emptyDeviceListHint(%j, %s)', (event, bluetooth, expected) => {
  expect(emptyDeviceListHint(event, bluetooth)).toBe(expected);
});
