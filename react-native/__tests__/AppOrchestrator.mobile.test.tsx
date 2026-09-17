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

test.each([['Settings', 'Settings stage']])(
  'mobile %s opens its real destination and can return home',
  async (label, stage) => {
    const renderer = await renderApp();
    await act(async () => {
      control(renderer, label).props.onPress();
    });
    expect(control(renderer, stage)).toBeDefined();
    await act(async () => control(renderer, 'Home').props.onPress());
    expect(control(renderer, 'Ask Omi')).toBeDefined();
  },
);

test('saved memories appear in matching Search results, not as a Home shortcut', async () => {
  const readsModule: typeof import('../src/app/useDesktopReads') = require('../src/app/useDesktopReads');
  const realReads = readsModule.useDesktopReads;
  const memory: import('../src/desktopReadClient').MemoryProjection = {
    kind: 'memory',
    id: 'workspace',
    title: 'Quiet workspace',
    summary: '',
    searchableText: 'Quiet workspace',
    citations: [],
    timestamp: null,
    provenance: {
      label: null,
      synthesisVersion: null,
      inputDigest: null,
      outputDigest: null,
    },
  };
  const spy = jest
    .spyOn(readsModule, 'useDesktopReads')
    .mockImplementation(options => ({
      ...realReads(options),
      readsPhase: 'ready',
      reads: [
        memory,
        {
          ...memory,
          id: 'walk',
          title: 'Afternoon walk',
          searchableText: 'Afternoon walk',
        },
      ],
    }));
  try {
    const renderer = await renderApp();
    const {ProjectionList} = require('../src/ui/ProjectionList');
    expect(control(renderer, 'Saved memories')).toBeUndefined();
    expect(control(renderer, 'Search results')).toBeUndefined();
    await act(async () => control(renderer, 'Search mode').props.onPress());
    await act(async () =>
      control(renderer, 'Search loaded data').props.onChangeText(' WORKSPACE '),
    );
    const results = () => renderer.root.findByType(ProjectionList).props.items;
    expect(results().map((item: {id: string}) => item.id)).toEqual([
      'workspace',
    ]);
    await act(async () =>
      control(renderer, 'Search loaded data').props.onChangeText('no match'),
    );
    expect(results()).toEqual([]);
    await act(async () => control(renderer, 'Clear search').props.onPress());
    expect(control(renderer, 'Search results')).toBeUndefined();
    expect(control(renderer, 'Saved memories')).toBeUndefined();
  } finally {
    spy.mockRestore();
  }
});

test('action items open from Home or the restored Tasks tab', async () => {
  const renderer = await renderApp();
  expect(control(renderer, 'Tasks')).toBeDefined();
  expect(control(renderer, 'Open calls')).toBeUndefined();
  expect(control(renderer, 'Start Live voice')).toBeUndefined();
  await act(async () =>
    control(renderer, 'See all action items').props.onPress(),
  );
  expect(control(renderer, 'Tasks').props.accessibilityState.selected).toBe(
    true,
  );
  expect(control(renderer, 'Start Live voice')).toBeUndefined();
  await act(async () => control(renderer, 'Home').props.onPress());
  expect(control(renderer, 'See all action items')).toBeDefined();
  expect(control(renderer, 'Start Live voice')).toBeUndefined();
  await act(async () => control(renderer, 'Tasks').props.onPress());
  expect(control(renderer, 'Tasks').props.accessibilityState.selected).toBe(
    true,
  );
});

test('mobile Ask Omi opens the actual chat and reports a missing backend', async () => {
  const renderer = await renderApp();
  const connections = mockNative.connectDevice.mock.calls.length;
  const disconnections = mockNative.disconnectDevice.mock.calls.length;
  const input = control(renderer, 'Ask Omi');
  await act(async () => {
    renderer.root
      .findAllByType(TextInput)
      .find(node => node.props.accessibilityLabel === 'Ask Omi')!
      .props.onChangeText('Hello Omi');
  });
  await act(async () => control(renderer, 'Ask Omi').props.onSubmitEditing());
  expect(control(renderer, 'Chat scroll region')).toBeDefined();
  expect(control(renderer, 'Start Live voice')).toBeUndefined();
  expect(control(renderer, 'Open calls')).toBeUndefined();
  expect(control(renderer, 'Ask Omi')).toBe(input);
  expect(JSON.stringify(renderer.toJSON())).toContain('Chat');
  await act(async () => control(renderer, 'Close chat').props.onPress());
  expect(control(renderer, 'Open Omi device')).toBeDefined();
  expect(control(renderer, 'Ask Omi').props.value).toBe('Hello Omi');
  expect(control(renderer, 'Ask Omi')).toBe(input);
  expect(mockNative.connectDevice).toHaveBeenCalledTimes(connections);
  expect(mockNative.disconnectDevice).toHaveBeenCalledTimes(disconnections);
});

test('bottom Ask returns to the previous page; Search uses the shared draft without opening chat', async () => {
  const renderer = await renderApp();
  await act(async () => control(renderer, 'Conversations').props.onPress());
  const input = control(renderer, 'Ask Omi');
  await act(async () => input.props.onChangeText('Workspace ideas'));
  await act(async () => control(renderer, 'Search mode').props.onPress());
  expect(control(renderer, 'Search loaded data').props.value).toBe(
    'Workspace ideas',
  );
  expect(control(renderer, 'Chat scroll region')).toBeUndefined();
  expect(control(renderer, 'Search loaded conversations')).toBeUndefined();
  await act(async () => control(renderer, 'Ask mode').props.onPress());
  await act(async () => control(renderer, 'Send to Omi').props.onPress());
  expect(control(renderer, 'Chat scroll region')).toBeDefined();
  await act(async () => control(renderer, 'Close chat').props.onPress());
  expect(
    control(renderer, 'Conversations').props.accessibilityState.selected,
  ).toBe(true);
  expect(control(renderer, 'Ask Omi').props.value).toBe('Workspace ideas');
  await act(async () => control(renderer, 'Search mode').props.onPress());
  await act(async () =>
    control(renderer, 'Search loaded data').props.onSubmitEditing(),
  );
  expect(control(renderer, 'Search results')).toBeDefined();
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

test('Settings remains a selected bottom destination and keeps Apps reachable', async () => {
  const renderer = await renderApp();
  expect(control(renderer, 'Apps')).toBeUndefined();
  expect(control(renderer, 'Open apps')).toBeUndefined();
  await act(async () => control(renderer, 'Settings').props.onPress());
  expect(control(renderer, 'Settings stage')).toBeDefined();
  expect(control(renderer, 'Open settings')).toBeUndefined();
  expect(control(renderer, 'Settings').props.accessibilityState.selected).toBe(
    true,
  );
  expect(control(renderer, 'Account settings')).toBeDefined();
  await act(async () => control(renderer, 'Open apps').props.onPress());
  expect(control(renderer, 'Connectors stage')).toBeDefined();
  expect(control(renderer, 'Settings').props.accessibilityState.selected).toBe(
    true,
  );
  await act(async () => control(renderer, 'Back to Settings').props.onPress());
  expect(control(renderer, 'Settings stage')).toBeDefined();
  expect(control(renderer, 'Open apps')).toBeDefined();
  await act(async () => control(renderer, 'Home').props.onPress());
  expect(control(renderer, 'Ask Omi')).toBeDefined();
});
