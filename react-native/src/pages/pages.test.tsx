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
  getSoftwarePlane: jest.fn(async (): Promise<'old' | 'new'> => 'old'),
  setSoftwarePlane: jest.fn(
    async (plane: 'old' | 'new'): Promise<'old' | 'new'> => plane,
  ),
  stampedV5BackendOrigin: jest.fn(async (): Promise<string | null> => null),
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
  mockBackend.getSoftwarePlane.mockReset();
  mockBackend.getSoftwarePlane.mockResolvedValue('old');
  mockBackend.setSoftwarePlane.mockReset();
  mockBackend.setSoftwarePlane.mockImplementation(async plane => plane);
  mockBackend.stampedV5BackendOrigin.mockReset();
  mockBackend.stampedV5BackendOrigin.mockResolvedValue(null);
});

async function renderPage(
  Page: typeof ConnectorsPage | typeof SettingsPage,
  extra: Record<string, unknown> = {},
) {
  let renderer: ReactTestRenderer.ReactTestRenderer;
  await act(async () => {
    renderer = ReactTestRenderer.create(
      <Page onSignIn={jest.fn()} {...extra} />,
    );
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

test('Settings keeps Old backend and New backend on the native transport', async () => {
  mockAuth.hasCloudSession.mockResolvedValue(false);
  mockBackend.stampedV5BackendOrigin.mockResolvedValue(
    'https://omi-v5-backend-staging.example.workers.dev',
  );
  const onWorkspaceReload = jest.fn();
  const renderer = await renderPage(SettingsPage, {onWorkspaceReload});
  expect(textOf(renderer)).toContain(
    'Old backend uses your existing Omi account',
  );
  expect(labelsOf(renderer)).toContain('Use Old backend');
  expect(labelsOf(renderer)).toContain('Use New backend');
  await act(async () => {
    renderer.root
      .find(node => node.props.accessibilityLabel === 'Use New backend')
      .props.onPress();
  });
  expect(mockBackend.setSoftwarePlane).toHaveBeenCalledWith('new');
  expect(onWorkspaceReload).toHaveBeenCalledTimes(1);
  expect(textOf(renderer)).toContain(
    'New sends v5 chat, capture, conversations, memories, tasks, and settings',
  );
});

test('a failed backend plane switch does not reload the workspace', async () => {
  mockAuth.hasCloudSession.mockResolvedValue(false);
  mockBackend.setSoftwarePlane.mockRejectedValueOnce(
    new Error('plane write failed'),
  );
  const onWorkspaceReload = jest.fn();
  const renderer = await renderPage(SettingsPage, {onWorkspaceReload});
  await act(async () => {
    renderer.root
      .find(node => node.props.accessibilityLabel === 'Use New backend')
      .props.onPress();
  });
  expect(onWorkspaceReload).not.toHaveBeenCalled();
  expect(textOf(renderer)).toContain(
    'Old backend uses your existing Omi account',
  );
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
      'Account profile and usage are not available from this service yet.',
    );
    expect(textOf(renderer)).not.toContain('service-settings-read');
    expect(textOf(renderer)).not.toContain('503');
    expect(textOf(renderer)).not.toContain(
      'Settings could not be loaded. Try again.',
    );
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
  [
    {
      code: 'development_backend_unsupported',
      retryable: false,
      action: 'none',
    },
  ],
  [
    {
      code: 'service_unavailable',
      retryable: false,
      action: 'none',
    },
  ],
])(
  'web Settings nested non-retryable 503s do not offer Retry (%j)',
  async error => {
    const originalPlatform = Platform.OS;
    Object.defineProperty(Platform, 'OS', {configurable: true, value: 'web'});
    mockBackend.request.mockResolvedValue({
      id: 'service-settings-read',
      status: 503,
      body: JSON.stringify({error}),
    });
    try {
      const renderer = await renderPage(SettingsPage);
      expect(textOf(renderer)).toContain(
        'Account profile and usage are not available from this service yet.',
      );
      expect(labelsOf(renderer)).not.toContain('Retry settings');
    } finally {
      Object.defineProperty(Platform, 'OS', {
        configurable: true,
        value: originalPlatform,
      });
    }
  },
);

test('web Settings omitted 503 retryable still offers Retry', async () => {
  const originalPlatform = Platform.OS;
  Object.defineProperty(Platform, 'OS', {configurable: true, value: 'web'});
  mockBackend.request.mockResolvedValue({
    id: 'service-settings-read',
    status: 503,
    body: '{"error":"service_unavailable"}',
  });
  try {
    const renderer = await renderPage(SettingsPage);
    expect(textOf(renderer)).toContain(
      'Account profile and usage are not available from this service yet.',
    );
    expect(labelsOf(renderer)).toContain('Retry settings');
  } finally {
    Object.defineProperty(Platform, 'OS', {
      configurable: true,
      value: originalPlatform,
    });
  }
});

test('web Settings maps unauthorized credentials without inventing a signed-in profile', async () => {
  const originalPlatform = Platform.OS;
  Object.defineProperty(Platform, 'OS', {configurable: true, value: 'web'});
  mockBackend.request.mockResolvedValue({
    id: 'service-settings-read',
    status: 401,
    body: JSON.stringify({error: 'unauthorized'}),
  });
  try {
    const renderer = await renderPage(SettingsPage);
    expect(textOf(renderer)).toContain('Omi cloud needs a signed-in session.');
    expect(textOf(renderer)).not.toContain('Identity unavailable');
    expect(textOf(renderer)).not.toContain('service-settings-read');
    expect(labelsOf(renderer)).toContain('Retry settings');
  } finally {
    Object.defineProperty(Platform, 'OS', {
      configurable: true,
      value: originalPlatform,
    });
  }
});

test.each([
  [null, null, 'Usage allowance is unavailable'],
  [{displayName: '', email: ''}, null, 'Identity unavailable'],
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

test.each([
  [
    {
      code: 'development_backend_unsupported',
      retryable: false,
      action: 'none',
    },
  ],
  [
    {
      code: 'not_found',
      retryable: false,
      action: 'none',
    },
  ],
])(
  'nested non-retryable Apps catalogue 503s do not offer Retry (%j)',
  async error => {
    mockAuth.hasCloudSession.mockResolvedValue(true);
    mockBackend.request.mockResolvedValue({
      id: 'desktop-apps-read',
      status: 503,
      body: JSON.stringify({error}),
    });
    const renderer = await renderPage(ConnectorsPage);
    expect(textOf(renderer)).toContain(
      'Apps are not available from the selected Omi service yet.',
    );
    expect(textOf(renderer)).not.toContain(
      'This saved data could not be loaded. Retry without changing it.',
    );
    expect(labelsOf(renderer)).not.toContain('Retry apps');
  },
);

test('omitted Apps 503 retryable still offers Retry', async () => {
  mockAuth.hasCloudSession.mockResolvedValue(true);
  mockBackend.request.mockResolvedValue({
    id: 'desktop-apps-read',
    status: 503,
    body: '{"error":"service_unavailable"}',
  });
  const renderer = await renderPage(ConnectorsPage);
  expect(textOf(renderer)).toContain(
    'This saved data could not be loaded. Retry without changing it.',
  );
  expect(labelsOf(renderer)).toContain('Retry apps');
});

test('nested non-retryable Apps profile reads do not claim owned apps are still loading', async () => {
  mockAuth.hasCloudSession.mockResolvedValue(true);
  mockBackend.request.mockImplementation(async request => {
    if (request.path === '/v1/apps') {
      return {
        id: request.id,
        status: 200,
        body: JSON.stringify([{id: 'catalog-app-1', name: 'Owned app'}]),
      };
    }
    if (request.path === '/v1/apps/enabled') {
      return {id: request.id, status: 200, body: JSON.stringify([])};
    }
    if (request.path === '/v1/users/profile') {
      return {
        id: request.id,
        status: 503,
        body: JSON.stringify({
          error: {
            code: 'development_backend_unsupported',
            retryable: false,
            action: 'none',
          },
        }),
      };
    }
    return {id: request.id, status: 404, body: null};
  });
  const renderer = await renderPage(ConnectorsPage);
  expect(textOf(renderer)).toContain(
    'This account setting is not available from the selected Omi service yet.',
  );
  expect(textOf(renderer)).not.toContain(
    'Owned apps are unavailable until the account profile loads.',
  );
});

test('nested non-retryable Apps enabled reads do not claim catalogue apps are installed', async () => {
  mockAuth.hasCloudSession.mockResolvedValue(true);
  mockBackend.request.mockImplementation(async request => {
    if (request.path === '/v1/apps') {
      return {
        id: request.id,
        status: 200,
        body: JSON.stringify([
          {id: 'catalog-app-1', name: 'Owned app', enabled: true},
        ]),
      };
    }
    if (request.path === '/v1/apps/enabled') {
      return {
        id: request.id,
        status: 503,
        body: JSON.stringify({
          error: {
            code: 'development_backend_unsupported',
            retryable: false,
            action: 'none',
          },
        }),
      };
    }
    if (request.path === '/v1/users/profile') {
      return {
        id: request.id,
        status: 200,
        body: JSON.stringify({uid: 'user-1'}),
      };
    }
    return {id: request.id, status: 404, body: null};
  });
  const renderer = await renderPage(ConnectorsPage);
  expect(textOf(renderer)).toContain(
    'Apps are not available from the selected Omi service yet.',
  );
  expect(textOf(renderer)).not.toContain('No installed apps.');
  expect(textOf(renderer)).toContain('Owned app');
  expect(textOf(renderer)).not.toContain('Not installed');
  expect(labelsOf(renderer)).not.toContain('Install Owned app');
  expect(labelsOf(renderer)).not.toContain('Remove Owned app');
});

test('successful empty Apps enabled reads still report catalogue apps as not installed', async () => {
  mockAuth.hasCloudSession.mockResolvedValue(true);
  mockBackend.request.mockImplementation(async request => {
    if (request.path === '/v1/apps') {
      return {
        id: request.id,
        status: 200,
        body: JSON.stringify([
          {id: 'catalog-app-1', name: 'Owned app', enabled: false},
        ]),
      };
    }
    if (request.path === '/v1/apps/enabled') {
      return {id: request.id, status: 200, body: JSON.stringify([])};
    }
    if (request.path === '/v1/users/profile') {
      return {
        id: request.id,
        status: 200,
        body: JSON.stringify({uid: 'user-1'}),
      };
    }
    return {id: request.id, status: 404, body: null};
  });
  const renderer = await renderPage(ConnectorsPage);
  expect(textOf(renderer)).toContain('Owned app');
  expect(textOf(renderer)).toContain('Not installed');
  expect(textOf(renderer)).toContain('No installed apps.');
  expect(labelsOf(renderer)).toContain('Install Owned app');
});

test('whitespace-only Apps description does not leave a blank catalogue subtitle', async () => {
  mockAuth.hasCloudSession.mockResolvedValue(true);
  mockBackend.request.mockImplementation(async request => {
    if (request.path === '/v1/apps') {
      return {
        id: request.id,
        status: 200,
        body: JSON.stringify([
          {
            id: 'catalog-app-1',
            name: 'Owned app',
            description: ' \t\n',
            enabled: false,
          },
        ]),
      };
    }
    if (request.path === '/v1/apps/enabled') {
      return {id: request.id, status: 200, body: JSON.stringify([])};
    }
    if (request.path === '/v1/users/profile') {
      return {
        id: request.id,
        status: 200,
        body: JSON.stringify({uid: 'user-1'}),
      };
    }
    return {id: request.id, status: 404, body: null};
  });
  const renderer = await renderPage(ConnectorsPage);
  expect(textOf(renderer)).toContain('Owned app');
  expect(textOf(renderer)).toContain('Not installed');
  const blankCopy = renderer.root.findAllByType(Text).filter(node => {
    const child = node.props.children;
    return typeof child === 'string' && child.length > 0 && child.trim() === '';
  });
  expect(blankCopy).toHaveLength(0);
});

test('nested non-retryable Apps enable writes latch Install', async () => {
  mockAuth.hasCloudSession.mockResolvedValue(true);
  mockBackend.request.mockImplementation(async request => {
    if (request.path === '/v1/apps') {
      return {
        id: request.id,
        status: 200,
        body: JSON.stringify([
          {id: 'catalog-app-1', name: 'Owned app', enabled: false},
        ]),
      };
    }
    if (request.path === '/v1/apps/enabled') {
      return {id: request.id, status: 200, body: JSON.stringify([])};
    }
    if (request.path === '/v1/users/profile') {
      return {
        id: request.id,
        status: 200,
        body: JSON.stringify({uid: 'user-1'}),
      };
    }
    if (
      request.method === 'POST' &&
      typeof request.path === 'string' &&
      request.path.startsWith('/v1/apps/enable')
    ) {
      return {
        id: request.id,
        status: 503,
        body: JSON.stringify({
          error: {
            code: 'development_backend_unsupported',
            retryable: false,
            action: 'none',
          },
        }),
      };
    }
    return {id: request.id, status: 404, body: null};
  });
  const renderer = await renderPage(ConnectorsPage);
  expect(labelsOf(renderer)).toContain('Install Owned app');
  await act(async () => {
    renderer.root
      .find(node => node.props.accessibilityLabel === 'Install Owned app')
      .props.onPress();
    await Promise.resolve();
    await Promise.resolve();
  });
  expect(textOf(renderer)).toContain(
    'Apps are not available from the selected Omi service yet.',
  );
  expect(labelsOf(renderer)).not.toContain('Install Owned app');
  expect(textOf(renderer)).toContain('Owned app');
  expect(textOf(renderer)).toContain('Not installed');
});

test('nested non-retryable training opt-in writes latch Opt in', async () => {
  mockAuth.hasCloudSession.mockResolvedValue(true);
  mockBackend.request.mockImplementation(async request => {
    if (request.path === '/v1/users/training-data-opt-in') {
      if (request.method === 'POST') {
        return {
          id: request.id,
          status: 503,
          body: JSON.stringify({
            error: {
              code: 'development_backend_unsupported',
              retryable: false,
              action: 'none',
            },
          }),
        };
      }
      return {
        id: request.id,
        status: 200,
        body: JSON.stringify({opted_in: false}),
      };
    }
    return {id: request.id, status: 404, body: null};
  });
  const renderer = await renderPage(SettingsPage);
  await act(async () => {
    renderer.root
      .find(node => node.props.accessibilityLabel === 'Privacy settings')
      .props.onPress();
  });
  expect(labelsOf(renderer)).toContain('Opt in');
  await act(async () => {
    renderer.root
      .find(node => node.props.accessibilityLabel === 'Opt in')
      .props.onPress();
    await Promise.resolve();
    await Promise.resolve();
  });
  expect(textOf(renderer)).toContain(
    'This account setting is not available from the selected Omi service yet.',
  );
  expect(labelsOf(renderer)).not.toContain('Opt in');
  expect(textOf(renderer)).toContain(
    'This account has not opted in to training data.',
  );
});

test('omitted training opt-in 503 still keeps Opt in live', async () => {
  mockAuth.hasCloudSession.mockResolvedValue(true);
  mockBackend.request.mockImplementation(async request => {
    if (request.path === '/v1/users/training-data-opt-in') {
      if (request.method === 'POST') {
        return {
          id: request.id,
          status: 503,
          body: '{"error":"service_unavailable"}',
        };
      }
      return {
        id: request.id,
        status: 200,
        body: JSON.stringify({opted_in: false}),
      };
    }
    return {id: request.id, status: 404, body: null};
  });
  const renderer = await renderPage(SettingsPage);
  await act(async () => {
    renderer.root
      .find(node => node.props.accessibilityLabel === 'Privacy settings')
      .props.onPress();
  });
  await act(async () => {
    renderer.root
      .find(node => node.props.accessibilityLabel === 'Opt in')
      .props.onPress();
    await Promise.resolve();
    await Promise.resolve();
  });
  expect(
    renderer.root.find(node => node.props.accessibilityLabel === 'Opt in').props
      .disabled,
  ).toBe(false);
});

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

test.each(['failure', 'signed-out'])(
  'older Settings session probe %s cannot replace the latest successful load',
  async outcome => {
    mockAuth.hasCloudSession.mockRejectedValueOnce(new Error('offline'));
    const renderer = await renderPage(SettingsPage);
    const retry = renderer.root.find(
      node => node.props.accessibilityLabel === 'Retry settings',
    ).props.onPress;
    let resolveOld!: (value: boolean) => void;
    let rejectOld!: (error: Error) => void;
    mockAuth.hasCloudSession
      .mockImplementationOnce(
        () =>
          new Promise((resolve, reject) => {
            resolveOld = resolve;
            rejectOld = reject;
          }),
      )
      .mockResolvedValue(true);
    mockBackend.request.mockImplementation(async request => ({
      id: request.id,
      status: 200,
      body: JSON.stringify({uid: 'current-user', name: 'Current account'}),
    }));
    await act(async () => {
      retry();
    });
    expect(textOf(renderer)).toContain('Loading account…');
    expect(labelsOf(renderer)).not.toContain('Retry settings');
    await act(async () => {
      retry();
    });
    expect(textOf(renderer)).toContain('Current account');
    await act(async () => {
      if (outcome === 'failure') {
        rejectOld(new Error('older failure'));
      } else {
        resolveOld(false);
      }
    });
    expect(textOf(renderer)).toContain('Current account');
    expect(labelsOf(renderer)).not.toContain('Retry settings');
  },
);

test('unmounted Settings session probes cannot start reads for the next account', async () => {
  let resolveOld!: (value: boolean) => void;
  mockAuth.hasCloudSession
    .mockImplementationOnce(
      () =>
        new Promise(resolve => {
          resolveOld = resolve;
        }),
    )
    .mockResolvedValue(true);
  const retired = await renderPage(SettingsPage);
  await act(async () => {
    retired.unmount();
  });
  mockBackend.request.mockImplementation(async request => ({
    id: request.id,
    status: 200,
    body: JSON.stringify({uid: 'next-user', name: 'Next account'}),
  }));
  const current = await renderPage(SettingsPage);
  const requests = mockBackend.request.mock.calls.length;
  await act(async () => {
    resolveOld(true);
  });
  expect(mockBackend.request).toHaveBeenCalledTimes(requests);
  expect(textOf(current)).toContain('Next account');
});

test('older browser Settings response cannot overwrite a newer response', async () => {
  const originalPlatform = Platform.OS;
  Object.defineProperty(Platform, 'OS', {configurable: true, value: 'web'});
  try {
    mockBackend.request.mockRejectedValueOnce(new Error('offline'));
    const renderer = await renderPage(SettingsPage);
    const retry = renderer.root.find(
      node => node.props.accessibilityLabel === 'Retry settings',
    ).props.onPress;
    let resolveOld!: (value: unknown) => void;
    mockBackend.request
      .mockImplementationOnce(
        () =>
          new Promise(resolve => {
            resolveOld = resolve;
          }),
      )
      .mockResolvedValue({
        id: 'service-settings-read',
        status: 200,
        body: JSON.stringify({
          identity: {displayName: 'Latest identity', email: ''},
          entitlement: null,
        }),
      });
    await act(async () => {
      retry();
    });
    await act(async () => {
      retry();
    });
    expect(textOf(renderer)).toContain('Latest identity');
    await act(async () => {
      resolveOld({
        id: 'service-settings-read',
        status: 200,
        body: JSON.stringify({
          identity: {displayName: 'Older identity', email: ''},
          entitlement: null,
        }),
      });
    });
    expect(textOf(renderer)).toContain('Latest identity');
    expect(textOf(renderer)).not.toContain('Older identity');
  } finally {
    Object.defineProperty(Platform, 'OS', {
      configurable: true,
      value: originalPlatform,
    });
  }
});

test('Settings developer webhook titles are not raw API keys', async () => {
  mockAuth.hasCloudSession.mockResolvedValue(true);
  mockBackend.request.mockImplementation(async request => {
    if (request.path === '/v1/users/developer/webhooks/status') {
      return {
        id: request.id,
        status: 200,
        body: JSON.stringify({
          memory_created: {
            enabled: true,
            url: 'https://example.test/conversation',
          },
          realtime_transcript: false,
          audio_bytes: {enabled: true, url: 'https://example.test/audio'},
          day_summary: {enabled: false, url: null},
          button_event: {url: 'https://example.test/button'},
        }),
      };
    }
    return {id: request.id, status: 404, body: null};
  });
  const renderer = await renderPage(SettingsPage);
  await act(async () => {
    renderer.root
      .find(node => node.props.accessibilityLabel === 'Developer settings')
      .props.onPress();
  });
  const tree = textOf(renderer);
  expect(tree).toContain('Conversation Events');
  expect(tree).toContain('Real-time Transcript');
  expect(tree).toContain('Audio Bytes');
  expect(tree).toContain('Day Summary');
  expect(tree).not.toContain('memory_created');
  expect(tree).not.toContain('realtime_transcript');
  expect(tree).not.toContain('audio_bytes');
  expect(tree).not.toContain('day_summary');
  expect(tree).toContain('Status unavailable');
  expect(tree).not.toContain('Status unknown');
});

test('Apps category labels are not raw wire tokens', async () => {
  mockAuth.hasCloudSession.mockResolvedValue(true);
  mockBackend.request.mockImplementation(async request => {
    if (request.path === '/v1/apps') {
      return {
        id: request.id,
        status: 200,
        body: JSON.stringify([
          {
            id: 'catalog-app-1',
            name: 'Catalog fixture app',
            category: 'productivity',
          },
        ]),
      };
    }
    if (request.path === '/v1/apps/enabled') {
      return {id: request.id, status: 200, body: JSON.stringify([])};
    }
    if (request.path === '/v1/users/profile') {
      return {
        id: request.id,
        status: 200,
        body: JSON.stringify({uid: 'user-1'}),
      };
    }
    return {id: request.id, status: 404, body: null};
  });
  const renderer = await renderPage(ConnectorsPage);
  const tree = textOf(renderer);
  expect(tree).toContain('Catalog fixture app');
  expect(tree).toContain('Productivity');
  expect(tree).not.toContain('productivity');
});
