import React from 'react';
import ReactTestRenderer, {act} from 'react-test-renderer';
import {Platform, TextInput} from 'react-native';

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
  requestPermissions: jest.fn(async () => ({
    microphone: 'denied',
    notifications: 'denied',
  })),
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

async function finishMobileSetup(
  renderer: ReactTestRenderer.ReactTestRenderer,
) {
  const press = async (label: string) => {
    await act(async () => control(renderer, label).props.onPress());
  };
  await press('Agree & Continue');
  await act(async () => {
    renderer.root
      .findAllByType(TextInput)
      .find(node => node.props.accessibilityLabel === 'Enter your name')!
      .props.onChangeText('Sam');
  });
  await press('Continue');
  await press('Continue');
  await press('TikTok');
  await press('Continue');
  await press("I'll do these later");
  await press('Skip for now');
  await press('Continue');
}

afterEach(() => {
  act(() => renderers.splice(0).forEach(renderer => renderer.unmount()));
});

test('mobile settings opens from the top chrome and can return home', async () => {
  const renderer = await renderApp();
  await act(async () => control(renderer, 'Settings').props.onPress());
  expect(control(renderer, 'Settings stage')).toBeDefined();
  await act(async () => control(renderer, 'Back to Home').props.onPress());
  expect(control(renderer, 'Search loaded data')).toBeDefined();
});

test('mobile Ask Omi opens the actual chat and reports a missing backend', async () => {
  const renderer = await renderApp();
  const connections = mockNative.connectDevice.mock.calls.length;
  const disconnections = mockNative.disconnectDevice.mock.calls.length;
  await act(async () => control(renderer, 'Ask mode').props.onPress());
  const input = control(renderer, 'Ask Omi');
  expect(control(renderer, 'Start Live voice')).toBeUndefined();
  expect(control(renderer, 'End Live voice')).toBeUndefined();
  await act(async () => {
    renderer.root
      .findAllByType(TextInput)
      .find(node => node.props.accessibilityLabel === 'Ask Omi')!
      .props.onChangeText('Hello Omi');
  });
  await act(async () => control(renderer, 'Ask Omi').props.onSubmitEditing());
  expect(control(renderer, 'Chat scroll region')).toBeDefined();
  expect(control(renderer, 'Start Live voice')).toBeUndefined();
  expect(control(renderer, 'End Live voice')).toBeUndefined();
  expect(control(renderer, 'Ask Omi')).toBe(input);
  expect(control(renderer, 'Compact chat response')).toBeDefined();
  expect(control(renderer, 'Expand response')).toBeUndefined();
  expect(control(renderer, 'Start Live voice')).toBeUndefined();
  expect(control(renderer, 'End Live voice')).toBeUndefined();
  await act(async () => control(renderer, 'Close chat').props.onPress());
  expect(control(renderer, 'Open Omi device')).toBeDefined();
  expect(control(renderer, 'Ask Omi').props.value).toBe('Hello Omi');
  expect(control(renderer, 'Ask Omi')).toBe(input);
  expect(mockNative.connectDevice).toHaveBeenCalledTimes(connections);
  expect(mockNative.disconnectDevice).toHaveBeenCalledTimes(disconnections);
});

test('Search is the default and Ask/Search use one shared draft without tabs', async () => {
  const renderer = await renderApp();
  const input = control(renderer, 'Search loaded data');
  await act(async () => input.props.onChangeText('Workspace ideas'));
  expect(
    control(renderer, 'Search mode').props.accessibilityState.selected,
  ).toBe(true);
  await act(async () => control(renderer, 'Ask mode').props.onPress());
  expect(control(renderer, 'Ask Omi').props.value).toBe('Workspace ideas');
  expect(control(renderer, 'Chat scroll region')).toBeUndefined();
  await act(async () => control(renderer, 'Search mode').props.onPress());
  expect(control(renderer, 'Search loaded data').props.value).toBe(
    'Workspace ideas',
  );
  expect(control(renderer, 'Chat scroll region')).toBeUndefined();
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

test.each(['ios', 'android'] as const)(
  'signed-out %s waits for the real sign-in before showing the app',
  async platform => {
    const originalPlatform = Platform.OS;
    Object.defineProperty(Platform, 'OS', {
      configurable: true,
      value: platform,
    });
    try {
      mockAuth.hasCloudSession.mockResolvedValueOnce(false);
      const renderer = await renderApp();
      expect(control(renderer, 'First-run onboarding')).toBeDefined();
      expect(control(renderer, 'Open Omi device')).toBeUndefined();
      await act(async () => control(renderer, 'Sign in').props.onPress());
      expect(mockAuth.signIn).toHaveBeenCalled();
      expect(control(renderer, 'Open Omi device')).toBeDefined();
    } finally {
      Object.defineProperty(Platform, 'OS', {
        configurable: true,
        value: originalPlatform,
      });
    }
  },
);

test.each([true, false])(
  'unfinished mobile setup hands off device connection only after consent: %s',
  async connect => {
    mockAuth.hasCompletedOnboarding.mockResolvedValue(false);
    mockNative.getSnapshot.mockClear();
    mockNative.startScan.mockClear();
    mockNative.connectDevice.mockClear();
    try {
      const renderer = await renderApp();
      expect(control(renderer, 'First-run onboarding')).toBeDefined();
      expect(mockNative.getSnapshot).not.toHaveBeenCalled();
      expect(mockNative.startScan).not.toHaveBeenCalled();
      expect(mockNative.connectDevice).not.toHaveBeenCalled();
      await finishMobileSetup(renderer);
      await act(async () =>
        control(
          renderer,
          connect
            ? 'Agree and connect Omi'
            : 'Agree and continue without a device',
        ).props.onPress(),
      );
      expect(control(renderer, 'First-run onboarding')).toBeUndefined();
      expect(mockAuth.markOnboardingComplete).toHaveBeenCalled();
      expect(Boolean(control(renderer, 'Scan for Omi devices'))).toBe(connect);
      expect(mockNative.startScan).not.toHaveBeenCalled();
      expect(mockNative.connectDevice).not.toHaveBeenCalled();
    } finally {
      mockAuth.hasCompletedOnboarding.mockResolvedValue(true);
    }
  },
);

test('Settings remains a selected top destination and returns to the one-page timeline', async () => {
  const renderer = await renderApp();
  await act(async () => control(renderer, 'Settings').props.onPress());
  expect(control(renderer, 'Settings stage')).toBeDefined();
  expect(control(renderer, 'Open settings')).toBeUndefined();
  expect(control(renderer, 'Settings').props.accessibilityState.selected).toBe(
    true,
  );
  expect(control(renderer, 'Account settings')).toBeDefined();
  await act(async () => control(renderer, 'Back to Home').props.onPress());
  expect(control(renderer, 'Search loaded data')).toBeDefined();
});
