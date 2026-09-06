import React from 'react';
import ReactTestRenderer, {act} from 'react-test-renderer';
import {TextInput} from 'react-native';

const mockDevice = {id: 'omi-1', name: 'Test Omi', rssi: -50, connected: false};
const mockNative = {
  getSnapshot: jest.fn(async () => ({
    bluetooth: 'poweredOn',
    devices: [mockDevice],
    connectedDeviceId: null,
    phase: 'disconnected',
    capture: 'idle',
    lastEvent: '',
    microphone: 'unknown',
    notifications: 'unknown',
  })),
  startScan: jest.fn(async () => [mockDevice]),
  connectDevice: jest.fn(async () => undefined),
  disconnectDevice: jest.fn(async () => undefined),
};

const mockAuth = {
  hasCloudSession: jest.fn(async () => true),
  hasCompletedOnboarding: jest.fn(async () => true),
  markOnboardingComplete: jest.fn(async () => undefined),
  signIn: jest.fn(async () => ({signedIn: true})),
};

jest.mock('../src/omiNative', () => ({
  omiAuth: mockAuth,
  omiBackend: null,
  omiNative: mockNative,
  requestBluetoothScanPermission: async () => true,
  isBluetoothScanAvailable: (state: string) => state === 'poweredOn',
  browserScanErrorMessage: () => null,
  subscribeOmiBackendSessionInvalidated: () => () => undefined,
  subscribeOmiNativeEvents: () => () => undefined,
}));
jest.mock('../src/app/useReduceMotion', () => ({useReduceMotion: () => true}));

const App = require('../src/app/AppOrchestrator').default;
const renderers: ReactTestRenderer.ReactTestRenderer[] = [];

async function renderApp() {
  let renderer!: ReactTestRenderer.ReactTestRenderer;
  await act(async () => {
    renderer = ReactTestRenderer.create(<App />);
  });
  renderers.push(renderer);
  return renderer;
}

function control(renderer: ReactTestRenderer.ReactTestRenderer, label: string) {
  return renderer.root.findAll(
    node => node.props.accessibilityLabel === label,
  )[0];
}

afterEach(() => {
  act(() => renderers.splice(0).forEach(renderer => renderer.unmount()));
});

test.each([
  ['Open settings', 'Settings stage'],
  ['Expand', 'Memories stage'],
  ['Apps', 'Connectors stage'],
])(
  'mobile %s opens its real destination and can return home',
  async (label, stage) => {
    const renderer = await renderApp();
    await act(async () => {
      if (label === 'Expand') {
        const expand = renderer.root.findAll(
          node => node.props.children === 'Expand',
        )[0];
        let button = expand.parent;
        while (button && typeof button.props.onPress !== 'function') {
          button = button.parent;
        }
        button!.props.onPress();
      } else {
        control(renderer, label).props.onPress();
      }
    });
    expect(control(renderer, stage)).toBeDefined();
    await act(async () => control(renderer, 'Back to Home').props.onPress());
    expect(control(renderer, 'Ask Omi')).toBeDefined();
  },
);

test('mobile Ask Omi opens the actual chat and reports a missing backend', async () => {
  const renderer = await renderApp();
  await act(async () => {
    renderer.root
      .findAllByType(TextInput)
      .find(node => node.props.accessibilityLabel === 'Ask Omi')!
      .props.onChangeText('Hello Omi');
  });
  await act(async () => control(renderer, 'Ask Omi').props.onSubmitEditing());
  expect(control(renderer, 'Chat scroll region')).toBeDefined();
  expect(JSON.stringify(renderer.toJSON())).toContain('Chat');
});

test('mobile device panel exposes the existing scan and connection controls', async () => {
  mockNative.startScan.mockClear();
  mockNative.connectDevice.mockClear();
  const renderer = await renderApp();
  expect(control(renderer, 'Scan for Omi devices')).toBeUndefined();
  await act(async () => control(renderer, 'Open Omi device').props.onPress());
  expect(
    control(renderer, 'Open Omi device').props.accessibilityState.expanded,
  ).toBe(true);
  await act(async () =>
    control(renderer, 'Scan for Omi devices').props.onPress(),
  );
  expect(mockNative.startScan).toHaveBeenCalledWith(8);
  await act(async () => control(renderer, 'Connect Test Omi').props.onPress());
  expect(mockNative.connectDevice).toHaveBeenCalledWith('omi-1');
  await act(async () => control(renderer, 'Open Omi device').props.onPress());
  expect(control(renderer, 'Scan for Omi devices')).toBeUndefined();
});

test('signed-out iOS waits for the real sign-in before showing the app', async () => {
  mockAuth.hasCloudSession.mockResolvedValueOnce(false);
  const renderer = await renderApp();
  expect(control(renderer, 'First-run onboarding')).toBeDefined();
  expect(control(renderer, 'Open Omi device')).toBeUndefined();
  await act(async () => control(renderer, 'Sign in').props.onPress());
  expect(mockAuth.signIn).toHaveBeenCalled();
  expect(control(renderer, 'Open Omi device')).toBeDefined();
});
