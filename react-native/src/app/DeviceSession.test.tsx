import React from 'react';
import ReactTestRenderer, {act} from 'react-test-renderer';
import {DeviceSession, homeConnectionStatus} from './DeviceSession';
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

test.each(['affordance', 'compact', 'overview'] as const)(
  '%s shows pending readiness and cancels the requested connection',
  async variant => {
    const snapshot = {
      bluetooth: 'poweredOn',
      phase: 'connecting',
      capture: 'idle',
      connectedDeviceId: 'omi-test',
      devices: [{id: 'omi-test', name: 'Omi', connected: false, rssi: -40}],
    } as PlatformNativeSnapshot;
    expect(homeConnectionStatus(snapshot)).toMatchObject({
      connectedDevice: null,
      label: 'Connecting to Omi…',
    });
    const onToggle = jest.fn();
    let renderer!: ReactTestRenderer.ReactTestRenderer;
    await act(async () => {
      renderer = ReactTestRenderer.create(
        <DeviceSession
          nativeSnapshot={snapshot}
          deviceBusy={false}
          deviceScanMessage={null}
          variant={variant}
          onScan={() => {}}
          onToggle={onToggle}
        />,
      );
    });
    expect(JSON.stringify(renderer.toJSON())).toContain('Connecting…');
    await act(async () => {
      renderer.root
        .findAllByProps({accessibilityLabel: 'Cancel connection to Omi'})[0]
        .props.onPress();
    });
    expect(onToggle).toHaveBeenCalledWith('omi-test', true);
    await act(async () => renderer.unmount());
  },
);

test.each(['affordance', 'compact', 'overview'] as const)(
  '%s exposes explicit remembered-device actions without inventing a scan result',
  async variant => {
    const onToggle = jest.fn(),
      onForget = jest.fn(),
      onScan = jest.fn();
    let renderer!: ReactTestRenderer.ReactTestRenderer;
    await act(async () => {
      renderer = ReactTestRenderer.create(
        <DeviceSession
          variant={variant}
          nativeSnapshot={null}
          deviceBusy={false}
          deviceScanMessage={null}
          rememberedDevice={{id: 'saved-id', name: 'My Omi'}}
          onForgetRemembered={onForget}
          onScan={onScan}
          onToggle={onToggle}
        />,
      );
    });
    try {
      expect(onToggle).not.toHaveBeenCalled();
      expect(onScan).not.toHaveBeenCalled();
      act(() =>
        renderer.root
          .findAll(
            node => node.props.accessibilityLabel === 'Reconnect My Omi',
          )[0]!
          .props.onPress(),
      );
      expect(onToggle).toHaveBeenCalledWith('saved-id', false);
      act(() =>
        renderer.root
          .findAll(
            node => node.props.accessibilityLabel === 'Forget My Omi',
          )[0]!
          .props.onPress(),
      );
      expect(onForget).toHaveBeenCalledTimes(1);
      expect(JSON.stringify(renderer.toJSON())).not.toContain('dBm');
    } finally {
      await act(async () => renderer.unmount());
    }
  },
);

test.each(['compact', 'overview'] as const)(
  '%s never invents signal strength for a retrieved device',
  async variant => {
    let renderer!: ReactTestRenderer.ReactTestRenderer;
    await act(async () => {
      renderer = ReactTestRenderer.create(
        <DeviceSession
          variant={variant}
          nativeSnapshot={{
            bluetooth: 'poweredOn',
            devices: [{id: 'saved-id', name: 'My Omi', connected: false}],
            connectedDeviceId: null,
            phase: 'disconnected',
            capture: 'idle',
            lastEvent: '',
            microphone: 'unknown',
            notifications: 'unknown',
          }}
          deviceBusy={false}
          deviceScanMessage={null}
          onScan={() => {}}
          onToggle={() => {}}
        />,
      );
    });
    try {
      const output = JSON.stringify(renderer.toJSON());
      expect(output).toContain('Signal unavailable');
      expect(output).not.toContain('dBm');
    } finally {
      await act(async () => renderer.unmount());
    }
  },
);

test('connected audio status waits for an actual packet without changing capture ownership', () => {
  const base: PlatformNativeSnapshot = {
    bluetooth: 'poweredOn',
    phase: 'connected',
    capture: 'recording',
    connectedDeviceId: 'omi',
    devices: [{id: 'omi', name: 'Omi', connected: true}],
    lastEvent: '',
    microphone: 'unknown',
    notifications: 'unknown',
  };
  expect(homeConnectionStatus({...base, audioStatus: 'waiting'}).label).toBe(
    'Connected · Waiting for audio',
  );
  expect(homeConnectionStatus({...base, audioStatus: 'active'}).label).toBe(
    'Connected · Listening',
  );
  expect(
    homeConnectionStatus({...base, capture: 'idle', audioStatus: 'waiting'})
      .label,
  ).toBe('Connected · Ready');
});

test.each(['compact', 'overview', 'affordance'] as const)(
  '%s shows transport-ready waiting status',
  async variant => {
    let renderer!: ReactTestRenderer.ReactTestRenderer;
    await act(async () => {
      renderer = ReactTestRenderer.create(
        <DeviceSession
          variant={variant}
          deviceBusy={false}
          deviceScanMessage={null}
          onScan={() => {}}
          onToggle={() => {}}
          nativeSnapshot={{
            bluetooth: 'poweredOn',
            phase: 'connected',
            capture: 'recording',
            audioStatus: 'waiting',
            connectedDeviceId: 'omi',
            devices: [{id: 'omi', name: 'Omi', connected: true}],
            lastEvent: '',
            microphone: 'unknown',
            notifications: 'unknown',
          }}
        />,
      );
    });
    expect(JSON.stringify(renderer.toJSON())).toContain('Waiting for audio');
    expect(JSON.stringify(renderer.toJSON())).not.toContain('Listening');
    await act(async () => renderer.unmount());
  },
);
