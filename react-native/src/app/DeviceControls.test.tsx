import React from 'react';
import ReactTestRenderer, {act} from 'react-test-renderer';
import {omiNative} from '../omiNative';
import type {Device} from '../omiNativeTypes';
import {FocusPressable} from '../ui/Pressable';
import {DeviceControls} from './DeviceControls';
import {
  batteryLevelCopy,
  chargingCopy,
  findDeviceCopy,
  ledBrightnessCopy,
  micGainCopy,
  micGainLevelCopy,
  deviceStorageCardCopy,
} from '../desktopReadClient';

jest.mock('../omiNative', () => ({
  omiNative: {
    setDeviceSetting: jest.fn(),
    findDevice: jest.fn(),
    readStorageStatus: jest.fn(),
  },
}));
const write = omiNative!.setDeviceSetting as jest.Mock;
const device: Device = {
  id: 'device-a',
  name: 'Omi',
  rssi: -50,
  connected: true,
  features: 384,
  ledBrightness: 50,
  microphoneGain: 8,
};
let renderer: ReactTestRenderer.ReactTestRenderer;
afterEach(async () => {
  await act(async () => renderer?.unmount());
  write.mockReset();
  (omiNative!.findDevice as jest.Mock).mockReset();
  (omiNative!.readStorageStatus as jest.Mock).mockReset();
});
const button = (label: string) =>
  renderer.root
    .findAllByType(FocusPressable)
    .find(item => item.props.accessibilityLabel === label)!;
async function render(value: Device) {
  await act(async () => {
    renderer = ReactTestRenderer.create(
      <DeviceControls key={value.id} device={value} busy={false} />,
    );
  });
}

test('requires reported feature bits and valid observed values before exposing writes', async () => {
  await render({...device, features: undefined});
  expect(renderer.root.findAllByType(FocusPressable)).toHaveLength(0);
  expect(JSON.stringify(renderer.toJSON())).not.toContain(
    `"${chargingCopy()}",":"," ","Unavailable"`,
  );
  expect(JSON.stringify(renderer.toJSON())).not.toContain('Unknown');
  expect(JSON.stringify(renderer.toJSON())).not.toContain('Not charging');
  await act(async () => {
    renderer.update(<DeviceControls device={device} busy={false} />);
  });
  const tree = JSON.stringify(renderer.toJSON());
  expect(tree).toContain(`"${ledBrightnessCopy()}",":"," ","50%"`);
  expect(tree).toContain(`"${micGainCopy()}",":"," ","${micGainLevelCopy(8)}"`);
  expect(tree).not.toContain(`"${micGainCopy()}",":"," ","8"`);
  expect(tree).not.toContain('LED brightness');
  expect(tree).not.toContain('Microphone gain');
  expect(button(`Increase ${micGainCopy().toLowerCase()}`).props.disabled).toBe(
    true,
  );
  expect(button(`Decrease ${micGainCopy().toLowerCase()}`).props.disabled).toBe(
    false,
  );
});

test('connected device omits Flutter DeviceSettings unused LED and Mic rows without feature bits', async () => {
  await render({...device, features: undefined});
  const missing = JSON.stringify(renderer.toJSON());
  expect(missing).not.toContain(`"${ledBrightnessCopy()}"`);
  expect(missing).not.toContain(`"${micGainCopy()}"`);
  await act(async () => {
    renderer.update(
      <DeviceControls device={{...device, features: 0}} busy={false} />,
    );
  });
  const none = JSON.stringify(renderer.toJSON());
  expect(none).not.toContain(`"${ledBrightnessCopy()}"`);
  expect(none).not.toContain(`"${micGainCopy()}"`);
  await act(async () => {
    renderer.update(
      <DeviceControls
        device={{
          ...device,
          features: 384,
          ledBrightness: undefined,
          microphoneGain: undefined,
        }}
        busy={false}
      />,
    );
  });
  const bitsWithoutValue = JSON.stringify(renderer.toJSON());
  expect(bitsWithoutValue).toContain(
    `"${ledBrightnessCopy()}",":"," ","Unavailable"`,
  );
  expect(bitsWithoutValue).toContain(
    `"${micGainCopy()}",":"," ","Unavailable"`,
  );
  await act(async () => {
    renderer.update(<DeviceControls device={device} busy={false} />);
  });
  const present = JSON.stringify(renderer.toJSON());
  expect(present).toContain(`"${ledBrightnessCopy()}",":"," ","50%"`);
  expect(present).toContain(
    `"${micGainCopy()}",":"," ","${micGainLevelCopy(8)}"`,
  );
});

test('connected device names Flutter DeviceSettings mic gain Mute and dB chips', async () => {
  await render({...device, microphoneGain: 0});
  const muted = JSON.stringify(renderer.toJSON());
  expect(muted).toContain(`"${micGainCopy()}",":"," ","${micGainLevelCopy(0)}"`);
  expect(muted).not.toContain(`"${micGainCopy()}",":"," ","0"`);
  await act(async () => {
    renderer.update(
      <DeviceControls
        device={{...device, microphoneGain: 3}}
        busy={false}
      />,
    );
  });
  const neutral = JSON.stringify(renderer.toJSON());
  expect(neutral).toContain(
    `"${micGainCopy()}",":"," ","${micGainLevelCopy(3)}"`,
  );
  expect(neutral).not.toContain(`"${micGainCopy()}",":"," ","3"`);
});

test('connected device names Flutter battery section Charging or Battery Level', async () => {
  await render({...device, battery: 87, charging: true});
  const charging = JSON.stringify(renderer.toJSON());
  expect(charging).toContain(`"${chargingCopy()}"`);
  expect(charging).not.toContain('Not charging');
  expect(charging).not.toContain(`"${batteryLevelCopy()}"`);
  expect(charging).not.toContain(`${chargingCopy()}:`);
  await act(async () => {
    renderer.update(
      <DeviceControls
        device={{...device, battery: 42, charging: false}}
        busy={false}
      />,
    );
  });
  const idle = JSON.stringify(renderer.toJSON());
  expect(idle).toContain(`"${batteryLevelCopy()}"`);
  expect(idle).not.toContain('Not charging');
  expect(idle).not.toContain(`${chargingCopy()}:`);
});

test('connected device names Flutter battery section percent and omits unused Charging Unavailable', async () => {
  await render(device);
  const missing = JSON.stringify(renderer.toJSON());
  expect(missing).not.toContain(
    `"${chargingCopy()}",":"," ","Unavailable"`,
  );
  expect(missing).not.toContain(`"${chargingCopy()}"`);
  expect(missing).not.toContain(`"${batteryLevelCopy()}"`);
  await act(async () => {
    renderer.update(
      <DeviceControls
        device={{...device, battery: 87, charging: true}}
        busy={false}
      />,
    );
  });
  const charging = JSON.stringify(renderer.toJSON());
  expect(charging).toContain(`"${chargingCopy()}"`);
  expect(charging).toContain('"87%"');
  expect(charging).not.toContain(`"${batteryLevelCopy()}"`);
  expect(charging).not.toContain(`${chargingCopy()}:`);
  expect(charging).not.toContain(
    `"${chargingCopy()}",":"," ","Unavailable"`,
  );
  await act(async () => {
    renderer.update(
      <DeviceControls
        device={{...device, battery: 42, charging: false}}
        busy={false}
      />,
    );
  });
  const idle = JSON.stringify(renderer.toJSON());
  expect(idle).toContain(`"${batteryLevelCopy()}"`);
  expect(idle).toContain('"42%"');
  expect(idle).not.toContain(`"${chargingCopy()}"`);
  await act(async () => {
    renderer.update(
      <DeviceControls
        device={{...device, battery: 0, charging: true}}
        busy={false}
      />,
    );
  });
  const zero = JSON.stringify(renderer.toJSON());
  expect(zero).not.toContain(`"${chargingCopy()}"`);
  expect(zero).not.toContain('"0%"');
  await act(async () => {
    renderer.update(
      <DeviceControls
        device={{...device, battery: 64, charging: undefined}}
        busy={false}
      />,
    );
  });
  const unknown = JSON.stringify(renderer.toJSON());
  expect(unknown).toContain(`"${batteryLevelCopy()}"`);
  expect(unknown).toContain('"64%"');
  expect(unknown).not.toContain(
    `"${chargingCopy()}",":"," ","Unavailable"`,
  );
});

test('serializes writes and waits for matching native read-back without optimistic values', async () => {
  let resolve!: (value: number) => void;
  write.mockReturnValue(
    new Promise<number>(done => {
      resolve = done;
    }),
  );
  await render(device);
  await act(async () => {
    const press = button('Increase led brightness').props.onPress;
    press();
    press();
  });
  expect(write).toHaveBeenCalledTimes(1);
  expect(write).toHaveBeenCalledWith('device-a', 'ledBrightness', 60);
  expect(JSON.stringify(renderer.toJSON())).toContain('50%');
  expect(JSON.stringify(renderer.toJSON())).not.toContain(
    'Confirmed on device',
  );
  await act(async () => resolve(60));
  expect(JSON.stringify(renderer.toJSON())).toContain('Confirmed on device');
});

test.each([false, true])(
  'failed or mismatched native acknowledgment remains an error (%s)',
  async reject => {
    write.mockImplementation(() =>
      reject ? Promise.reject(new Error('disconnected')) : Promise.resolve(7),
    );
    await render(device);
    await act(async () => button('Increase led brightness').props.onPress());
    expect(JSON.stringify(renderer.toJSON())).toContain(
      'Could not confirm the change',
    );
    expect(JSON.stringify(renderer.toJSON())).not.toContain(
      'Confirmed on device',
    );
  },
);

test('completion from a replaced device does not report success for the next device', async () => {
  let resolve!: (value: number) => void;
  write.mockReturnValue(
    new Promise<number>(done => {
      resolve = done;
    }),
  );
  await render(device);
  await act(async () => button('Increase led brightness').props.onPress());
  await act(async () =>
    renderer.update(
      <DeviceControls
        key="device-b"
        device={{...device, id: 'device-b'}}
        busy={false}
      />,
    ),
  );
  await act(async () => resolve(60));
  expect(JSON.stringify(renderer.toJSON())).not.toContain(
    'Confirmed on device',
  );
  expect(button('Increase led brightness').props.disabled).toBe(false);
});

test('find requires discovered support, serializes commands and reports only acknowledgement', async () => {
  let resolve!: () => void;
  const find = omiNative!.findDevice as jest.Mock;
  find.mockReturnValue(
    new Promise<void>(done => {
      resolve = done;
    }),
  );
  await render(device);
  expect(button(findDeviceCopy())).toBeUndefined();
  await act(async () =>
    renderer.update(
      <DeviceControls
        device={{...device, findDeviceSupported: true}}
        busy={false}
      />,
    ),
  );
  await act(async () => {
    button(findDeviceCopy()).props.onPress();
    button(findDeviceCopy()).props.onPress();
  });
  expect(find).toHaveBeenCalledTimes(1);
  expect(find).toHaveBeenCalledWith(device.id);
  expect(button('Increase led brightness').props.disabled).toBe(true);
  expect(JSON.stringify(renderer.toJSON())).not.toContain(
    'commands acknowledged',
  );
  await act(async () => resolve());
  expect(JSON.stringify(renderer.toJSON())).toContain('commands acknowledged');
});

test('find failure remains retryable without claiming physical vibration', async () => {
  (omiNative!.findDevice as jest.Mock).mockRejectedValue(
    new Error('disconnected'),
  );
  await render({...device, findDeviceSupported: true});
  await act(async () => button(findDeviceCopy()).props.onPress());
  expect(JSON.stringify(renderer.toJSON())).toContain(
    'Could not send all find device commands',
  );
  expect(button(findDeviceCopy()).props.disabled).toBe(false);
});

test('storage read is capability gated and shows only acknowledged values', async () => {
  await render(device);
  expect(button('Read storage status')).toBeUndefined();
  const read = omiNative!.readStorageStatus as jest.Mock;
  let resolve!: (value: unknown) => void;
  read.mockReturnValue(
    new Promise(done => {
      resolve = done;
    }),
  );
  await act(async () =>
    renderer.update(
      <DeviceControls
        device={{...device, storageStatusSupported: true}}
        busy={false}
      />,
    ),
  );
  await act(async () => {
    button('Read storage status').props.onPress();
    button('Read storage status').props.onPress();
  });
  expect(read).toHaveBeenCalledTimes(1);
  expect(read).toHaveBeenCalledWith(device.id);
  expect(button('Increase led brightness').props.disabled).toBe(true);
  expect(JSON.stringify(renderer.toJSON())).not.toContain('Stored audio:');
  expect(JSON.stringify(renderer.toJSON())).not.toContain('Device Storage');
  await act(async () =>
    resolve({
      usedBytes: 4096,
      unreadPackets: 256,
      freeBytes: 8192,
      clockValid: false,
    }),
  );
  const loaded = JSON.stringify(renderer.toJSON());
  for (const line of deviceStorageCardCopy({
    usedBytes: 4096,
    freeBytes: 8192,
  })) {
    expect(loaded).toContain(line);
  }
  expect(loaded).not.toContain('Stored audio');
  expect(loaded).not.toContain('Unread packets');
  expect(loaded).not.toContain('Last reported storage');
  expect(loaded).not.toContain('Not set');
  expect(loaded).not.toContain('256');
});

test('storage read failure remains unknown and can be retried', async () => {
  (omiNative!.readStorageStatus as jest.Mock).mockRejectedValue(
    new Error('legacy format'),
  );
  await render({...device, storageStatusSupported: true});
  await act(async () => button('Read storage status').props.onPress());
  expect(JSON.stringify(renderer.toJSON())).toContain(
    'Storage status could not be read',
  );
  expect(JSON.stringify(renderer.toJSON())).not.toContain('Stored audio:');
  expect(button('Read storage status').props.disabled).toBe(false);
});

test('connected device omits Flutter DeviceSettings unused Find-unavailable copy', async () => {
  await render(device);
  expect(JSON.stringify(renderer.toJSON())).not.toContain(
    'Find device unavailable',
  );
  expect(button(findDeviceCopy())).toBeUndefined();
  await act(async () =>
    renderer.update(
      <DeviceControls
        device={{...device, findDeviceSupported: true}}
        busy={false}
      />,
    ),
  );
  expect(JSON.stringify(renderer.toJSON())).toContain(`"${findDeviceCopy()}"`);
  expect(JSON.stringify(renderer.toJSON())).not.toContain(
    'Find device unavailable',
  );
  await act(async () =>
    renderer.update(
      <DeviceControls
        device={{...device, connected: false, findDeviceSupported: true}}
        busy={false}
      />,
    ),
  );
  expect(JSON.stringify(renderer.toJSON())).not.toContain(
    'Find device unavailable',
  );
  expect(button(findDeviceCopy())).toBeUndefined();
});

test('connected device omits Flutter DeviceSettings unused storage-unavailable copy', async () => {
  await render(device);
  expect(JSON.stringify(renderer.toJSON())).not.toContain(
    'Storage status unavailable',
  );
  expect(button('Read storage status')).toBeUndefined();
  await act(async () =>
    renderer.update(
      <DeviceControls
        device={{...device, storageStatusSupported: true}}
        busy={false}
      />,
    ),
  );
  expect(JSON.stringify(renderer.toJSON())).toContain('Read storage status');
  expect(JSON.stringify(renderer.toJSON())).not.toContain(
    'Storage status unavailable',
  );
  await act(async () =>
    renderer.update(
      <DeviceControls
        device={{
          ...device,
          connected: false,
          storageStatusSupported: true,
        }}
        busy={false}
      />,
    ),
  );
  expect(JSON.stringify(renderer.toJSON())).not.toContain(
    'Storage status unavailable',
  );
  expect(button('Read storage status')).toBeUndefined();
});

test('connected device omits Flutter DeviceSettings unused Double-press copy', async () => {
  await render({...device, buttonSupported: true});
  expect(JSON.stringify(renderer.toJSON())).not.toContain(
    'Double-press to save this conversation and keep recording.',
  );
  expect(JSON.stringify(renderer.toJSON())).not.toContain('Double-press');
  expect(JSON.stringify(renderer.toJSON())).not.toContain('Double Tap');
  await act(async () =>
    renderer.update(
      <DeviceControls
        device={{...device, buttonSupported: false}}
        busy={false}
      />,
    ),
  );
  expect(JSON.stringify(renderer.toJSON())).not.toContain('Double-press');
  await act(async () =>
    renderer.update(
      <DeviceControls
        device={{...device, connected: false, buttonSupported: true}}
        busy={false}
      />,
    ),
  );
  expect(JSON.stringify(renderer.toJSON())).not.toContain('Double-press');
});
