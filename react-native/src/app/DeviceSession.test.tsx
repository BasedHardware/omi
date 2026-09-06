import React from 'react';
import ReactTestRenderer, {act} from 'react-test-renderer';
import {DeviceSession} from './DeviceSession';
import type {PlatformNativeSnapshot} from '../omiNative';

jest.mock('../omiNative', () => ({
  isBluetoothScanAvailable: () => true,
}));

test('connected device details show reported values and truthful unknown fields', async () => {
  const snapshot = {
    bluetooth: 'poweredOn',
    devices: [
      {
        id: 'omi-test',
        name: 'Omi',
        connected: true,
        rssi: -40,
        information: {model: 'Omi Dev Kit', firmware: '1.2.3'},
      },
    ],
    connectedDeviceId: 'omi-test',
    capture: 'idle',
  } as PlatformNativeSnapshot;
  let renderer!: ReactTestRenderer.ReactTestRenderer;
  await act(async () => {
    renderer = ReactTestRenderer.create(
      <DeviceSession
        nativeSnapshot={snapshot}
        deviceBusy={false}
        deviceScanMessage={null}
        variant="compact"
        onScan={() => {}}
        onToggle={() => {}}
      />,
    );
  });
  const output = JSON.stringify(renderer.toJSON());
  expect(output).toContain('Omi Dev Kit');
  expect(output).toContain('1.2.3');
  expect(output).toContain('Unknown');
  expect(output).toContain('Serial number');
  await act(async () => {
    renderer.update(
      <DeviceSession
        nativeSnapshot={{...snapshot, devices: []}}
        deviceBusy={false}
        deviceScanMessage={null}
        variant="compact"
        onScan={() => {}}
        onToggle={() => {}}
      />,
    );
  });
  expect(JSON.stringify(renderer.toJSON())).not.toContain('Omi Dev Kit');
  await act(async () => renderer.unmount());
});
