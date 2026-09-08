import React from 'react';
import ReactTestRenderer, {act} from 'react-test-renderer';
import {DeviceSession, homeConnectionStatus} from './DeviceSession';
import type {PlatformNativeSnapshot} from '../omiNative';

jest.mock('../omiNative', () => ({
  isBluetoothScanAvailable: (state?: string) => state === 'poweredOn',
}));

test('connected device details show reported values and truthful unavailable fields', async () => {
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
  expect(output).toContain('"Serial number",": ","Unavailable"');
  expect(output).toContain('"Hardware",": ","Unavailable"');
  expect(output).not.toContain('Unknown');
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

test('powered-on Home status does not claim a dropped Omi session', () => {
  const snapshot = {
    bluetooth: 'poweredOn',
    phase: 'disconnected',
    capture: 'idle',
    connectedDeviceId: null,
    devices: [{id: 'omi', name: 'Omi', connected: false, rssi: -40}],
    lastEvent: '',
    microphone: 'unknown',
    notifications: 'unknown',
  } as PlatformNativeSnapshot;
  expect(homeConnectionStatus(snapshot).label).toBe('Omi not connected');
  expect(homeConnectionStatus(snapshot).label).not.toBe('Omi disconnected');
  expect(
    homeConnectionStatus({
      ...snapshot,
      lastEvent: 'Bluetooth adapter not checked',
    }).label,
  ).toBe('Omi not connected');
  expect(
    homeConnectionStatus({
      ...snapshot,
      bluetooth: 'poweredOff',
      devices: [],
    }).label,
  ).toBe('Bluetooth off');
  expect(
    homeConnectionStatus({
      ...snapshot,
      bluetooth: 'unknown',
      devices: [],
      lastEvent: 'Bluetooth adapter not checked',
    }).label,
  ).toBe('Checking Bluetooth…');
  expect(
    homeConnectionStatus({
      ...snapshot,
      bluetooth: 'unknown',
      devices: [],
      lastEvent: 'Bluetooth adapter not checked',
    }).color,
  ).toBe('#b4ad9f');
  expect(
    homeConnectionStatus({
      ...snapshot,
      bluetooth: 'unknown',
      devices: [],
      lastEvent: 'Bluetooth is unavailable',
    }).label,
  ).toBe('Bluetooth status unknown');
});

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

test.each(['compact', 'overview', 'affordance'] as const)(
  '%s live capture row says Listening instead of Connected',
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
            audioStatus: 'active',
            connectedDeviceId: 'omi',
            devices: [{id: 'omi', name: 'Omi', connected: true}],
            lastEvent: '',
            microphone: 'unknown',
            notifications: 'unknown',
          }}
        />,
      );
    });
    const output = JSON.stringify(renderer.toJSON());
    expect(output).toContain('Listening');
    expect(output).not.toContain('Connected');
    await act(async () => renderer.unmount());
  },
);

test.each([
  ['Bluetooth is poweredOn', 'No Omi device was discovered.', 'poweredOn'],
  ['Bluetooth is powered on', 'No Omi device was discovered.', 'poweredOn'],
  ['Bluetooth is poweredOff', 'Bluetooth off', 'poweredOff'],
  ['Bluetooth is unauthorized', 'Bluetooth permission needed', 'unauthorized'],
  ['Bluetooth is not powered on', 'Bluetooth off', 'poweredOff'],
  [
    'Bluetooth permission is required',
    'Bluetooth permission needed',
    'unauthorized',
  ],
  ['Bluetooth is unavailable', 'Bluetooth status unknown', 'unknown'],
  ['Bluetooth is unavailable', 'Bluetooth off', 'poweredOff'],
  ['Bluetooth adapter not checked', 'Checking Bluetooth…', 'unknown'],
  ['Bluetooth adapter not checked', 'Bluetooth off', 'poweredOff'],
] as const)(
  'empty device list maps Bluetooth lastEvent %s',
  async (lastEvent, expected, bluetooth) => {
    let renderer!: ReactTestRenderer.ReactTestRenderer;
    await act(async () => {
      renderer = ReactTestRenderer.create(
        <DeviceSession
          nativeSnapshot={
            {
              bluetooth,
              devices: [],
              connectedDeviceId: null,
              capture: 'idle',
              lastEvent,
            } as PlatformNativeSnapshot
          }
          deviceBusy={false}
          deviceScanMessage={null}
          variant="compact"
          onScan={() => {}}
          onToggle={() => {}}
        />,
      );
    });
    const output = JSON.stringify(renderer.toJSON());
    expect(output).toContain(expected);
    expect(output).not.toContain('poweredOn');
    expect(output).not.toContain('poweredOff');
    expect(output).not.toContain('unauthorized');
    expect(output).not.toContain('Bluetooth is not powered on');
    expect(output).not.toContain('Bluetooth permission is required');
    expect(output).not.toContain('Bluetooth is unavailable');
    expect(output).not.toContain('Bluetooth adapter not checked');
    await act(async () => renderer.unmount());
  },
);

test.each([
  ['BLE scan failed: 2', 'Bluetooth scan failed.'],
  ['Omi connection failed: 133', 'Omi connection failed.'],
] as const)(
  'empty device list does not show GATT status %s',
  async (lastEvent, expected) => {
    let renderer!: ReactTestRenderer.ReactTestRenderer;
    await act(async () => {
      renderer = ReactTestRenderer.create(
        <DeviceSession
          nativeSnapshot={
            {
              bluetooth: 'poweredOn',
              devices: [],
              connectedDeviceId: null,
              capture: 'idle',
              lastEvent,
            } as PlatformNativeSnapshot
          }
          deviceBusy={false}
          deviceScanMessage={null}
          variant="compact"
          onScan={() => {}}
          onToggle={() => {}}
        />,
      );
    });
    const output = JSON.stringify(renderer.toJSON());
    expect(output).toContain(expected);
    expect(output).not.toContain('failed: 2');
    expect(output).not.toContain('failed: 133');
    await act(async () => renderer.unmount());
  },
);

test('empty device list does not keep Scanning after the scan is no longer busy', async () => {
  let renderer!: ReactTestRenderer.ReactTestRenderer;
  await act(async () => {
    renderer = ReactTestRenderer.create(
      <DeviceSession
        nativeSnapshot={
          {
            bluetooth: 'poweredOn',
            devices: [],
            connectedDeviceId: null,
            capture: 'idle',
            lastEvent: 'Scanning for Omi devices',
          } as PlatformNativeSnapshot
        }
        deviceBusy={false}
        deviceScanMessage={null}
        variant="compact"
        onScan={() => {}}
        onToggle={() => {}}
      />,
    );
  });
  const output = JSON.stringify(renderer.toJSON());
  expect(output).toContain('No Omi device was discovered.');
  expect(output).not.toContain('Scanning for Omi devices');
  await act(async () => renderer.unmount());
});

test('empty device list keeps Scanning copy while a scan is busy', async () => {
  let renderer!: ReactTestRenderer.ReactTestRenderer;
  await act(async () => {
    renderer = ReactTestRenderer.create(
      <DeviceSession
        nativeSnapshot={
          {
            bluetooth: 'poweredOn',
            devices: [],
            connectedDeviceId: null,
            capture: 'idle',
            lastEvent: 'Scanning for Omi devices',
          } as PlatformNativeSnapshot
        }
        deviceBusy={true}
        deviceScanMessage={null}
        variant="compact"
        onScan={() => {}}
        onToggle={() => {}}
      />,
    );
  });
  expect(JSON.stringify(renderer.toJSON())).toContain(
    'Scanning for Omi devices',
  );
  await act(async () => renderer.unmount());
});

test('empty device list keeps an already-human Bluetooth last event', async () => {
  let renderer!: ReactTestRenderer.ReactTestRenderer;
  await act(async () => {
    renderer = ReactTestRenderer.create(
      <DeviceSession
        nativeSnapshot={
          {
            bluetooth: 'poweredOn',
            devices: [],
            connectedDeviceId: null,
            capture: 'idle',
            lastEvent: 'No Omi devices found',
          } as PlatformNativeSnapshot
        }
        deviceBusy={false}
        deviceScanMessage={null}
        variant="overview"
        onScan={() => {}}
        onToggle={() => {}}
      />,
    );
  });
  const output = JSON.stringify(renderer.toJSON());
  expect(output).toContain('No Omi devices found');
  expect(output).not.toContain('poweredOn');
  await act(async () => renderer.unmount());
});

test('Bluetooth off keeps a dimmed Scan control instead of a live Scan pill', async () => {
  const onScan = jest.fn();
  let renderer!: ReactTestRenderer.ReactTestRenderer;
  await act(async () => {
    renderer = ReactTestRenderer.create(
      <DeviceSession
        nativeSnapshot={
          {
            bluetooth: 'poweredOff',
            devices: [],
            connectedDeviceId: null,
            capture: 'idle',
            lastEvent: '',
          } as PlatformNativeSnapshot
        }
        deviceBusy={false}
        deviceScanMessage={null}
        variant="compact"
        onScan={onScan}
        onToggle={() => {}}
      />,
    );
  });
  const send = renderer.root.find(
    node => node.props.accessibilityLabel === 'Scan for Omi devices',
  );
  expect(send.props.disabled).toBe(true);
  const sendStyle =
    typeof send.props.style === 'function'
      ? send.props.style({pressed: false})
      : send.props.style;
  expect([sendStyle].flat(Infinity)).toEqual(
    expect.arrayContaining([expect.objectContaining({opacity: 0.35})]),
  );
  expect(JSON.stringify(renderer.toJSON())).toContain('Scan');
  send.props.onPress();
  expect(onScan).not.toHaveBeenCalled();
  let live!: ReactTestRenderer.ReactTestRenderer;
  await act(async () => {
    live = ReactTestRenderer.create(
      <DeviceSession
        nativeSnapshot={
          {
            bluetooth: 'poweredOn',
            devices: [],
            connectedDeviceId: null,
            capture: 'idle',
            lastEvent: '',
          } as PlatformNativeSnapshot
        }
        deviceBusy={false}
        deviceScanMessage={null}
        variant="compact"
        onScan={onScan}
        onToggle={() => {}}
      />,
    );
  });
  const liveScan = live.root.find(
    node => node.props.accessibilityLabel === 'Scan for Omi devices',
  );
  expect(liveScan.props.disabled).toBe(false);
  const liveStyle =
    typeof liveScan.props.style === 'function'
      ? liveScan.props.style({pressed: false})
      : liveScan.props.style;
  expect(JSON.stringify([liveStyle].flat(Infinity))).not.toContain(
    '"opacity":0.35',
  );
  await act(async () => {
    renderer.unmount();
    live.unmount();
  });
});

test('Bluetooth off keeps a dimmed Reconnect control and a live Forget control', async () => {
  const onToggle = jest.fn();
  const onForget = jest.fn();
  let renderer!: ReactTestRenderer.ReactTestRenderer;
  await act(async () => {
    renderer = ReactTestRenderer.create(
      <DeviceSession
        nativeSnapshot={
          {
            bluetooth: 'poweredOff',
            devices: [],
            connectedDeviceId: null,
            capture: 'idle',
            lastEvent: '',
          } as PlatformNativeSnapshot
        }
        deviceBusy={false}
        deviceScanMessage={null}
        rememberedDevice={{id: 'saved-id', name: 'My Omi'}}
        onForgetRemembered={onForget}
        variant="compact"
        onScan={() => {}}
        onToggle={onToggle}
      />,
    );
  });
  const reconnect = renderer.root.find(
    node => node.props.accessibilityLabel === 'Reconnect My Omi',
  );
  expect(reconnect.props.disabled).toBe(true);
  const reconnectStyle =
    typeof reconnect.props.style === 'function'
      ? reconnect.props.style({pressed: false})
      : reconnect.props.style;
  expect([reconnectStyle].flat(Infinity)).toEqual(
    expect.arrayContaining([expect.objectContaining({opacity: 0.35})]),
  );
  expect(JSON.stringify(renderer.toJSON())).toContain('Reconnect');
  reconnect.props.onPress();
  expect(onToggle).not.toHaveBeenCalled();
  const forget = renderer.root.find(
    node => node.props.accessibilityLabel === 'Forget My Omi',
  );
  expect(forget.props.disabled).toBe(false);
  const forgetStyle =
    typeof forget.props.style === 'function'
      ? forget.props.style({pressed: false})
      : forget.props.style;
  expect(JSON.stringify([forgetStyle].flat(Infinity))).not.toContain(
    '"opacity":0.35',
  );
  forget.props.onPress();
  expect(onForget).toHaveBeenCalledTimes(1);
  await act(async () => renderer.unmount());
});

test('Bluetooth off keeps a dimmed leftover Connect control and a live Disconnect control', async () => {
  const onToggle = jest.fn();
  let renderer!: ReactTestRenderer.ReactTestRenderer;
  await act(async () => {
    renderer = ReactTestRenderer.create(
      <DeviceSession
        nativeSnapshot={
          {
            bluetooth: 'poweredOff',
            devices: [
              {
                id: 'omi-left',
                name: 'Omi leftover',
                connected: false,
                rssi: -40,
              },
              {id: 'omi-live', name: 'Omi live', connected: true, rssi: -35},
            ],
            connectedDeviceId: 'omi-live',
            capture: 'idle',
            lastEvent: '',
          } as PlatformNativeSnapshot
        }
        deviceBusy={false}
        deviceScanMessage={null}
        variant="compact"
        onScan={() => {}}
        onToggle={onToggle}
      />,
    );
  });
  const connect = renderer.root.find(
    node => node.props.accessibilityLabel === 'Connect Omi leftover',
  );
  expect(connect.props.disabled).toBe(true);
  const connectStyle =
    typeof connect.props.style === 'function'
      ? connect.props.style({pressed: false})
      : connect.props.style;
  expect([connectStyle].flat(Infinity)).toEqual(
    expect.arrayContaining([expect.objectContaining({opacity: 0.35})]),
  );
  expect(JSON.stringify(renderer.toJSON())).toContain('Connect');
  connect.props.onPress();
  expect(onToggle).not.toHaveBeenCalled();
  const disconnect = renderer.root.find(
    node => node.props.accessibilityLabel === 'Disconnect Omi live',
  );
  expect(disconnect.props.disabled).toBe(false);
  const disconnectStyle =
    typeof disconnect.props.style === 'function'
      ? disconnect.props.style({pressed: false})
      : disconnect.props.style;
  expect(JSON.stringify([disconnectStyle].flat(Infinity))).not.toContain(
    '"opacity":0.35',
  );
  disconnect.props.onPress();
  expect(onToggle).toHaveBeenCalledWith('omi-live', true);
  await act(async () => renderer.unmount());
});
