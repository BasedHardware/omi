import React from 'react';
import ReactTestRenderer, {act} from 'react-test-renderer';
import {Linking, Platform, Text} from 'react-native';

const mockAuth = {
  hasCloudSession: jest.fn(),
  hasCompletedOnboarding: jest.fn(),
  markOnboardingComplete: jest.fn(async () => undefined),
  signIn: jest.fn(),
  signOut: jest.fn(),
};
const mockBackend = {
  request: jest.fn(),
  generationEvents: jest.fn(),
  cancelGenerationEvents: jest.fn(async () => undefined),
};

jest.mock('../omiNative', () => ({
  omiAuth: mockAuth,
  omiBackend: mockBackend,
}));

const {ConnectorsPage} = require('./Connectors');
const {SettingsPage} = require('./Settings');

function textOf(renderer: ReactTestRenderer.ReactTestRenderer): string {
  return renderer.root
    .findAllByType(Text)
    .flatMap(node =>
      Array.isArray(node.props.children)
        ? node.props.children
        : [node.props.children],
    )
    .filter(
      (value): value is string | number =>
        typeof value === 'string' || typeof value === 'number',
    )
    .join(' ');
}

function labelsOf(renderer: ReactTestRenderer.ReactTestRenderer): string[] {
  return renderer.root
    .findAll(node => typeof node.props.accessibilityLabel === 'string')
    .map(node => node.props.accessibilityLabel);
}

const renderers: ReactTestRenderer.ReactTestRenderer[] = [];

afterEach(() => {
  act(() => {
    renderers.splice(0).forEach(renderer => renderer.unmount());
  });
  mockAuth.hasCloudSession.mockReset();
  mockBackend.request.mockReset();
});

async function renderPage(Page: typeof ConnectorsPage) {
  let renderer: ReactTestRenderer.ReactTestRenderer;
  await act(async () => {
    renderer = ReactTestRenderer.create(<Page onSignIn={jest.fn()} />);
  });
  renderers.push(renderer!);
  return renderer!;
}

test('a rejected session probe keeps apps retryable instead of loading forever', async () => {
  mockAuth.hasCloudSession.mockRejectedValue(
    Object.assign(new Error('Omi cloud session could not be refreshed'), {
      code: 'OMI_AUTH_TRANSPORT',
    }),
  );
  const renderer = await renderPage(ConnectorsPage);
  const tree = textOf(renderer);
  expect(tree).toContain('Apps unavailable');
  expect(tree).toContain(
    'The selected Omi service is unavailable. Check the connection, then retry.',
  );
  expect(tree).toContain('Retry');
  expect(tree).not.toContain('Loading apps…');
  expect(tree).not.toContain('Signed out');
  // Retry re-probes the session instead of stranding the loading spinner.
  mockAuth.hasCloudSession.mockResolvedValue(true);
  mockBackend.request.mockResolvedValue({id: 'apps', status: 200, body: '[]'});
  await act(async () => {
    renderer.root
      .find(node => node.props.accessibilityLabel === 'Retry apps')
      .props.onPress();
  });
  expect(mockAuth.hasCloudSession).toHaveBeenCalledTimes(2);
});

test('a rejected session probe keeps settings retryable instead of loading forever', async () => {
  mockAuth.hasCloudSession.mockRejectedValue(
    Object.assign(new Error('Omi cloud session could not be refreshed'), {
      code: 'OMI_AUTH_TRANSPORT',
    }),
  );
  const renderer = await renderPage(SettingsPage);
  const tree = textOf(renderer);
  expect(tree).toContain(
    'The selected Omi service is unavailable. Check the connection, then retry.',
  );
  expect(labelsOf(renderer)).toContain('Retry settings');
  expect(tree).not.toContain('Loading account…');
});

test('a signed-out session still offers the native sign-in', async () => {
  mockAuth.hasCloudSession.mockResolvedValue(false);
  const connectors = await renderPage(ConnectorsPage);
  expect(textOf(connectors)).toContain('Signed out');
  expect(textOf(connectors)).toContain('Omi cloud needs a signed-in session.');
  expect(labelsOf(connectors)).toContain('Sign in');
});

test('web Settings loads real service usage without offering a fake sign-in', async () => {
  const originalPlatform = Platform.OS;
  Object.defineProperty(Platform, 'OS', {configurable: true, value: 'web'});
  mockBackend.request.mockResolvedValue({
    id: 'service-settings-read',
    status: 200,
    body: JSON.stringify({
      identity: {displayName: 'Local QA identity', email: ''},
      entitlement: {limitKey: 'chat', used: 7, limit: 100},
    }),
  });
  try {
    const renderer = await renderPage(SettingsPage);
    expect(mockAuth.hasCloudSession).not.toHaveBeenCalled();
    expect(mockBackend.request).toHaveBeenCalledWith({
      id: 'service-settings-read',
      method: 'GET',
      path: '/v1/settings',
    });
    expect(textOf(renderer)).toContain('7 of 100 requests used');
    expect(textOf(renderer)).toContain('Local QA identity');
    expect(labelsOf(renderer)).not.toContain('Sign in');
    expect(labelsOf(renderer)).not.toContain('Open app permissions');
  } finally {
    Object.defineProperty(Platform, 'OS', {
      configurable: true,
      value: originalPlatform,
    });
  }
});

test('Settings exposes real native app permissions even if cloud account reads fail', async () => {
  mockAuth.hasCloudSession.mockResolvedValue(false);
  const open = jest.spyOn(Linking, 'openSettings').mockResolvedValue();
  try {
    const renderer = await renderPage(SettingsPage);
    await act(async () =>
      renderer.root
        .findAll(
          node => node.props.accessibilityLabel === 'Open app permissions',
        )[0]
        .props.onPress(),
    );
    expect(open).toHaveBeenCalledTimes(1);
  } finally {
    open.mockRestore();
  }
});

test('web Settings hides request details and offers a real retry after failure', async () => {
  const originalPlatform = Platform.OS;
  Object.defineProperty(Platform, 'OS', {configurable: true, value: 'web'});
  mockBackend.request
    .mockResolvedValueOnce({
      id: 'service-settings-read',
      status: 503,
      body: null,
    })
    .mockResolvedValueOnce({
      id: 'service-settings-read',
      status: 200,
      body: JSON.stringify({
        identity: null,
        entitlement: {limitKey: 'chat', used: 1, limit: null},
      }),
    });
  try {
    const renderer = await renderPage(SettingsPage);
    expect(textOf(renderer)).toContain(
      'Settings could not be loaded. Try again.',
    );
    expect(textOf(renderer)).not.toContain('service-settings-read');
    expect(textOf(renderer)).not.toContain('503');
    await act(async () =>
      renderer.root
        .findAll(node => node.props.accessibilityLabel === 'Retry settings')[0]
        .props.onPress(),
    );
    expect(textOf(renderer)).toContain('1 requests used');
    expect(textOf(renderer)).not.toContain('Settings could not be loaded');
  } finally {
    Object.defineProperty(Platform, 'OS', {
      configurable: true,
      value: originalPlatform,
    });
  }
});

test.each([
  [null, null, 'Usage allowance is unavailable'],
  [
    null,
    {limitKey: 'transcription_seconds', used: 1.5, limit: 3600.5},
    '1.5 of 3600.5 seconds used',
  ],
  [{displayName: 'Local identity', email: ''}, null, 'Local identity'],
  [
    null,
    {limitKey: 'transcription_seconds', used: 90, limit: 3600},
    '90 of 3600 seconds used',
  ],
  [
    null,
    {limitKey: 'transcription_seconds', used: 90, limit: null},
    '90 seconds used',
  ],
  [
    null,
    {limitKey: 'future_unit', used: 7, limit: 100},
    'Usage allowance is unavailable',
  ],
])(
  'web Settings preserves nullable projections and allowance units (%s, %s)',
  async (identity, entitlement, expected) => {
    const originalPlatform = Platform.OS;
    Object.defineProperty(Platform, 'OS', {configurable: true, value: 'web'});
    mockBackend.request.mockResolvedValue({
      id: 'service-settings-read',
      status: 200,
      body: JSON.stringify({identity, entitlement}),
    });
    try {
      const renderer = await renderPage(SettingsPage);
      expect(textOf(renderer)).toContain(expected as string);
      expect(textOf(renderer)).not.toContain('Settings could not be loaded');
      expect(textOf(renderer)).not.toContain('requests used');
      expect(mockAuth.hasCloudSession).not.toHaveBeenCalled();
    } finally {
      Object.defineProperty(Platform, 'OS', {
        configurable: true,
        value: originalPlatform,
      });
    }
  },
);

test.each([-1, 1.5])(
  'web Settings rejects malformed chat allowance without inventing zero usage (%s)',
  async used => {
    const originalPlatform = Platform.OS;
    Object.defineProperty(Platform, 'OS', {configurable: true, value: 'web'});
    mockBackend.request.mockResolvedValue({
      id: 'service-settings-read',
      status: 200,
      body: JSON.stringify({
        identity: null,
        entitlement: {limitKey: 'chat', used, limit: 100},
      }),
    });
    try {
      const renderer = await renderPage(SettingsPage);
      expect(textOf(renderer)).toContain('Settings could not be loaded');
      expect(textOf(renderer)).not.toContain('0 of 100');
    } finally {
      Object.defineProperty(Platform, 'OS', {
        configurable: true,
        value: originalPlatform,
      });
    }
  },
);

test('browser Apps does not offer an unusable native sign-in or installation retry', async () => {
  const previous = Platform.OS;
  Object.defineProperty(Platform, 'OS', {value: 'web', configurable: true});
  try {
    const renderer = await renderPage(ConnectorsPage);
    expect(textOf(renderer)).toContain(
      'Apps are not available for this browser connection yet.',
    );
    expect(labelsOf(renderer)).not.toContain('Sign in');
    expect(labelsOf(renderer)).not.toContain('Retry apps');
    expect(mockAuth.hasCloudSession).not.toHaveBeenCalled();
    expect(mockBackend.request).not.toHaveBeenCalled();
  } finally {
    Object.defineProperty(Platform, 'OS', {
      value: previous,
      configurable: true,
    });
  }
});
