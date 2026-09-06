import React from 'react';
import ReactTestRenderer, {act} from 'react-test-renderer';
import {omiNative} from '../omiNative';
import type {Device} from '../omiNativeTypes';
import {FocusPressable} from '../ui/Pressable';
import {DeviceControls} from './DeviceControls';

jest.mock('../omiNative', () => ({
  omiNative: {setDeviceSetting: jest.fn(), findDevice: jest.fn()},
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
  expect(JSON.stringify(renderer.toJSON())).toContain('Unknown');
  await act(async () => {
    renderer.update(<DeviceControls device={device} busy={false} />);
  });
  expect(button('Increase microphone gain').props.disabled).toBe(true);
  expect(button('Decrease microphone gain').props.disabled).toBe(false);
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
  expect(button('Find device')).toBeUndefined();
  await act(async () =>
    renderer.update(
      <DeviceControls
        device={{...device, findDeviceSupported: true}}
        busy={false}
      />,
    ),
  );
  await act(async () => {
    button('Find device').props.onPress();
    button('Find device').props.onPress();
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
  await act(async () => button('Find device').props.onPress());
  expect(JSON.stringify(renderer.toJSON())).toContain(
    'Could not send all find device commands',
  );
  expect(button('Find device').props.disabled).toBe(false);
});
