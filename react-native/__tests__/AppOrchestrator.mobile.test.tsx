import React from 'react';
import ReactTestRenderer, {act} from 'react-test-renderer';
import {Platform} from 'react-native';

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
  ['View All Mind Map', 'Memories stage'],
  ['Apps', 'Connectors stage'],
])(
  'mobile %s opens its real destination and can return home',
  async (label, stage) => {
    const renderer = await renderApp();
    await act(async () => {
      control(renderer, label).props.onPress();
    });
    expect(control(renderer, stage)).toBeDefined();
    await act(async () =>
      control(
        renderer,
        label === 'View All Mind Map' ? 'Back to Home' : 'Home',
      ).props.onPress(),
    );
    expect(control(renderer, 'Ask Omi')).toBeDefined();
  },
);

test('mobile Ask Omi stays unavailable without a backend', async () => {
  const renderer = await renderApp();
  expect(control(renderer, 'Send to Omi unavailable')).toBeDefined();
  const ask = control(renderer, 'Ask Omi');
  expect(ask.props.editable).toBe(false);
  expect(ask.props.placeholder).toBe(
    'Sending messages is not available on this backend yet.',
  );
  expect(ask.props.onSubmitEditing).toBeUndefined();
});

test('compact Home does not claim Omi disconnected when nothing is connected', async () => {
  const renderer = await renderApp();
  const tree = JSON.stringify(renderer.toJSON());
  expect(tree).toContain('Omi not connected');
  expect(tree).not.toContain('Omi disconnected');
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

test('Settings remains a selected bottom destination and keeps Apps reachable', async () => {
  const renderer = await renderApp();
  await act(async () => control(renderer, 'Settings').props.onPress());
  expect(control(renderer, 'Settings stage')).toBeDefined();
  expect(control(renderer, 'Open settings')).toBeUndefined();
  expect(control(renderer, 'Settings').props.accessibilityState.selected).toBe(
    true,
  );
  expect(control(renderer, 'Account settings')).toBeDefined();
  await act(async () => control(renderer, 'Apps').props.onPress());
  expect(control(renderer, 'Connectors stage')).toBeDefined();
  expect(control(renderer, 'Apps').props.accessibilityState.selected).toBe(
    true,
  );
  await act(async () => control(renderer, 'Home').props.onPress());
  expect(control(renderer, 'Ask Omi')).toBeDefined();
});
