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
const {developerKeyCreatedCopy, desktopBackendServiceCopy} = require('../desktopReadClient');

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
    expect(textOf(renderer)).toContain('Plan unavailable');
    expect(labelsOf(renderer)).not.toContain('Sign in');
    expect(labelsOf(renderer)).not.toContain('Open app permissions');
  } finally {
    Object.defineProperty(Platform, 'OS', {
      configurable: true,
      value: originalPlatform,
    });
  }
});

test('web Settings keeps GET planLabel instead of a plan-less usage row', async () => {
  const originalPlatform = Platform.OS;
  Object.defineProperty(Platform, 'OS', {configurable: true, value: 'web'});
  mockBackend.request.mockResolvedValue({
    id: 'service-settings-read',
    status: 200,
    body: JSON.stringify({
      identity: {displayName: 'Local QA identity', email: ''},
      entitlement: {
        planLabel: 'Omi Plus',
        limitKey: 'chat',
        used: 7,
        limit: 100,
      },
    }),
  });
  try {
    const renderer = await renderPage(SettingsPage);
    const tree = textOf(renderer);
    expect(tree).toContain('Omi Plus');
    expect(tree).toContain('7 of 100 requests used');
    expect(tree).not.toContain('Plan unavailable');
    expect(tree).not.toContain('Upgrade');
    expect(labelsOf(renderer)).not.toContain('Sign in');
  } finally {
    Object.defineProperty(Platform, 'OS', {
      configurable: true,
      value: originalPlatform,
    });
  }
});

test('web Settings keeps GET limitReached instead of a usage-only row', async () => {
  const originalPlatform = Platform.OS;
  Object.defineProperty(Platform, 'OS', {configurable: true, value: 'web'});
  mockBackend.request.mockResolvedValue({
    id: 'service-settings-read',
    status: 200,
    body: JSON.stringify({
      identity: {displayName: 'Local QA identity', email: ''},
      entitlement: {
        planLabel: 'Omi Plus',
        limitKey: 'chat',
        used: 1,
        limit: 100,
        limitReached: true,
      },
    }),
  });
  try {
    const renderer = await renderPage(SettingsPage);
    const tree = textOf(renderer);
    expect(tree).toContain('1 of 100 requests used · Limit reached');
    expect(tree).not.toContain('Upgrade');
  } finally {
    Object.defineProperty(Platform, 'OS', {
      configurable: true,
      value: originalPlatform,
    });
  }
});

test('web Settings does not invent Limit reached from exhausted used and limit', async () => {
  const originalPlatform = Platform.OS;
  Object.defineProperty(Platform, 'OS', {configurable: true, value: 'web'});
  mockBackend.request.mockResolvedValue({
    id: 'service-settings-read',
    status: 200,
    body: JSON.stringify({
      identity: {displayName: 'Local QA identity', email: ''},
      entitlement: {
        planLabel: 'Omi Plus',
        limitKey: 'chat',
        used: 100,
        limit: 100,
      },
    }),
  });
  try {
    const renderer = await renderPage(SettingsPage);
    const tree = textOf(renderer);
    expect(tree).toContain('100 of 100 requests used');
    expect(tree).not.toContain('Limit reached');
    expect(tree).not.toContain('Upgrade');
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
  [{displayName: ' \t', email: ' \n'}, null, 'Identity unavailable'],
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
  [
    {displayName: 'Local identity', email: ''},
    {limitKey: '', used: 7, limit: 100},
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

test('successful Apps enabled reads do not treat catalogue enabled bits as installed', async () => {
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
  expect(labelsOf(renderer)).not.toContain('Remove Owned app');
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

test('NEXT LINE-only Apps description does not leave a blank catalogue subtitle', async () => {
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
            description: '\u0085',
            author: '\u0085',
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
  expect(textOf(renderer)).not.toContain('\u0085');
});

test('whitespace-only Apps name stays visible instead of a blank catalogue title', async () => {
  mockAuth.hasCloudSession.mockResolvedValue(true);
  mockBackend.request.mockImplementation(async request => {
    if (request.path === '/v1/apps') {
      return {
        id: request.id,
        status: 200,
        body: JSON.stringify([
          {
            id: 'catalog-app-1',
            name: ' \t\n',
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
  expect(textOf(renderer)).toContain('App name unavailable');
  expect(textOf(renderer)).toContain('Not installed');
  expect(labelsOf(renderer)).toContain('Install App name unavailable');
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

test('Settings omits NEXT LINE-only company and job instead of blank rows', async () => {
  mockAuth.hasCloudSession.mockResolvedValue(true);
  mockBackend.request.mockImplementation(async request => {
    if (request.path === '/v1/users/profile') {
      return {
        id: request.id,
        status: 200,
        body: JSON.stringify({
          uid: 'user-1',
          name: 'Ada',
          email: 'ada@example.com',
          company: '\u0085',
          job: '\u0085',
        }),
      };
    }
    return {id: request.id, status: 404, body: null};
  });
  const renderer = await renderPage(SettingsPage);
  const tree = textOf(renderer);
  expect(tree).toContain('Ada');
  expect(tree).not.toContain('Company');
  expect(tree).not.toContain('Job');
  expect(tree).not.toContain('\u0085');
});

test('Settings names GET usage today without Upgrade', async () => {
  mockAuth.hasCloudSession.mockResolvedValue(true);
  mockBackend.request.mockImplementation(async request => {
    if (request.path === '/v1/users/me/usage?period=today') {
      return {
        id: request.id,
        status: 200,
        body: JSON.stringify({
          today: {
            transcription_seconds: 90,
            words_transcribed: 12,
            insights_gained: 3,
            memories_created: 1,
          },
        }),
      };
    }
    return {id: request.id, status: 404, body: null};
  });
  const renderer = await renderPage(SettingsPage);
  const tree = textOf(renderer);
  expect(tree).toContain('Listening');
  expect(tree).toContain('2 minutes');
  expect(tree).toContain('Understanding');
  expect(tree).toContain('12 words');
  expect(tree).toContain('Providing');
  expect(tree).toContain('3 insights');
  expect(tree).toContain('Remembering');
  expect(tree).toContain('1 memories');
  expect(tree).not.toContain('Upgrade');
});

test('Settings names GET subscription period quotas without Upgrade', async () => {
  mockAuth.hasCloudSession.mockResolvedValue(true);
  mockBackend.request.mockImplementation(async request => {
    if (request.path === '/v1/users/me/subscription') {
      return {
        id: request.id,
        status: 200,
        body: JSON.stringify({
          plan: 'basic',
          status: 'active',
          words_transcribed_used: 12,
          words_transcribed_limit: 10000,
          insights_gained_used: 3,
          insights_gained_limit: 500,
          chat_quota_used: 5,
          chat_quota_unit: 'messages',
          subscription: {
            plan: 'basic',
            status: 'active',
            limits: {chat_questions_per_month: 100},
          },
        }),
      };
    }
    return {id: request.id, status: 404, body: null};
  });
  const renderer = await renderPage(SettingsPage);
  const tree = textOf(renderer);
  expect(tree).toContain('Words this month');
  expect(tree).toContain('12 of 10000 words used this month');
  expect(tree).toContain('Insights this month');
  expect(tree).toContain('3 of 500 insights gained this month');
  expect(tree).toContain('Chat this month');
  expect(tree).toContain('5 of 100 messages used this month');
  expect(tree).not.toContain('Upgrade');
});

test('Settings names GET primary language without a write sheet', async () => {
  mockAuth.hasCloudSession.mockResolvedValue(true);
  mockBackend.request.mockImplementation(async request => {
    if (request.path === '/v1/users/language') {
      return {
        id: request.id,
        status: 200,
        body: JSON.stringify({language: 'en'}),
      };
    }
    if (request.path === '/v1/users/available-languages') {
      return {
        id: request.id,
        status: 200,
        body: JSON.stringify({
          languages: [{code: 'en', name: 'English'}],
        }),
      };
    }
    return {id: request.id, status: 404, body: null};
  });
  const renderer = await renderPage(SettingsPage);
  const tree = textOf(renderer);
  expect(tree).toContain('Primary language');
  expect(tree).toContain('English');
  expect(tree).not.toContain('Not set');
});

test('Settings names GET people without a write sheet', async () => {
  mockAuth.hasCloudSession.mockResolvedValue(true);
  mockBackend.request.mockImplementation(async request => {
    if (request.path === '/v1/users/people?include_speech_samples=false') {
      return {
        id: request.id,
        status: 200,
        body: JSON.stringify([
          {id: 'person-alex', name: 'Alex Chen'},
          {id: 'person-empty', name: ' \t'},
        ]),
      };
    }
    return {id: request.id, status: 404, body: null};
  });
  const renderer = await renderPage(SettingsPage);
  const tree = textOf(renderer);
  expect(tree).toContain('People');
  expect(tree).toContain('Alex Chen');
  expect(tree).not.toContain('person-alex');
  expect(tree).not.toContain('person-empty');
});

test('Settings names GET fair use without Upgrade or a write sheet', async () => {
  mockAuth.hasCloudSession.mockResolvedValue(true);
  mockBackend.request.mockImplementation(async request => {
    if (request.path === '/v1/fair-use/status') {
      return {
        id: request.id,
        status: 200,
        body: JSON.stringify({
          stage: 'restrict',
          case_ref: 'FU-1',
          message: 'Usage is restricted.',
          speech_hours_today: 2.4,
          speech_hours_3day: 8.1,
          speech_hours_weekly: 11,
          limits: {
            daily_hours: 2,
            three_day_hours: 8,
            weekly_hours: 10,
          },
          usage_pct: {daily: 120, three_day: 101, weekly: 110},
          dg_budget: {
            daily_limit_ms: 1800000,
            used_ms: 1800000,
            remaining_ms: 0,
            exhausted: true,
            resets_at: '2099-01-01T00:00:00Z',
          },
        }),
      };
    }
    return {id: request.id, status: 404, body: null};
  });
  const renderer = await renderPage(SettingsPage);
  const tree = textOf(renderer);
  expect(tree).toContain('Fair Use');
  expect(tree).toContain('Restricted');
  expect(tree).toContain('FU-1');
  expect(tree).toContain('2.4h / 2h');
  expect(tree).toContain('3-Day Rolling');
  expect(tree).toContain('Weekly Rolling');
  expect(tree).toContain('Usage is restricted.');
  expect(tree).toContain('Daily transcription');
  expect(tree).toContain('30m / 30m');
  expect(tree).toContain('Daily transcription limit reached');
  expect(tree).toMatch(/Resets \d+h/);
  expect(tree).not.toContain('Upgrade');
});

test('Settings names GET daily summaries without regenerate or a write sheet', async () => {
  mockAuth.hasCloudSession.mockResolvedValue(true);
  mockBackend.request.mockImplementation(async request => {
    if (request.path === '/v1/users/daily-summaries?limit=3&offset=0') {
      return {
        id: request.id,
        status: 200,
        body: JSON.stringify({
          summaries: [
            {
              id: 'sum-1',
              date: '2026-09-09',
              headline: 'Met with the team',
              day_emoji: '🎯',
              overview: 'Shipped the recap body.',
              stats: {
                total_conversations: 3,
                action_items_count: 2,
                total_duration_minutes: 90,
                watching_minutes: 10,
                proactive_moments: 1,
              },
            },
            {id: 'sum-empty', date: '2026-09-08', headline: ' \t'},
          ],
        }),
      };
    }
    return {id: request.id, status: 404, body: null};
  });
  const renderer = await renderPage(SettingsPage);
  const tree = textOf(renderer);
  expect(tree).toContain('Daily summary');
  expect(tree).toContain('Met with the team');
  expect(tree).toContain('🎯');
  expect(tree).toContain('3 conversations');
  expect(tree).toContain('1h 30m');
  expect(tree).toContain('2 action items');
  expect(tree).toContain('10m watching');
  expect(tree).toContain('1 proactive moment');
  expect(tree).toContain('Shipped the recap body.');
  expect(tree).not.toContain('Your Day in Review');
  expect(tree).not.toContain('📅');
  expect(tree).not.toContain('sum-1');
  expect(tree).not.toContain('Regenerate');
  expect(tree).not.toContain('Delivery time');
  expect(tree).not.toContain('10:00 PM');
  expect(tree).not.toContain('Notification frequency');
  expect(tree).not.toContain('Custom vocabulary');
  expect(tree).not.toContain('Automatic translation');
});

test('Settings names GET daily-summary-settings without a picker or Flutter defaults', async () => {
  mockAuth.hasCloudSession.mockResolvedValue(true);
  mockBackend.request.mockImplementation(async request => {
    if (request.path === '/v1/users/daily-summary-settings') {
      return {
        id: request.id,
        status: 200,
        body: JSON.stringify({enabled: true, hour: 22}),
      };
    }
    return {id: request.id, status: 404, body: null};
  });
  const renderer = await renderPage(SettingsPage);
  const tree = textOf(renderer);
  expect(tree).toContain('Daily summaries');
  expect(tree).toContain('Enabled');
  expect(tree).toContain('Delivery time');
  expect(tree).toContain('10:00 PM');
  expect(tree).not.toContain('Your Day in Review');
  expect(mockBackend.request).toHaveBeenCalledWith({
    id: expect.any(String),
    method: 'GET',
    expectedApiContract: 'omi',
    path: '/v1/users/daily-summary-settings',
  });
  expect(mockBackend.request.mock.calls.some(call => call[0].method === 'PATCH')).toBe(
    false,
  );
});

test('Settings names GET mentor notification frequency without a purple slider', async () => {
  mockAuth.hasCloudSession.mockResolvedValue(true);
  mockBackend.request.mockImplementation(async request => {
    if (request.path === '/v1/users/mentor-notification-settings') {
      return {
        id: request.id,
        status: 200,
        body: JSON.stringify({frequency: 1}),
      };
    }
    return {id: request.id, status: 404, body: null};
  });
  const renderer = await renderPage(SettingsPage);
  const tree = textOf(renderer);
  expect(tree).toContain('Notification frequency');
  expect(tree).toContain('Minimal');
  expect(tree).not.toContain('Balanced');
  expect(tree).not.toContain('Only critical reminders');
  expect(mockBackend.request).toHaveBeenCalledWith({
    id: expect.any(String),
    method: 'GET',
    expectedApiContract: 'omi',
    path: '/v1/users/mentor-notification-settings',
  });
  expect(mockBackend.request.mock.calls.some(call => call[0].method === 'PATCH')).toBe(
    false,
  );
});

test('Settings names GET custom vocabulary without add/delete or Flutter false defaults', async () => {
  mockAuth.hasCloudSession.mockResolvedValue(true);
  mockBackend.request.mockImplementation(async request => {
    if (request.path === '/v1/users/transcription-preferences') {
      return {
        id: request.id,
        status: 200,
        body: JSON.stringify({
          vocabulary: ['Omi', ' \t', 'Based Hardware'],
          single_language_mode: true,
        }),
      };
    }
    return {id: request.id, status: 404, body: null};
  });
  const renderer = await renderPage(SettingsPage);
  const tree = textOf(renderer);
  expect(tree).toContain('Custom vocabulary');
  expect(tree).toContain('Omi');
  expect(tree).toContain('Based Hardware');
  expect(tree).toContain('Automatic translation');
  expect(tree).toContain('Off');
  expect(tree).not.toContain('Detect 10+ languages');
  expect(tree).not.toContain('Add Words');
  expect(mockBackend.request).toHaveBeenCalledWith({
    id: expect.any(String),
    method: 'GET',
    expectedApiContract: 'omi',
    path: '/v1/users/transcription-preferences',
  });
  expect(mockBackend.request.mock.calls.some(call => call[0].method === 'PATCH')).toBe(
    false,
  );
});

test('Settings omits Automatic translation when GET single_language_mode is missing', async () => {
  mockAuth.hasCloudSession.mockResolvedValue(true);
  mockBackend.request.mockImplementation(async request => {
    if (request.path === '/v1/users/transcription-preferences') {
      return {
        id: request.id,
        status: 200,
        body: JSON.stringify({vocabulary: ['Omi']}),
      };
    }
    return {id: request.id, status: 404, body: null};
  });
  const renderer = await renderPage(SettingsPage);
  const tree = textOf(renderer);
  expect(tree).toContain('Custom vocabulary');
  expect(tree).toContain('Omi');
  expect(tree).not.toContain('Automatic translation');
});

test('Settings developer webhook URLs omit empty or whitespace values', async () => {
  mockAuth.hasCloudSession.mockResolvedValue(true);
  mockBackend.request.mockImplementation(async request => {
    if (request.path === '/v1/users/developer/webhooks/status') {
      return {
        id: request.id,
        status: 200,
        body: JSON.stringify({
          memory_created: {enabled: true, url: ' \t\n'},
          day_summary: {enabled: false, url: '  https://example.test/day  '},
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
  expect(tree).toContain('Enabled');
  expect(tree).toContain('Disabled');
  expect(tree).toContain('https://example.test/day');
  expect(tree).not.toContain(' \t\n');
});

test('Settings names GET developer webhook URLs without enable writes', async () => {
  mockAuth.hasCloudSession.mockResolvedValue(true);
  mockBackend.request.mockImplementation(async request => {
    if (request.path === '/v1/users/developer/webhooks/status') {
      return {
        id: request.id,
        status: 200,
        body: JSON.stringify({
          memory_created: true,
          realtime_transcript: false,
          audio_bytes: true,
          day_summary: true,
        }),
      };
    }
    if (request.path === '/v1/users/developer/webhook/memory_created') {
      return {
        id: request.id,
        status: 200,
        body: JSON.stringify({url: 'https://example.test/conversation'}),
      };
    }
    if (request.path === '/v1/users/developer/webhook/realtime_transcript') {
      return {
        id: request.id,
        status: 200,
        body: JSON.stringify({url: 'https://example.test/transcript'}),
      };
    }
    if (request.path === '/v1/users/developer/webhook/audio_bytes') {
      return {
        id: request.id,
        status: 200,
        body: JSON.stringify({url: 'https://example.test/audio,5'}),
      };
    }
    if (request.path === '/v1/users/developer/webhook/day_summary') {
      return {
        id: request.id,
        status: 200,
        body: JSON.stringify({url: ''}),
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
  expect(tree).toContain('https://example.test/conversation');
  expect(tree).toContain('https://example.test/transcript');
  expect(tree).toContain('https://example.test/audio');
  expect(tree).toContain('5s');
  expect(tree).not.toContain('https://example.test/audio,5');
  expect(mockBackend.request.mock.calls.some(call => call[0].method === 'POST')).toBe(
    false,
  );
  expect(
    mockBackend.request.mock.calls.some(
      call => call[0].path === '/v1/users/developer/webhook/button_event',
    ),
  ).toBe(false);
});

test('Settings names GET developer and MCP keys without revoke or a full secret', async () => {
  mockAuth.hasCloudSession.mockResolvedValue(true);
  mockBackend.request.mockImplementation(async request => {
    if (request.path === '/v1/dev/keys') {
      return {
        id: request.id,
        status: 200,
        body: JSON.stringify([
          {
            id: 'dev-1',
            name: 'Local',
            key_prefix: 'omi_sk_ab',
            key: 'omi_sk_abcdef_secret',
            created_at: '2026-09-09T12:00:00.000Z',
            scopes: [
              'conversations:read',
              'conversations:write',
              'memories:read',
              'memories:write',
              'action_items:read',
              'action_items:write',
              'goals:read',
              'goals:write',
            ],
          },
        ]),
      };
    }
    if (request.path === '/v1/mcp/keys') {
      return {
        id: request.id,
        status: 200,
        body: JSON.stringify([
          {
            id: 'mcp-1',
            name: 'Cursor',
            key_prefix: 'omi_mcp_cd',
            created_at: '2026-09-09T12:00:00.000Z',
            scopes: [
              'conversations:read',
              'conversations:write',
              'memories:read',
              'memories:write',
              'action_items:read',
              'action_items:write',
              'goals:read',
              'goals:write',
            ],
          },
        ]),
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
  const created = developerKeyCreatedCopy(
    Date.parse('2026-09-09T12:00:00.000Z'),
  );
  expect(tree).toContain('Developer key');
  expect(tree).toContain(`Local · omi_sk_ab · ${created} · Full Access`);
  expect(tree).toContain('MCP key');
  expect(tree).toContain('Cursor · omi_mcp_cd');
  expect(tree).not.toContain(`Cursor · omi_mcp_cd · ${created}`);
  expect(tree).not.toContain('Cursor · omi_mcp_cd · Full Access');
  expect(tree).not.toContain('Read Only');
  expect(tree).not.toContain('omi_sk_abcdef_secret');
  expect(tree).not.toContain('Revoke');
  expect(tree).not.toContain('Create');
  expect(mockBackend.request).toHaveBeenCalledWith({
    id: expect.any(String),
    method: 'GET',
    expectedApiContract: 'omi',
    path: '/v1/dev/keys',
  });
  expect(mockBackend.request).toHaveBeenCalledWith({
    id: expect.any(String),
    method: 'GET',
    expectedApiContract: 'omi',
    path: '/v1/mcp/keys',
  });
  expect(
    mockBackend.request.mock.calls.some(
      call => call[0].method === 'POST' || call[0].method === 'DELETE',
    ),
  ).toBe(false);
});

test('Settings names GET import jobs without Start import or Limitless', async () => {
  mockAuth.hasCloudSession.mockResolvedValue(true);
  mockBackend.request.mockImplementation(async request => {
    if (request.path === '/v1/import/jobs?limit=50') {
      return {
        id: request.id,
        status: 200,
        body: JSON.stringify([
          {
            job_id: 'job-1',
            status: 'completed',
            conversations_created: 3,
            conversations_skipped: 2,
          },
          {
            job_id: 'job-2',
            status: 'processing',
            processed_files: 3,
            total_files: 10,
          },
          {
            job_id: 'job-3',
            status: 'failed',
            error: 'Zip could not be read.',
          },
          {job_id: 'job-4', status: 'queued'},
        ]),
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
  expect(tree).toContain('Import Data');
  expect(tree).toContain('Completed · 3 conversations · 2 skipped');
  expect(tree).toContain('Processing · 3/10');
  expect(tree).toContain('Failed · Zip could not be read.');
  expect(tree).toContain('queued');
  expect(tree).not.toContain('job-1');
  expect(tree).not.toContain('Pending');
  expect(tree).not.toContain('No imports yet');
  expect(tree).not.toContain('Limitless');
  expect(tree).not.toContain('Coming Soon');
  expect(tree).not.toContain('Delete Imported Data');
  expect(tree).not.toContain('less than a minute');
  expect(mockBackend.request).toHaveBeenCalledWith({
    id: expect.any(String),
    method: 'GET',
    expectedApiContract: 'omi',
    path: '/v1/import/jobs?limit=50',
  });
  expect(
    mockBackend.request.mock.calls.some(
      call => call[0].method === 'POST' || call[0].method === 'DELETE',
    ),
  ).toBe(false);
  expect(
    mockBackend.request.mock.calls.some(call =>
      String(call[0].path).includes('limitless'),
    ),
  ).toBe(false);
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

test('Connectors rows keep GET connected accounts as Connected instead of Installed-only', async () => {
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
            connected_accounts: ['acct-1'],
          },
        ]),
      };
    }
    if (request.path === '/v1/apps/enabled') {
      return {
        id: request.id,
        status: 200,
        body: JSON.stringify(['catalog-app-1']),
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
  const tree = textOf(renderer);
  expect(tree).toContain('Owned app');
  expect(tree).toContain('Connected');
  expect(tree).not.toContain('acct-1');
  expect(tree).not.toContain('Not installed');
});

test('Connectors rows keep GET private instead of a public-looking catalogue', async () => {
  mockAuth.hasCloudSession.mockResolvedValue(true);
  mockBackend.request.mockImplementation(async request => {
    if (request.path === '/v1/apps') {
      return {
        id: request.id,
        status: 200,
        body: JSON.stringify([
          {
            id: 'catalog-app-private',
            name: 'Owned app',
            private: true,
          },
          {
            id: 'catalog-app-public',
            name: 'Catalog fixture app',
            private: false,
          },
        ]),
      };
    }
    if (request.path === '/v1/apps/enabled') {
      return {
        id: request.id,
        status: 200,
        body: JSON.stringify([]),
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
  const tree = textOf(renderer);
  expect(tree).toContain('Owned app');
  expect(tree).toContain('Private · Not installed');
  expect(tree).toContain('Catalog fixture app');
  expect(tree).not.toContain('Official');
});

test('Connectors rows keep GET ratings instead of a scoreless catalogue', async () => {
  mockAuth.hasCloudSession.mockResolvedValue(true);
  mockBackend.request.mockImplementation(async request => {
    if (request.path === '/v1/apps') {
      return {
        id: request.id,
        status: 200,
        body: JSON.stringify([
          {
            id: 'catalog-app-rated',
            name: 'Owned app',
            rating_avg: 4.5,
            rating_count: 12,
          },
          {
            id: 'catalog-app-unrated',
            name: 'Catalog fixture app',
          },
        ]),
      };
    }
    if (request.path === '/v1/apps/enabled') {
      return {
        id: request.id,
        status: 200,
        body: JSON.stringify([]),
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
  const tree = textOf(renderer);
  expect(tree).toContain('Owned app');
  expect(tree).toContain('4.5 (12)');
  expect(tree).toContain('Catalog fixture app');
  expect(tree).not.toContain('0.0');
  expect(tree).not.toContain('Official');
});

test('Connectors rows keep GET http images instead of a logo-less catalogue', async () => {
  mockAuth.hasCloudSession.mockResolvedValue(true);
  mockBackend.request.mockImplementation(async request => {
    if (request.path === '/v1/apps') {
      return {
        id: request.id,
        status: 200,
        body: JSON.stringify([
          {
            id: 'catalog-app-imaged',
            name: 'Owned app',
            image: 'https://cdn.example.test/app.png',
          },
          {
            id: 'catalog-app-relative',
            name: 'Catalog fixture app',
            image: '/assets/apps/foo.png',
          },
        ]),
      };
    }
    if (request.path === '/v1/apps/enabled') {
      return {
        id: request.id,
        status: 200,
        body: JSON.stringify([]),
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
  const tree = textOf(renderer);
  expect(tree).toContain('Owned app');
  expect(
    renderer.root.findAll(
      node =>
        node.props.accessibilityLabel === 'App image' &&
        node.props.source?.uri === 'https://cdn.example.test/app.png',
    ).length,
  ).toBeGreaterThan(0);
  expect(tree).toContain('Catalog fixture app');
  expect(
    renderer.root.findAll(
      node =>
        node.props.accessibilityLabel === 'App image' &&
        node.props.source?.uri === '/assets/apps/foo.png',
    ),
  ).toHaveLength(0);
  expect(tree).not.toContain('Official');
});

test('Settings names GET task integrations without Connect or a write sheet', async () => {
  mockAuth.hasCloudSession.mockResolvedValue(true);
  mockBackend.request.mockImplementation(async request => {
    if (request.path === '/v1/task-integrations') {
      return {
        id: request.id,
        status: 200,
        body: JSON.stringify({
          integrations: {
            todoist: {connected: true, access_token: 'secret-todoist'},
            asana: {connected: false, access_token: 'secret-asana'},
            clickup: {connected: true},
          },
          default_app: 'todoist',
        }),
      };
    }
    return {id: request.id, status: 404, body: null};
  });
  const renderer = await renderPage(SettingsPage);
  const tree = textOf(renderer);
  expect(tree).toContain('Task integrations');
  expect(tree).toContain('Todoist · Default');
  expect(tree).toContain('ClickUp');
  expect(tree).not.toContain('Asana');
  expect(tree).not.toContain('secret-todoist');
  expect(tree).not.toContain('Coming Soon');
  expect(labelsOf(renderer).includes('Connect')).toBe(false);
  expect(mockBackend.request).toHaveBeenCalledWith({
    id: expect.any(String),
    method: 'GET',
    expectedApiContract: 'omi',
    path: '/v1/task-integrations',
  });
  expect(
    mockBackend.request.mock.calls.some(call => call[0].method === 'PUT'),
  ).toBe(false);
});

test('Settings names GET integrations without Connect or a write sheet', async () => {
  mockAuth.hasCloudSession.mockResolvedValue(true);
  mockBackend.request.mockImplementation(async request => {
    if (request.path === '/v1/integrations/gmail') {
      return {
        id: request.id,
        status: 200,
        body: JSON.stringify({app_key: 'gmail', connected: true}),
      };
    }
    if (request.path === '/v1/integrations/google_calendar') {
      return {
        id: request.id,
        status: 200,
        body: JSON.stringify({app_key: 'google_calendar', connected: false}),
      };
    }
    if (request.path === '/v1/integrations/apple_health') {
      return {
        id: request.id,
        status: 200,
        body: JSON.stringify({app_key: 'apple_health', connected: true}),
      };
    }
    return {id: request.id, status: 404, body: null};
  });
  const renderer = await renderPage(SettingsPage);
  const tree = textOf(renderer);
  expect(tree).toContain('Integrations');
  expect(tree).toContain('Gmail');
  expect(tree).toContain('Apple Health');
  expect(tree).not.toContain('Google Calendar');
  expect(tree).not.toContain('Coming Soon');
  expect(tree).not.toContain('Disconnect');
  expect(tree).not.toContain('Create your own');
  expect(labelsOf(renderer).includes('Connect')).toBe(false);
  expect(mockBackend.request).toHaveBeenCalledWith({
    id: expect.any(String),
    method: 'GET',
    expectedApiContract: 'omi',
    path: '/v1/integrations/gmail',
  });
  expect(
    mockBackend.request.mock.calls.some(
      call => call[0].method === 'PUT' || call[0].method === 'DELETE',
    ),
  ).toBe(false);
  expect(
    mockBackend.request.mock.calls.some(
      call =>
        typeof call[0].path === 'string' && call[0].path.includes('oauth-url'),
    ),
  ).toBe(false);
});

test('Settings names a failed integrations GET instead of empty success', async () => {
  mockAuth.hasCloudSession.mockResolvedValue(true);
  mockBackend.request.mockImplementation(async request => {
    if (
      typeof request.path === 'string' &&
      request.path.startsWith('/v1/integrations/')
    ) {
      throw Object.assign(new Error('lost'), {code: 'OMI_HTTP_TRANSPORT'});
    }
    return {id: request.id, status: 404, body: null};
  });
  const renderer = await renderPage(SettingsPage);
  const tree = textOf(renderer);
  expect(tree).toContain('Integrations');
  expect(tree).toContain(desktopBackendServiceCopy);
  expect(tree).not.toContain('Gmail');
  expect(labelsOf(renderer).includes('Connect')).toBe(false);
});

test('Settings names GET app changelogs without dismiss or a default icon', async () => {
  mockAuth.hasCloudSession.mockResolvedValue(true);
  mockBackend.request.mockImplementation(async request => {
    if (request.path === '/v1/announcements/changelogs?limit=5') {
      return {
        id: request.id,
        status: 200,
        body: JSON.stringify([
          {
            id: 'ann-1',
            type: 'changelog',
            app_version: '1.2.0',
            content: {
              title: 'Release notes',
              changes: [
                {
                  title: 'Faster sync',
                  description: 'Uploads finish sooner.',
                  icon: '🚀',
                },
                {title: 'Offline replay', description: ''},
              ],
            },
          },
        ]),
      };
    }
    return {id: request.id, status: 404, body: null};
  });
  const renderer = await renderPage(SettingsPage);
  const tree = textOf(renderer);
  expect(tree).toContain("What's New in 1.2.0");
  expect(tree).toContain('🚀 · Faster sync · Uploads finish sooner.');
  expect(tree).toContain('Offline replay');
  expect(tree).not.toContain('Release notes');
  expect(tree).not.toContain('ann-1');
  expect(tree).not.toContain('✨');
  expect(tree).not.toContain('Dismiss');
  expect(mockBackend.request).toHaveBeenCalledWith({
    id: expect.any(String),
    method: 'GET',
    expectedApiContract: 'omi',
    path: '/v1/announcements/changelogs?limit=5',
  });
  expect(
    mockBackend.request.mock.calls.some(
      call => call[0].method === 'POST' || String(call[0].path).includes('dismiss'),
    ),
  ).toBe(false);
});

test('Settings names GET usage monthly yearly all-time without Upgrade', async () => {
  mockAuth.hasCloudSession.mockResolvedValue(true);
  mockBackend.request.mockImplementation(async request => {
    if (request.path === '/v1/users/me/usage?period=monthly') {
      return {
        id: request.id,
        status: 200,
        body: JSON.stringify({
          monthly: {
            transcription_seconds: 180,
            words_transcribed: 40,
            insights_gained: 5,
            memories_created: 2,
            speech_seconds: 99,
          },
        }),
      };
    }
    if (request.path === '/v1/users/me/usage?period=yearly') {
      return {
        id: request.id,
        status: 200,
        body: JSON.stringify({
          yearly: {
            transcription_seconds: 0,
            words_transcribed: 0,
            insights_gained: 0,
            memories_created: 0,
          },
        }),
      };
    }
    if (request.path === '/v1/users/me/usage?period=all_time') {
      return {
        id: request.id,
        status: 200,
        body: JSON.stringify({
          all_time: {
            transcription_seconds: 3600,
            words_transcribed: 80,
            insights_gained: 9,
            memories_created: 4,
          },
        }),
      };
    }
    return {id: request.id, status: 404, body: null};
  });
  const renderer = await renderPage(SettingsPage);
  const tree = textOf(renderer);
  expect(tree).toContain('This month · Listening');
  expect(tree).toContain('3 minutes');
  expect(tree).toContain('This month · Understanding');
  expect(tree).toContain('40 words');
  expect(tree).toContain('This month · Providing');
  expect(tree).toContain('5 insights');
  expect(tree).toContain('This month · Remembering');
  expect(tree).toContain('2 memories');
  expect(tree).toContain('All time · Listening');
  expect(tree).toContain('60 minutes');
  expect(tree).not.toContain('This year ·');
  expect(tree).not.toContain('99');
  expect(tree).not.toContain('Upgrade');
  expect(mockBackend.request).toHaveBeenCalledWith({
    id: expect.any(String),
    method: 'GET',
    expectedApiContract: 'omi',
    path: '/v1/users/me/usage?period=monthly',
  });
  expect(mockBackend.request).toHaveBeenCalledWith({
    id: expect.any(String),
    method: 'GET',
    expectedApiContract: 'omi',
    path: '/v1/users/me/usage?period=yearly',
  });
  expect(mockBackend.request).toHaveBeenCalledWith({
    id: expect.any(String),
    method: 'GET',
    expectedApiContract: 'omi',
    path: '/v1/users/me/usage?period=all_time',
  });
});
