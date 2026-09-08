import {bluetoothSessionColor, emptyDeviceListHint} from './bluetooth';

test.each([
  [null, 'poweredOn', 'No Omi device was discovered.'],
  ['', 'poweredOn', 'No Omi device was discovered.'],
  ['Bluetooth is poweredOn', 'poweredOn', 'No Omi device was discovered.'],
  ['Bluetooth is powered on', 'poweredOn', 'No Omi device was discovered.'],
  ['Bluetooth is poweredOff', 'poweredOff', 'Bluetooth off'],
  ['', 'poweredOff', 'Bluetooth off'],
  ['Bluetooth is unauthorized', 'unauthorized', 'Bluetooth permission needed'],
  ['Bluetooth is unknown', 'unknown', 'Bluetooth status unknown'],
  ['Bluetooth is not powered on', 'poweredOff', 'Bluetooth off'],
  [
    'Bluetooth permission is required',
    'unauthorized',
    'Bluetooth permission needed',
  ],
  [
    'Location permission is required for Bluetooth scanning',
    'poweredOn',
    'Location permission is required for Bluetooth scanning',
  ],
  ['Bluetooth is unavailable', 'unknown', 'Bluetooth status unknown'],
  ['Bluetooth is unavailable', 'poweredOff', 'Bluetooth off'],
  ['Bluetooth is unavailable', 'poweredOn', 'No Omi device was discovered.'],
  ['Bluetooth adapter not checked', 'unknown', 'Checking Bluetooth…'],
  [
    'Bluetooth adapter not checked',
    'poweredOn',
    'No Omi device was discovered.',
  ],
  ['Bluetooth adapter not checked', 'poweredOff', 'Bluetooth off'],
  [
    'Bluetooth LE scanner is unavailable',
    'poweredOn',
    'Bluetooth LE scanner is unavailable',
  ],
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
  ['Scanning for Omi devices', 'poweredOn', 'No Omi device was discovered.'],
] as const)('emptyDeviceListHint(%j, %s)', (event, bluetooth, expected) => {
  expect(emptyDeviceListHint(event, bluetooth)).toBe(expected);
});

test('emptyDeviceListHint keeps Scanning copy only while a scan is busy', () => {
  expect(
    emptyDeviceListHint('Scanning for Omi devices', 'poweredOn', true),
  ).toBe('Scanning for Omi devices');
});

test.each([
  [null, 'unknown', '#b4ad9f'],
  ['Bluetooth adapter not checked', 'unknown', '#b4ad9f'],
  ['Bluetooth is unavailable', 'unknown', '#d9826f'],
  ['Bluetooth adapter not checked', 'poweredOn', '#45b79b'],
  ['', 'poweredOff', '#d9826f'],
] as const)(
  'bluetoothSessionColor(%j, %s)',
  (lastEvent, bluetooth, expected) => {
    expect(
      bluetoothSessionColor(lastEvent === null ? null : {bluetooth, lastEvent}),
    ).toBe(expected);
  },
);
