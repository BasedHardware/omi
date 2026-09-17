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
const {developerKeyCreatedCopy, desktopBackendServiceCopy, desktopReadErrorCopy, dailySummaryDefaultHeadlineCopy, appsEmptyCopy, permissionsTitleCopy, fairUseLoadErrorCopy, usageLoadErrorCopy, subscriptionLoadErrorCopy, primaryLanguageNotSetCopy, taskIntegrationsFooterCopy, integrationsFooterCopy} = require('../desktopReadClient');
const {appChangelogsLoadErrorCopy} = require('../legacyOmiAppChangelogs');
const {styles} = require('../ui/styles');

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

function sectionText(
  renderer: ReactTestRenderer.ReactTestRenderer,
  title: string,
): string {
  const heading = renderer.root.find(
    node =>
      node.type === Text &&
      node.props.children === title &&
      node.props.style === styles.destinationSectionTitle,
  );
  return heading.parent
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
    expect(textOf(renderer)).toContain(permissionsTitleCopy());
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

test('Apps names GET empty catalogue Flutter noAppsFound', async () => {
  mockAuth.hasCloudSession.mockResolvedValue(true);
  mockBackend.request.mockImplementation(async request => {
    if (request.path === '/v1/apps') {
      return {id: request.id, status: 200, body: JSON.stringify([])};
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
  expect(tree).toContain(appsEmptyCopy());
  expect(tree).not.toContain('No apps were returned by the catalogue.');
  expect(tree).not.toContain('Unable to fetch apps');
  expect(tree).not.toContain('try adjusting');
  expect(tree).toContain('No installed apps.');
  expect(tree).toContain('No apps owned by this account.');
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
  expect(textOf(renderer)).not.toContain('Not installed');
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
  expect(textOf(renderer)).not.toContain('Not installed');
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
  expect(textOf(renderer)).not.toContain('Not installed');
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
  expect(textOf(renderer)).not.toContain('Not installed');
  expect(textOf(renderer)).not.toContain('\u0085');
});

test('Connectors names Flutter empty GET app names', async () => {
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
  expect(textOf(renderer)).toContain(' \t\n');
  expect(textOf(renderer)).not.toContain('App name unavailable');
  expect(textOf(renderer)).not.toContain('Not installed');
  expect(labelsOf(renderer)).toContain('Install  \t\n');
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
  expect(textOf(renderer)).not.toContain('Not installed');
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
  expect(tree).toContain('New conversation created');
  expect(tree).toContain('Transcript received');
  expect(tree).toContain('Audio data received');
  expect(tree).toContain('Summary generated');
  expect(tree).not.toContain('memory_created');
  expect(tree).not.toContain('realtime_transcript');
  expect(tree).not.toContain('audio_bytes');
  expect(tree).not.toContain('day_summary');
  expect(tree).toContain('Status unavailable');
  expect(tree).not.toContain('Status unknown');
});

test('Settings omits Flutter Profile.build() GET company, job, and data protection', async () => {
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
          company: 'Fixture Company Co',
          job: 'Fixture Job Title',
          data_protection_level: 'standard',
        }),
      };
    }
    return {id: request.id, status: 404, body: null};
  });
  const renderer = await renderPage(SettingsPage);
  const tree = textOf(renderer);
  expect(tree).toContain('Ada');
  expect(tree).toContain('User ID');
  expect(tree).toContain('user-1');
  expect(tree).not.toContain('Company');
  expect(tree).not.toContain('Fixture Company Co');
  expect(tree).not.toContain('Job');
  expect(tree).not.toContain('Fixture Job Title');
  expect(tree).not.toContain('Data protection');
  expect(tree).not.toContain('Standard');
});

test('Settings names Flutter Profile truncated User ID', async () => {
  mockAuth.hasCloudSession.mockResolvedValue(true);
  mockBackend.request.mockImplementation(async request => {
    if (request.path === '/v1/users/profile') {
      return {
        id: request.id,
        status: 200,
        body: JSON.stringify({
          uid: 'firebase-uid-abcdefghijklmnopqrstuvwxyz',
          name: 'Ada',
          email: 'ada@example.com',
        }),
      };
    }
    return {id: request.id, status: 404, body: null};
  });
  const renderer = await renderPage(SettingsPage);
  const tree = textOf(renderer);
  expect(tree).toContain('User ID');
  expect(tree).toContain('fir•••••xyz');
  expect(tree).not.toContain('firebase-uid-abcdefghijklmnopqrstuvwxyz');
  expect(tree).toContain('Ada');
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
  expect(tree).toContain('User ID');
  expect(tree).toContain('user-1');
  expect(tree).not.toContain('Account id');
  expect(tree).not.toContain('Company');
  expect(tree).not.toContain('Job');
  expect(tree).not.toContain('\u0085');
});

test('Settings names Flutter notSet for empty GET name and email', async () => {
  mockAuth.hasCloudSession.mockResolvedValue(true);
  mockBackend.request.mockImplementation(async request => {
    if (request.path === '/v1/users/profile') {
      return {
        id: request.id,
        status: 200,
        body: JSON.stringify({
          uid: 'user-1',
          name: '',
          email: null,
        }),
      };
    }
    return {id: request.id, status: 404, body: null};
  });
  const renderer = await renderPage(SettingsPage);
  const tree = textOf(renderer);
  expect(tree).toContain(primaryLanguageNotSetCopy());
  expect(tree).not.toContain('Name not set on this account.');
  expect(tree).not.toContain('Email not set on this account.');
  expect(tree).toContain('User ID');
  expect(tree).toContain('user-1');
});

test('Settings names Flutter Profile padded GET name instead of remapping to a chip', async () => {
  mockAuth.hasCloudSession.mockResolvedValue(true);
  mockBackend.request.mockImplementation(async request => {
    if (request.path === '/v1/users/profile') {
      return {
        id: request.id,
        status: 200,
        body: JSON.stringify({
          uid: '  user-42  ',
          name: '  Ada  ',
          email: '  ada@example.com  ',
        }),
      };
    }
    return {id: request.id, status: 404, body: null};
  });
  const renderer = await renderPage(SettingsPage);
  const tree = textOf(renderer);
  expect(tree).toContain('  Ada  ');
  expect(tree).toContain('  ada@example.com  ');
  expect(tree).toContain('  u•••••2  ');
  expect(tree).not.toContain('use•••••-42');
  expect(tree).not.toContain('Name not set on this account.');
  expect(tree).not.toContain('Email not set on this account.');
});

test('Settings names Flutter UserProfile fromJson padded GET created_at instead of remapping to a Name chip', async () => {
  mockAuth.hasCloudSession.mockResolvedValue(true);
  mockBackend.request.mockImplementation(async request => {
    if (request.path === '/v1/users/profile') {
      return {
        id: request.id,
        status: 200,
        body: JSON.stringify({
          uid: 'user-1',
          name: 'Ada',
          email: 'ada@example.test',
          created_at: '  2026-09-07T00:00:00.000Z  ',
        }),
      };
    }
    return {id: request.id, status: 404, body: null};
  });
  const renderer = await renderPage(SettingsPage);
  const tree = sectionText(renderer, 'Account');
  expect(tree).toContain(
    desktopReadErrorCopy(new Error('Profile response is malformed')),
  );
  expect(tree).not.toContain('Ada');
  expect(tree).not.toContain('ada@example.test');
  expect(tree).not.toContain('Name');
  expect(tree).not.toContain('Email');
  expect(tree).not.toContain('User ID');
});

test('Settings names Flutter UserProfile fromJson type-wrong GET created_at instead of remapping to a Name chip', async () => {
  mockAuth.hasCloudSession.mockResolvedValue(true);
  mockBackend.request.mockImplementation(async request => {
    if (request.path === '/v1/users/profile') {
      return {
        id: request.id,
        status: 200,
        body: JSON.stringify({
          uid: 'user-1',
          name: 'Ada',
          email: 'ada@example.test',
          created_at: 1,
        }),
      };
    }
    return {id: request.id, status: 404, body: null};
  });
  const renderer = await renderPage(SettingsPage);
  const tree = sectionText(renderer, 'Account');
  expect(tree).toContain(
    desktopReadErrorCopy(new Error('Profile response is malformed')),
  );
  expect(tree).not.toContain('Ada');
  expect(tree).not.toContain('ada@example.test');
  expect(tree).not.toContain('Name');
  expect(tree).not.toContain('Email');
  expect(tree).not.toContain('User ID');
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
            speech_seconds: 99,
          },
        }),
      };
    }
    return {id: request.id, status: 404, body: null};
  });
  const renderer = await renderPage(SettingsPage);
  const tree = textOf(renderer);
  expect(tree).toContain('Today · Listening');
  expect(tree).toContain('2 minutes');
  expect(tree).toContain('Today · Understanding');
  expect(tree).toContain('12 Understanding (words)');
  expect(tree).toContain('Today · Providing');
  expect(tree).toContain('3 Insights');
  expect(tree).toContain('Today · Remembering');
  expect(tree).toContain('1 Memories');
  expect(tree).toContain('Total time Omi has actively listened.');
  expect(tree).toContain('Words understood from your conversations.');
  expect(tree).toContain('Action items, and notes automatically captured.');
  expect(tree).toContain('Facts and details remembered for you.');
  expect(tree).not.toContain('Upgrade');
  expect(tree).not.toContain('99');
});

test('Settings names Flutter UsagePage fromJson invalid GET today speech_seconds instead of empty success', async () => {
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
            speech_seconds: 'bad',
          },
        }),
      };
    }
    return {id: request.id, status: 404, body: null};
  });
  const renderer = await renderPage(SettingsPage);
  const tree = textOf(renderer);
  expect(tree).toContain('Listening');
  expect(tree).toContain(usageLoadErrorCopy());
  expect(tree).not.toContain('Today · Listening');
  expect(tree).not.toContain('2 minutes');
  expect(tree).not.toContain('Upgrade');
});

test('Settings names a failed usage today GET instead of empty success', async () => {
  mockAuth.hasCloudSession.mockResolvedValue(true);
  mockBackend.request.mockImplementation(async request => {
    if (request.path === '/v1/users/me/usage?period=today') {
      throw Object.assign(new Error('lost'), {code: 'OMI_HTTP_TRANSPORT'});
    }
    return {id: request.id, status: 404, body: null};
  });
  const renderer = await renderPage(SettingsPage);
  const tree = textOf(renderer);
  expect(tree).toContain('Listening');
  expect(tree).toContain('Understanding');
  expect(tree).toContain('Providing');
  expect(tree).toContain('Remembering');
  expect(tree).toContain(usageLoadErrorCopy());
  expect(tree).not.toContain(desktopBackendServiceCopy);
  expect(tree).not.toContain('2 minutes');
  expect(tree).not.toContain('Total time Omi has actively listened.');
  expect(tree).not.toContain('Upgrade');
});

test('Settings names HTTP 404 usage today GET Flutter usageLoadError instead of account-settings chrome', async () => {
  mockAuth.hasCloudSession.mockResolvedValue(true);
  mockBackend.request.mockImplementation(async request => {
    if (request.path === '/v1/users/me/usage?period=today') {
      return {id: request.id, status: 404, body: null};
    }
    if (
      typeof request.path === 'string' &&
      request.path.startsWith('/v1/users/me/usage?period=')
    ) {
      return {id: request.id, status: 200, body: '{}'};
    }
    return {id: request.id, status: 404, body: null};
  });
  const renderer = await renderPage(SettingsPage);
  const tree = textOf(renderer);
  expect(tree).toContain('Listening');
  expect(tree).toContain('Understanding');
  expect(tree).toContain('Providing');
  expect(tree).toContain('Remembering');
  expect(tree).toContain(usageLoadErrorCopy());
  expect(tree).not.toContain('This Month');
  expect(tree).not.toContain('2 minutes');
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
          transcription_seconds_used: 0,
          transcription_seconds_limit: 0,
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
  expect(tree).toContain('12 of 10,000 words used this month');
  expect(tree).toContain('Insights this month');
  expect(tree).toContain('3 of 500 insights gained this month');
  expect(tree).toContain('Chat this month');
  expect(tree).toContain('5 Chat');
  expect(tree).toContain('AI chat messages used with Omi this month.');
  expect(tree).toContain('5 of 100 messages used this month');
  expect(tree).not.toContain('Upgrade');
});

test('Settings names Flutter UsagePage empty GET chatQuotaUnit without omitting Chat this month', async () => {
  mockAuth.hasCloudSession.mockResolvedValue(true);
  mockBackend.request.mockImplementation(async request => {
    if (request.path === '/v1/users/me/subscription') {
      return {
        id: request.id,
        status: 200,
        body: JSON.stringify({
          insights_gained_limit: 0,
          insights_gained_used: 0,
          transcription_seconds_limit: 0,
          transcription_seconds_used: 0,
          words_transcribed_limit: 0,
          words_transcribed_used: 0,
          chat_quota_used: 5,
          chat_quota_unit: ' \t',
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
  expect(tree).toContain('Chat this month');
  expect(tree).toContain('5 Chat');
  expect(tree).toContain('AI chat messages used with Omi this month.');
  expect(tree).toContain('5 of 100 messages used this month');
  expect(tree).not.toContain('Upgrade');
});

test('Settings names Flutter UsagePage padded GET chatQuotaUnit as messages', async () => {
  mockAuth.hasCloudSession.mockResolvedValue(true);
  mockBackend.request.mockImplementation(async request => {
    if (request.path === '/v1/users/me/subscription') {
      return {
        id: request.id,
        status: 200,
        body: JSON.stringify({
          insights_gained_limit: 0,
          insights_gained_used: 0,
          transcription_seconds_limit: 0,
          transcription_seconds_used: 0,
          words_transcribed_limit: 0,
          words_transcribed_used: 0,
          chat_quota_used: 5,
          chat_quota_unit: '  cost_usd  ',
          subscription: {
            plan: 'basic',
            status: 'active',
            limits: {chat_questions_per_month: 100, chat_cost_usd_per_month: 20},
          },
        }),
      };
    }
    return {id: request.id, status: 404, body: null};
  });
  const renderer = await renderPage(SettingsPage);
  const tree = textOf(renderer);
  expect(tree).toContain('Chat this month');
  expect(tree).toContain('5 Chat');
  expect(tree).toContain('5 of 100 messages used this month');
  expect(tree).not.toContain('$5.00');
  expect(tree).not.toContain('Upgrade');
});

test('Settings names Flutter UsagePage padded GET chat_quota_used instead of remapping to a Chat this month chip', async () => {
  mockAuth.hasCloudSession.mockResolvedValue(true);
  mockBackend.request.mockImplementation(async request => {
    if (request.path === '/v1/users/me/subscription') {
      return {
        id: request.id,
        status: 200,
        body: JSON.stringify({
          insights_gained_limit: 0,
          insights_gained_used: 0,
          transcription_seconds_limit: 0,
          transcription_seconds_used: 0,
          words_transcribed_limit: 0,
          words_transcribed_used: 0,
          chat_quota_used: '  5.5  ',
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
  expect(tree).toContain(subscriptionLoadErrorCopy());
  expect(tree).not.toContain('5 Chat');
  expect(tree).not.toContain('5.5');
  expect(tree).not.toContain('Chat this month');
  expect(tree).not.toContain('Upgrade');
});

test('Settings names GET subscription transcription quota as minutes this month', async () => {
  mockAuth.hasCloudSession.mockResolvedValue(true);
  mockBackend.request.mockImplementation(async request => {
    if (request.path === '/v1/users/me/subscription') {
      return {
        id: request.id,
        status: 200,
        body: JSON.stringify({
          insights_gained_limit: 0,
          insights_gained_used: 0,
          transcription_seconds_used: 90,
          transcription_seconds_limit: 3600,
          words_transcribed_limit: 0,
          words_transcribed_used: 0,
          subscription: {plan: 'basic', status: 'active'},
        }),
      };
    }
    return {id: request.id, status: 404, body: null};
  });
  const renderer = await renderPage(SettingsPage);
  const tree = textOf(renderer);
  expect(tree).toContain('Free Plan · Active · 2 of 60 min used this month');
  expect(tree).not.toContain('90 / 3600');
  expect(tree).not.toContain('transcribed seconds');
  expect(tree).not.toContain('Upgrade');
});

test('Settings names Flutter UsagePage padded GET status as Inactive', async () => {
  mockAuth.hasCloudSession.mockResolvedValue(true);
  mockBackend.request.mockImplementation(async request => {
    if (request.path === '/v1/users/me/subscription') {
      return {
        id: request.id,
        status: 200,
        body: JSON.stringify({
          insights_gained_limit: 0,
          insights_gained_used: 0,
          transcription_seconds_used: 90,
          transcription_seconds_limit: 3600,
          words_transcribed_limit: 0,
          words_transcribed_used: 0,
          subscription: {plan: 'plus', status: '  active  '},
        }),
      };
    }
    return {id: request.id, status: 404, body: null};
  });
  const renderer = await renderPage(SettingsPage);
  const tree = textOf(renderer);
  expect(tree).toContain('Plus · Inactive · 2 of 60 min used this month');
  expect(tree).not.toContain('Plus · Active');
  expect(tree).not.toContain('Upgrade');
});

test('Settings names Flutter UsagePage padded GET plan as Free Plan', async () => {
  mockAuth.hasCloudSession.mockResolvedValue(true);
  mockBackend.request.mockImplementation(async request => {
    if (request.path === '/v1/users/me/subscription') {
      return {
        id: request.id,
        status: 200,
        body: JSON.stringify({
          insights_gained_limit: 0,
          insights_gained_used: 0,
          transcription_seconds_used: 90,
          transcription_seconds_limit: 3600,
          words_transcribed_limit: 0,
          words_transcribed_used: 0,
          subscription: {plan: '  plus  ', status: 'active'},
        }),
      };
    }
    return {id: request.id, status: 404, body: null};
  });
  const renderer = await renderPage(SettingsPage);
  const tree = textOf(renderer);
  expect(tree).toContain('Free Plan · Active · 2 of 60 min used this month');
  expect(tree).not.toContain('Plus');
  expect(tree).not.toContain('Upgrade');
});

test('Settings names malformed GET subscription Flutter load-error instead of Plan unavailable', async () => {
  mockAuth.hasCloudSession.mockResolvedValue(true);
  mockBackend.request.mockImplementation(async request => {
    if (request.path === '/v1/users/me/subscription') {
      return {id: request.id, status: 200, body: '{'};
    }
    return {id: request.id, status: 404, body: null};
  });
  const renderer = await renderPage(SettingsPage);
  const tree = textOf(renderer);
  expect(tree).toContain(subscriptionLoadErrorCopy());
  expect(tree).not.toContain('Plan is unavailable.');
  expect(tree).not.toContain('Free Plan');
  expect(tree).not.toContain('Upgrade');
});

test('Settings names Flutter UsagePage fromJson invalid GET available_plans instead of Free Plan', async () => {
  mockAuth.hasCloudSession.mockResolvedValue(true);
  mockBackend.request.mockImplementation(async request => {
    if (request.path === '/v1/users/me/subscription') {
      return {
        id: request.id,
        status: 200,
        body: JSON.stringify({
          insights_gained_limit: 0,
          insights_gained_used: 0,
          transcription_seconds_limit: 3600,
          transcription_seconds_used: 90,
          words_transcribed_limit: 0,
          words_transcribed_used: 0,
          available_plans: [{title: 'Plus'}],
          subscription: {plan: 'basic', status: 'active'},
        }),
      };
    }
    return {id: request.id, status: 404, body: null};
  });
  const renderer = await renderPage(SettingsPage);
  const tree = textOf(renderer);
  expect(tree).toContain(subscriptionLoadErrorCopy());
  expect(tree).not.toContain('Free Plan');
  expect(tree).not.toContain('Upgrade');
});

test('Settings omits HTTP 503 subscription GET instead of inventing Plan unavailable', async () => {
  mockAuth.hasCloudSession.mockResolvedValue(true);
  mockBackend.request.mockImplementation(async request => {
    if (request.path === '/v1/users/me/subscription') {
      return {id: request.id, status: 503, body: null};
    }
    return {id: request.id, status: 404, body: null};
  });
  const renderer = await renderPage(SettingsPage);
  const tree = textOf(renderer);
  expect(tree).not.toContain(subscriptionLoadErrorCopy());
  expect(tree).not.toContain('Plan is unavailable.');
  expect(tree).not.toContain('Free Plan');
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
  expect(tree).toContain('Primary Language');
  expect(tree).toContain('English');
  expect(tree).not.toContain('Not set');
});

test('Settings names a failed language GET instead of empty success', async () => {
  mockAuth.hasCloudSession.mockResolvedValue(true);
  mockBackend.request.mockImplementation(async request => {
    if (request.path === '/v1/users/language') {
      throw Object.assign(new Error('lost'), {code: 'OMI_HTTP_TRANSPORT'});
    }
    return {id: request.id, status: 404, body: null};
  });
  const renderer = await renderPage(SettingsPage);
  const tree = textOf(renderer);
  expect(tree).toContain('Primary Language');
  expect(tree).toContain(desktopBackendServiceCopy);
  expect(tree).not.toContain('English');
  expect(tree).not.toContain('Not set');
});

test('Settings names Flutter notSet for empty GET language', async () => {
  mockAuth.hasCloudSession.mockResolvedValue(true);
  mockBackend.request.mockImplementation(async request => {
    if (request.path === '/v1/users/language') {
      return {
        id: request.id,
        status: 200,
        body: JSON.stringify({language: ' \t'}),
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
  expect(tree).toContain('Primary Language');
  expect(tree).toContain('Not set');
});

test('Settings names Flutter notSet for catalog-miss GET language', async () => {
  mockAuth.hasCloudSession.mockResolvedValue(true);
  mockBackend.request.mockImplementation(async request => {
    if (request.path === '/v1/users/language') {
      return {
        id: request.id,
        status: 200,
        body: JSON.stringify({language: 'xx'}),
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
  expect(tree).toContain('Primary Language');
  expect(tree).toContain('Not set');
  expect(tree).not.toContain('xx');
  expect(tree).not.toContain('English');
});

test('Settings names Flutter LanguageSettingsPage padded GET language as Not set', async () => {
  mockAuth.hasCloudSession.mockResolvedValue(true);
  mockBackend.request.mockImplementation(async request => {
    if (request.path === '/v1/users/language') {
      return {
        id: request.id,
        status: 200,
        body: JSON.stringify({language: '  en  '}),
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
  expect(tree).toContain('Primary Language');
  expect(tree).toContain('Not set');
  expect(tree).not.toContain('English');
});

test('Settings names Flutter LanguageSettingsPage empty GET language names', async () => {
  mockAuth.hasCloudSession.mockResolvedValue(true);
  mockBackend.request.mockImplementation(async request => {
    if (request.path === '/v1/users/language') {
      return {
        id: request.id,
        status: 200,
        body: JSON.stringify({language: 'fr'}),
      };
    }
    if (request.path === '/v1/users/available-languages') {
      return {
        id: request.id,
        status: 200,
        body: JSON.stringify({
          languages: [
            {code: 'fr', name: ''},
            {code: 'en', name: 'English'},
          ],
        }),
      };
    }
    return {id: request.id, status: 404, body: null};
  });
  const renderer = await renderPage(SettingsPage);
  const tree = textOf(renderer);
  expect(tree).toContain('Primary Language');
  expect(tree).not.toContain('Not set');
  expect(tree).not.toContain('English');
  expect(tree).not.toContain('fr');
});

test('Settings names Flutter LanguageSettingsPage whitespace GET language names', async () => {
  mockAuth.hasCloudSession.mockResolvedValue(true);
  mockBackend.request.mockImplementation(async request => {
    if (request.path === '/v1/users/language') {
      return {
        id: request.id,
        status: 200,
        body: JSON.stringify({language: 'de'}),
      };
    }
    if (request.path === '/v1/users/available-languages') {
      return {
        id: request.id,
        status: 200,
        body: JSON.stringify({
          languages: [
            {code: 'de', name: ' \t'},
            {code: 'en', name: 'English'},
          ],
        }),
      };
    }
    return {id: request.id, status: 404, body: null};
  });
  const renderer = await renderPage(SettingsPage);
  const tree = textOf(renderer);
  expect(tree).toContain('Primary Language');
  expect(tree).toContain(' \t');
  expect(tree).not.toContain('Not set');
  expect(tree).not.toContain('English');
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
          {id: ' \t', name: 'Whitespace id'},
          {id: '', name: 'Blank id'},
        ]),
      };
    }
    return {id: request.id, status: 404, body: null};
  });
  const renderer = await renderPage(SettingsPage);
  const tree = textOf(renderer);
  expect(tree).toContain('People');
  expect(tree).toContain('Alex Chen');
  expect(tree).toContain('Whitespace id');
  expect(tree).toContain('Blank id');
  expect(tree).not.toContain('person-alex');
  expect(tree).not.toContain('person-empty');
  expect(tree).not.toContain(
    'Create a new person and train Omi to recognize their speech too!',
  );
});

test('Settings names Flutter People.build empty GET names without createPersonHint', async () => {
  mockAuth.hasCloudSession.mockResolvedValue(true);
  mockBackend.request.mockImplementation(async request => {
    if (request.path === '/v1/users/people?include_speech_samples=false') {
      return {
        id: request.id,
        status: 200,
        body: JSON.stringify([{id: 'person-empty', name: ' \t'}]),
      };
    }
    return {id: request.id, status: 404, body: null};
  });
  const renderer = await renderPage(SettingsPage);
  const tree = textOf(renderer);
  expect(tree).toContain('People');
  expect(tree).not.toContain('person-empty');
  expect(tree).not.toContain(
    'Create a new person and train Omi to recognize their speech too!',
  );
  expect(tree).not.toContain('Add New Person');
  expect(tree).not.toContain('Speech Profile');
});

test('Settings names a failed people GET instead of empty success', async () => {
  mockAuth.hasCloudSession.mockResolvedValue(true);
  mockBackend.request.mockImplementation(async request => {
    if (request.path === '/v1/users/people?include_speech_samples=false') {
      throw Object.assign(new Error('lost'), {code: 'OMI_HTTP_TRANSPORT'});
    }
    return {id: request.id, status: 404, body: null};
  });
  const renderer = await renderPage(SettingsPage);
  const tree = textOf(renderer);
  expect(tree).toContain('People');
  expect(tree).toContain(desktopBackendServiceCopy);
  expect(tree).not.toContain('Alex Chen');
  expect(tree).not.toContain('person-alex');
  expect(tree).not.toContain(
    'Create a new person and train Omi to recognize their speech too!',
  );
});

test('Settings names Flutter createPersonHint for empty GET people', async () => {
  mockAuth.hasCloudSession.mockResolvedValue(true);
  mockBackend.request.mockImplementation(async request => {
    if (request.path === '/v1/users/people?include_speech_samples=false') {
      return {id: request.id, status: 200, body: JSON.stringify([])};
    }
    return {id: request.id, status: 404, body: null};
  });
  const renderer = await renderPage(SettingsPage);
  const tree = textOf(renderer);
  expect(tree).toContain('People');
  expect(tree).toContain(
    'Create a new person and train Omi to recognize their speech too!',
  );
  expect(tree).not.toContain(desktopBackendServiceCopy);
  expect(tree).not.toContain('Add New Person');
  expect(tree).not.toContain('Speech Profile');
  expect(tree).not.toContain('How it works?');
});

test('Settings omits Worker 404 people instead of createPersonHint', async () => {
  mockAuth.hasCloudSession.mockResolvedValue(true);
  mockBackend.request.mockImplementation(async request => ({
    id: request.id,
    status: 404,
    body: null,
  }));
  const renderer = await renderPage(SettingsPage);
  const tree = textOf(renderer);
  expect(tree).not.toContain(
    'Create a new person and train Omi to recognize their speech too!',
  );
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
  expect(tree).toContain('Speech Usage');
  expect(tree).toContain('2.4h / 2h');
  expect(tree).toContain('3-Day Rolling');
  expect(tree).toContain('Weekly Rolling');
  expect(tree).toContain('Usage is restricted.');
  expect(tree).toContain('Daily Transcription');
  expect(tree).toContain('30m / 30m');
  expect(tree).toContain('Daily transcription limit reached');
  expect(tree).toMatch(/Resets \d+h/);
  expect(tree).toContain('About Fair Use');
  expect(tree).toContain(
    'Usage is measured by real speech time detected, not connection time.',
  );
  expect(tree).not.toContain('Upgrade');
});

test('Settings names Flutter FairUsePage padded GET speech_hours_today instead of remapping to a hours chip', async () => {
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
          speech_hours_today: '  2.4  ',
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
  expect(tree).toContain(fairUseLoadErrorCopy());
  expect(tree).not.toContain('2.4h / 2h');
  expect(tree).not.toContain('Restricted');
  expect(tree).not.toContain('FU-1');
  expect(tree).not.toContain('About Fair Use');
  expect(tree).not.toContain('Upgrade');
});

test('Settings names Flutter FairUsePage padded GET resets_at instead of remapping to a Resets chip', async () => {
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
            resets_at: '  2099-01-01T00:00:00Z  ',
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
  expect(tree).toContain('2.4h / 2h');
  expect(tree).toContain('Daily transcription limit reached');
  expect(tree).not.toContain('Resets');
  expect(tree).not.toContain('Upgrade');
});

test('Settings names Flutter FairUsePage whitespace GET message without omitting Fair Use', async () => {
  mockAuth.hasCloudSession.mockResolvedValue(true);
  mockBackend.request.mockImplementation(async request => {
    if (request.path === '/v1/fair-use/status') {
      return {
        id: request.id,
        status: 200,
        body: JSON.stringify({
          stage: 'none',
          case_ref: '',
          message: ' \t',
          speech_hours_today: 0,
          speech_hours_3day: 0,
          speech_hours_weekly: 0,
          limits: {
            daily_hours: 2,
            three_day_hours: 8,
            weekly_hours: 10,
          },
          usage_pct: {daily: 0, three_day: 0, weekly: 0},
          dg_budget: {
            daily_limit_ms: 1800000,
            used_ms: 0,
            remaining_ms: 1800000,
            exhausted: false,
            resets_at: '2099-01-01T00:00:00Z',
          },
        }),
      };
    }
    return {id: request.id, status: 404, body: null};
  });
  const renderer = await renderPage(SettingsPage);
  const tree = textOf(renderer);
  expect(
    renderer.root
      .findAllByType(Text)
      .some(node => node.props.children === 'Fair Use'),
  ).toBe(true);
  expect(
    renderer.root
      .findAllByType(Text)
      .some(node => node.props.children === ' \t'),
  ).toBe(true);
  expect(tree).toContain('Speech Usage');
  expect(tree).toContain('About Fair Use');
  expect(tree).not.toContain('Restricted');
  expect(tree).not.toContain('Upgrade');
});

test('Settings names Flutter FairUsePage whitespace GET caseRef without omitting Fair Use', async () => {
  mockAuth.hasCloudSession.mockResolvedValue(true);
  mockBackend.request.mockImplementation(async request => {
    if (request.path === '/v1/fair-use/status') {
      return {
        id: request.id,
        status: 200,
        body: JSON.stringify({
          stage: 'restrict',
          case_ref: ' \t',
          message: '',
          speech_hours_today: 0,
          speech_hours_3day: 0,
          speech_hours_weekly: 0,
          limits: {
            daily_hours: 2,
            three_day_hours: 8,
            weekly_hours: 10,
          },
          usage_pct: {daily: 0, three_day: 0, weekly: 0},
          dg_budget: {
            daily_limit_ms: 1800000,
            used_ms: 0,
            remaining_ms: 1800000,
            exhausted: false,
            resets_at: '2099-01-01T00:00:00Z',
          },
        }),
      };
    }
    return {id: request.id, status: 404, body: null};
  });
  const renderer = await renderPage(SettingsPage);
  const tree = textOf(renderer);
  expect(
    renderer.root
      .findAllByType(Text)
      .some(node => node.props.children === 'Restricted ·  \t'),
  ).toBe(true);
  expect(tree).toContain('Restricted \u00b7 ');
  expect(tree).toContain('Speech Usage');
  expect(tree).toContain('About Fair Use');
  expect(tree).not.toContain('FU-1');
  expect(tree).not.toContain('Upgrade');
});

test('Settings names a failed fair use GET instead of empty success', async () => {
  mockAuth.hasCloudSession.mockResolvedValue(true);
  mockBackend.request.mockImplementation(async request => {
    if (request.path === '/v1/fair-use/status') {
      throw Object.assign(new Error('lost'), {code: 'OMI_HTTP_TRANSPORT'});
    }
    return {id: request.id, status: 404, body: null};
  });
  const renderer = await renderPage(SettingsPage);
  const tree = textOf(renderer);
  expect(tree).toContain('Fair Use');
  expect(tree).toContain(fairUseLoadErrorCopy());
  expect(tree).not.toContain(desktopBackendServiceCopy);
  expect(tree).not.toContain('Restricted');
  expect(tree).not.toContain('FU-1');
  expect(tree).not.toContain('About Fair Use');
  expect(tree).not.toContain('Upgrade');
});

test('Settings names HTTP 404 fair use GET Flutter fairUseLoadError instead of omitting', async () => {
  mockAuth.hasCloudSession.mockResolvedValue(true);
  mockBackend.request.mockImplementation(async request => {
    if (request.path === '/v1/fair-use/status') {
      return {id: request.id, status: 404, body: null};
    }
    return {id: request.id, status: 404, body: null};
  });
  const renderer = await renderPage(SettingsPage);
  const tree = textOf(renderer);
  expect(tree).toContain('Fair Use');
  expect(tree).toContain(fairUseLoadErrorCopy());
  expect(tree).not.toContain('Restricted');
  expect(tree).not.toContain('About Fair Use');
  expect(tree).not.toContain('Upgrade');
});

test('Settings names malformed fair use GET instead of empty success', async () => {
  mockAuth.hasCloudSession.mockResolvedValue(true);
  mockBackend.request.mockImplementation(async request => {
    if (request.path === '/v1/fair-use/status') {
      return {id: request.id, status: 200, body: '{'};
    }
    return {id: request.id, status: 404, body: null};
  });
  const renderer = await renderPage(SettingsPage);
  const tree = textOf(renderer);
  expect(tree).toContain('Fair Use');
  expect(tree).toContain(fairUseLoadErrorCopy());
  expect(tree).not.toContain('Restricted');
  expect(tree).not.toContain('FU-1');
  expect(tree).not.toContain('Upgrade');
});

test('Settings omits Flutter DailySummaryCard unused GET stats emoji and overview', async () => {
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
  expect(tree).not.toContain('🎯');
  expect(tree).not.toContain('3 conversations');
  expect(tree).not.toContain('1h 30m');
  expect(tree).not.toContain('2 action items');
  expect(tree).not.toContain('10m watching');
  expect(tree).not.toContain('1 proactive moment');
  expect(tree).not.toContain('Shipped the recap body.');
  expect(tree).not.toContain('Your Day in Review');
  expect(tree).not.toContain('📅');
  expect(tree).not.toContain('sum-1');
  expect(tree).not.toContain('Regenerate');
  expect(tree).not.toContain('Delivery Time');
  expect(tree).not.toContain('10:00 PM');
  expect(tree).not.toContain('Notification Frequency');
  expect(tree).not.toContain('Custom Vocabulary');
  expect(tree).not.toContain('Automatic Translation');
});

test('Settings names Flutter DailySummaryCard omitted GET headlines as Your Day in Review', async () => {
  mockAuth.hasCloudSession.mockResolvedValue(true);
  mockBackend.request.mockImplementation(async request => {
    if (request.path === '/v1/users/daily-summaries?limit=3&offset=0') {
      return {
        id: request.id,
        status: 200,
        body: JSON.stringify({
          summaries: [
            {id: 'sum-omitted'},
            {id: 'sum-empty', headline: ' \t'},
            {id: 'sum-kept', headline: 'Met with the team'},
          ],
        }),
      };
    }
    return {id: request.id, status: 404, body: null};
  });
  const renderer = await renderPage(SettingsPage);
  const tree = textOf(renderer);
  expect(tree).toContain('Daily summary');
  expect(tree).toContain(dailySummaryDefaultHeadlineCopy());
  expect(tree).toContain('Met with the team');
  expect(tree).not.toContain('📅');
  expect(tree).not.toContain('Regenerate');
});

test('Settings names Flutter DailySummaryCard empty GET ids without omitting Daily summary', async () => {
  mockAuth.hasCloudSession.mockResolvedValue(true);
  mockBackend.request.mockImplementation(async request => {
    if (request.path === '/v1/users/daily-summaries?limit=3&offset=0') {
      return {
        id: request.id,
        status: 200,
        body: JSON.stringify({
          summaries: [
            {id: '', date: '2026-09-08', headline: 'Empty id'},
            {id: ' \t', date: '2026-09-07', headline: 'Whitespace id'},
            {id: '  padded  ', date: '2026-09-06', headline: 'Padded id'},
          ],
        }),
      };
    }
    return {id: request.id, status: 404, body: null};
  });
  const renderer = await renderPage(SettingsPage);
  const tree = textOf(renderer);
  expect(tree).toContain('Daily summary');
  expect(tree).toContain('Empty id');
  expect(tree).toContain('Whitespace id');
  expect(tree).toContain('Padded id');
  expect(tree).not.toContain('Your Day in Review');
  expect(tree).not.toContain('Regenerate');
});

test('Settings names Flutter DailySummaryCard empty GET dates without omitting Daily summary', async () => {
  mockAuth.hasCloudSession.mockResolvedValue(true);
  mockBackend.request.mockImplementation(async request => {
    if (request.path === '/v1/users/daily-summaries?limit=3&offset=0') {
      return {
        id: request.id,
        status: 200,
        body: JSON.stringify({
          summaries: [
            {id: 'sum-empty-date', date: '', headline: 'Empty date'},
            {id: 'sum-whitespace-date', date: ' \t', headline: 'Whitespace date'},
            {id: 'sum-padded-date', date: '  padded  ', headline: 'Padded date'},
          ],
        }),
      };
    }
    return {id: request.id, status: 404, body: null};
  });
  const renderer = await renderPage(SettingsPage);
  const tree = textOf(renderer);
  expect(tree).toContain('Daily summary');
  expect(tree).toContain('Empty date');
  expect(tree).toContain(' \t · Whitespace date');
  expect(tree).toContain('padded');
  expect(tree).toContain('Padded date');
  expect(tree).not.toContain('Your Day in Review');
  expect(tree).not.toContain('Regenerate');
});

test('Settings names Flutter DailySummaryCard empty GET headlines without omitting Daily summary', async () => {
  mockAuth.hasCloudSession.mockResolvedValue(true);
  mockBackend.request.mockImplementation(async request => {
    if (request.path === '/v1/users/daily-summaries?limit=3&offset=0') {
      return {
        id: request.id,
        status: 200,
        body: JSON.stringify({
          summaries: [{id: 'sum-empty', headline: ' \t'}],
        }),
      };
    }
    return {id: request.id, status: 404, body: null};
  });
  const renderer = await renderPage(SettingsPage);
  const tree = textOf(renderer);
  expect(tree).toContain('Daily summary');
  expect(tree).not.toContain('sum-empty');
  expect(tree).not.toContain('Your Day in Review');
  expect(tree).not.toContain('Regenerate');
});

test('Settings names a failed daily summaries GET instead of empty success', async () => {
  mockAuth.hasCloudSession.mockResolvedValue(true);
  mockBackend.request.mockImplementation(async request => {
    if (request.path === '/v1/users/daily-summaries?limit=3&offset=0') {
      throw Object.assign(new Error('lost'), {code: 'OMI_HTTP_TRANSPORT'});
    }
    return {id: request.id, status: 404, body: null};
  });
  const renderer = await renderPage(SettingsPage);
  const tree = textOf(renderer);
  expect(tree).toContain('Daily summary');
  expect(tree).toContain(desktopBackendServiceCopy);
  expect(tree).not.toContain('Met with the team');
  expect(tree).not.toContain('Your Day in Review');
  expect(tree).not.toContain('Regenerate');
});

test('Settings names Flutter DailySummary.fromGenerated type-wrong GET created_at instead of remapping to a headline chip', async () => {
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
              created_at: 1,
            },
            {id: 'sum-kept', date: '2026-09-08', headline: 'Neighbor recap'},
          ],
        }),
      };
    }
    return {id: request.id, status: 404, body: null};
  });
  const renderer = await renderPage(SettingsPage);
  const tree = textOf(renderer);
  expect(tree).toContain('Fair Use');
  expect(tree).not.toContain('Daily summary');
  expect(tree).not.toContain('Met with the team');
  expect(tree).not.toContain('Neighbor recap');
  expect(tree).not.toContain('Your Day in Review');
  expect(tree).not.toContain('Regenerate');
});

test('Settings names Flutter DailySummary.fromGenerated type-wrong GET headline instead of remapping to a headline chip', async () => {
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
              headline: 1,
            },
            {id: 'sum-kept', date: '2026-09-08', headline: 'Neighbor recap'},
          ],
        }),
      };
    }
    return {id: request.id, status: 404, body: null};
  });
  const renderer = await renderPage(SettingsPage);
  const tree = textOf(renderer);
  expect(tree).toContain('Fair Use');
  expect(tree).not.toContain('Daily summary');
  expect(tree).not.toContain('Met with the team');
  expect(tree).not.toContain('Neighbor recap');
  expect(tree).not.toContain('Your Day in Review');
  expect(tree).not.toContain('Regenerate');
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
  expect(tree).toContain('Daily Summary');
  expect(tree).toContain('Enabled');
  expect(tree).toContain('Delivery Time');
  expect(tree).toContain('10:00 PM');
  expect(tree).toContain(
    "Get a personalized summary of your day's conversations delivered as a notification.",
  );
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

test('Settings names a failed daily-summary-settings GET instead of empty success', async () => {
  mockAuth.hasCloudSession.mockResolvedValue(true);
  mockBackend.request.mockImplementation(async request => {
    if (request.path === '/v1/users/daily-summary-settings') {
      throw Object.assign(new Error('lost'), {code: 'OMI_HTTP_TRANSPORT'});
    }
    return {id: request.id, status: 404, body: null};
  });
  const renderer = await renderPage(SettingsPage);
  const tree = textOf(renderer);
  expect(tree).toContain('Daily Summary');
  expect(tree).toContain(desktopBackendServiceCopy);
  expect(tree).not.toContain('Enabled');
  expect(tree).not.toContain('10:00 PM');
  expect(tree).not.toContain('Your Day in Review');
  expect(tree).not.toContain(
    "Get a personalized summary of your day's conversations delivered as a notification.",
  );
});

test('Settings names Flutter DailySummarySettings fromJson padded GET hour instead of omitting Daily Summary', async () => {
  mockAuth.hasCloudSession.mockResolvedValue(true);
  mockBackend.request.mockImplementation(async request => {
    if (request.path === '/v1/users/daily-summary-settings') {
      return {
        id: request.id,
        status: 200,
        body: JSON.stringify({enabled: true, hour: '  22  '}),
      };
    }
    return {id: request.id, status: 404, body: null};
  });
  const renderer = await renderPage(SettingsPage);
  const tree = textOf(renderer);
  expect(tree).toContain('Daily Summary');
  expect(tree).toContain(
    desktopReadErrorCopy(
      new Error('Omi daily summary settings are malformed'),
    ),
  );
  expect(tree).not.toContain('Enabled');
  expect(tree).not.toContain('10:00 PM');
  expect(tree).not.toContain('Your Day in Review');
  expect(tree).not.toContain(
    "Get a personalized summary of your day's conversations delivered as a notification.",
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
  expect(tree).toContain('Notification Frequency');
  expect(tree).toContain('Minimal');
  expect(tree).toContain('Only critical reminders');
  expect(tree).toContain(
    'Control how often Omi sends you proactive notifications and reminders.',
  );
  expect(tree).not.toContain('Balanced');
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

test('Settings names a failed mentor notification GET instead of empty success', async () => {
  mockAuth.hasCloudSession.mockResolvedValue(true);
  mockBackend.request.mockImplementation(async request => {
    if (request.path === '/v1/users/mentor-notification-settings') {
      throw Object.assign(new Error('lost'), {code: 'OMI_HTTP_TRANSPORT'});
    }
    return {id: request.id, status: 404, body: null};
  });
  const renderer = await renderPage(SettingsPage);
  const tree = textOf(renderer);
  expect(tree).toContain('Notification Frequency');
  expect(tree).toContain(desktopBackendServiceCopy);
  expect(tree).not.toContain('Minimal');
  expect(tree).not.toContain('Balanced');
  expect(tree).not.toContain(
    'Control how often Omi sends you proactive notifications and reminders.',
  );
});

test('Settings names Flutter MentorNotificationSettings fromJson padded GET frequency instead of omitting Notification Frequency', async () => {
  mockAuth.hasCloudSession.mockResolvedValue(true);
  mockBackend.request.mockImplementation(async request => {
    if (request.path === '/v1/users/mentor-notification-settings') {
      return {
        id: request.id,
        status: 200,
        body: JSON.stringify({frequency: '  3  '}),
      };
    }
    return {id: request.id, status: 404, body: null};
  });
  const renderer = await renderPage(SettingsPage);
  const tree = textOf(renderer);
  expect(tree).toContain('Notification Frequency');
  expect(tree).toContain(
    desktopReadErrorCopy(
      new Error('Omi mentor notification settings are malformed'),
    ),
  );
  expect(tree).not.toContain('Minimal');
  expect(tree).not.toContain('Balanced');
  expect(tree).not.toContain(
    'Control how often Omi sends you proactive notifications and reminders.',
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
  expect(tree).toContain('Custom Vocabulary');
  expect(tree).toContain('Omi');
  expect(tree).toContain('Based Hardware');
  expect(tree).toContain('Automatic Translation');
  expect(tree).toContain('Off');
  expect(tree).toContain('Detect 10+ languages');
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

test('Settings names Flutter TranscriptionPreferences fromJson type-wrong GET custom_stt_since instead of remapping to a language chip', async () => {
  mockAuth.hasCloudSession.mockResolvedValue(true);
  mockBackend.request.mockImplementation(async request => {
    if (request.path === '/v1/users/transcription-preferences') {
      return {
        id: request.id,
        status: 200,
        body: JSON.stringify({
          vocabulary: ['Based Hardware'],
          single_language_mode: true,
          custom_stt_since: 1,
        }),
      };
    }
    return {id: request.id, status: 404, body: null};
  });
  const renderer = await renderPage(SettingsPage);
  const tree = textOf(renderer);
  expect(tree).not.toContain('Based Hardware');
  expect(tree).not.toContain('Detect 10+ languages');
  expect(tree).not.toContain('Off');
});

test('Settings names a failed transcription-preferences GET instead of empty success', async () => {
  mockAuth.hasCloudSession.mockResolvedValue(true);
  mockBackend.request.mockImplementation(async request => {
    if (request.path === '/v1/users/transcription-preferences') {
      throw Object.assign(new Error('lost'), {code: 'OMI_HTTP_TRANSPORT'});
    }
    return {id: request.id, status: 404, body: null};
  });
  const renderer = await renderPage(SettingsPage);
  const tree = textOf(renderer);
  expect(tree).toContain('Automatic Translation');
  expect(tree).toContain('Custom Vocabulary');
  expect(tree).toContain(desktopBackendServiceCopy);
  expect(tree).not.toContain('Based Hardware');
  expect(tree).not.toContain('Add Words');
  expect(tree).not.toContain('Detect 10+ languages');
});

test('Settings names Flutter omitted GET single_language_mode as Automatic Translation Enabled', async () => {
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
  expect(tree).toContain('Custom Vocabulary');
  expect(tree).toContain('Omi');
  expect(tree).toContain('Automatic Translation');
  expect(tree).toContain('Enabled');
  expect(tree).toContain('Detect 10+ languages');
});

test('Settings names Flutter developer webhook empty GET URLs', async () => {
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
  expect(tree).toContain(' \t\n');
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
  expect(tree).toContain('New conversation created');
  expect(tree).toContain('Transcript received');
  expect(tree).toContain('Audio data received');
  expect(tree).toContain('Summary generated');
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

test('Settings names a failed developer webhook URLs GET instead of empty success', async () => {
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
    if (request.path.startsWith('/v1/users/developer/webhook/')) {
      throw Object.assign(new Error('lost'), {code: 'OMI_HTTP_TRANSPORT'});
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
  expect(tree).toContain('Webhooks');
  expect(tree).toContain(desktopBackendServiceCopy);
  expect(tree).not.toContain('https://example.test/conversation');
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
  expect(tree).toContain('Developer API');
  expect(tree).not.toContain('Developer key');
  expect(tree).toContain(`Local · omi_sk_ab*** · ${created} · Full Access`);
  expect(tree).not.toContain('omi_mcp_cd***');
  expect(tree).toContain('MCP');
  expect(tree).not.toContain('MCP key');
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

test('Settings names Flutter DevApiKeyListItem padded GET scopes without Read', async () => {
  mockAuth.hasCloudSession.mockResolvedValue(true);
  mockBackend.request.mockImplementation(async request => {
    if (request.path === '/v1/dev/keys') {
      return {
        id: request.id,
        status: 200,
        body: JSON.stringify([
          {
            id: 'dev-padded',
            name: 'Padded',
            key_prefix: 'omi_sk_ab',
            created_at: '2026-09-09T12:00:00.000Z',
            scopes: ['  conversations:read  '],
          },
          {
            id: 'dev-exact',
            name: 'Exact',
            key_prefix: 'omi_sk_cd',
            created_at: '2026-09-09T12:00:00.000Z',
            scopes: ['conversations:read'],
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
            scopes: ['  conversations:read  '],
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
  expect(tree).toContain(`Padded · omi_sk_ab*** · ${created}`);
  expect(tree).not.toContain(`Padded · omi_sk_ab*** · ${created} · Read`);
  expect(tree).toContain(`Exact · omi_sk_cd*** · ${created} · Read`);
  expect(tree).toContain('Cursor · omi_mcp_cd');
  expect(tree).not.toContain('Cursor · omi_mcp_cd · Read');
  expect(tree).not.toContain('Full Access');
  expect(tree).not.toContain('Read Only');
  expect(tree).not.toContain('Revoke');
});

test('Settings names GET developer-key empty scopes Read Only without inventing it on MCP keys', async () => {
  mockAuth.hasCloudSession.mockResolvedValue(true);
  mockBackend.request.mockImplementation(async request => {
    if (request.path === '/v1/dev/keys') {
      return {
        id: request.id,
        status: 200,
        body: JSON.stringify([
          {
            id: 'dev-empty',
            name: 'Readonly',
            key_prefix: 'omi_sk_ro',
            created_at: '2026-09-09T12:00:00.000Z',
            scopes: [],
          },
          {
            id: 'dev-omitted',
            name: 'Omitted',
            key_prefix: 'omi_sk_om',
            created_at: '2026-09-09T12:00:00.000Z',
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
            scopes: [],
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
  expect(tree).toContain(`Readonly · omi_sk_ro*** · ${created} · Read Only`);
  expect(tree).toContain(`Omitted · omi_sk_om*** · ${created} · Read Only`);
  expect(tree).not.toContain('omi_mcp_cd***');
  expect(tree).toContain('Cursor · omi_mcp_cd');
  expect(tree).not.toContain('Cursor · omi_mcp_cd · Read Only');
  expect(tree).not.toContain('Revoke');
});

test('Settings names a failed developer and MCP keys GET instead of empty success', async () => {
  mockAuth.hasCloudSession.mockResolvedValue(true);
  mockBackend.request.mockImplementation(async request => {
    if (request.path === '/v1/dev/keys' || request.path === '/v1/mcp/keys') {
      throw Object.assign(new Error('lost'), {code: 'OMI_HTTP_TRANSPORT'});
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
  expect(tree).toContain('Developer API');
  expect(tree).not.toContain('Developer key');
  expect(tree).toContain('MCP');
  expect(tree).not.toContain('MCP key');
  expect(tree).toContain(desktopBackendServiceCopy);
  expect(tree).not.toContain('omi_sk_abcdef_secret');
  expect(tree).not.toContain('Revoke');
  expect(tree).not.toContain('Create');
  expect(tree).not.toContain('No API keys yet');
});

test('Settings names HTTP 500 developer and MCP keys GET instead of empty success', async () => {
  mockAuth.hasCloudSession.mockResolvedValue(true);
  mockBackend.request.mockImplementation(async request => {
    if (request.path === '/v1/dev/keys' || request.path === '/v1/mcp/keys') {
      return {id: request.id, status: 500, body: '{"error":"internal"}'};
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
  expect(tree).toContain('Developer API');
  expect(tree).not.toContain('Developer key');
  expect(tree).toContain('MCP');
  expect(tree).not.toContain('MCP key');
  expect(tree).toContain(
    desktopReadErrorCopy(new Error('Omi developer keys are malformed')),
  );
  expect(tree).not.toContain('omi_sk_abcdef_secret');
  expect(tree).not.toContain('Revoke');
  expect(tree).not.toContain('Create');
  expect(tree).not.toContain('No API keys yet');
});

test('Settings names Flutter DevApiKey fromJson invalid created_at instead of undated success', async () => {
  mockAuth.hasCloudSession.mockResolvedValue(true);
  mockBackend.request.mockImplementation(async request => {
    if (request.path === '/v1/dev/keys') {
      return {
        id: request.id,
        status: 200,
        body: JSON.stringify([
          {
            id: 'key-undated',
            name: 'Legacy',
            key_prefix: 'omi_sk_ef',
            created_at: 'not-a-date',
          },
          {
            id: 'key-kept',
            name: 'Cursor',
            key_prefix: 'omi_sk_cd',
            created_at: '2026-09-09T12:00:00.000Z',
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
  expect(tree).toContain('Developer API');
  expect(tree).toContain(
    desktopReadErrorCopy(new Error('Omi developer keys are malformed')),
  );
  expect(tree).not.toContain('Legacy');
  expect(tree).not.toContain('Cursor');
  expect(tree).not.toContain('omi_sk_ef');
  expect(tree).not.toContain('No API keys yet');
  expect(tree).not.toContain('Revoke');
});

test('Settings names Flutter DevApiKey fromJson invalid GET last_used_at instead of empty success', async () => {
  mockAuth.hasCloudSession.mockResolvedValue(true);
  mockBackend.request.mockImplementation(async request => {
    if (request.path === '/v1/dev/keys') {
      return {
        id: request.id,
        status: 200,
        body: JSON.stringify([
          {
            id: 'key-used',
            name: 'Legacy',
            key_prefix: 'omi_sk_ef',
            created_at: '2026-09-09T12:00:00.000Z',
            last_used_at: 'not-a-date',
          },
          {
            id: 'key-kept',
            name: 'Cursor',
            key_prefix: 'omi_sk_cd',
            created_at: '2026-09-09T12:00:00.000Z',
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
  expect(tree).toContain('Developer API');
  expect(tree).toContain(
    desktopReadErrorCopy(new Error('Omi developer keys are malformed')),
  );
  expect(tree).not.toContain('Legacy');
  expect(tree).not.toContain('Cursor');
  expect(tree).not.toContain('omi_sk_ef');
  expect(tree).not.toContain('No API keys yet');
  expect(tree).not.toContain('Revoke');
});

test('Settings names Flutter McpApiKeyListItem empty GET keyPrefix without omitting MCP', async () => {
  mockAuth.hasCloudSession.mockResolvedValue(true);
  mockBackend.request.mockImplementation(async request => {
    if (request.path === '/v1/mcp/keys') {
      return {
        id: request.id,
        status: 200,
        body: JSON.stringify([
          {id: 'mcp-empty', name: 'Cursor', key_prefix: '', created_at: '2026-09-09T12:00:00.000Z'},
          {id: 'mcp-whitespace', name: 'Whitespace prefix', key_prefix: ' \t', created_at: '2026-09-09T12:00:00.000Z'},
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
  expect(tree).toContain('MCP');
  expect(tree).toContain('Cursor \u00b7 ');
  expect(tree).toContain('Whitespace prefix \u00b7  \t');
  expect(tree).not.toContain('mcp-empty');
  expect(tree).not.toContain('***');
  expect(tree).not.toContain('No API keys yet');
  expect(tree).not.toContain('Revoke');
  expect(tree).not.toContain('Create Key');
});

test('Settings names Flutter DevApiKeyListItem empty GET names without noApiKeys', async () => {
  mockAuth.hasCloudSession.mockResolvedValue(true);
  mockBackend.request.mockImplementation(async request => {
    if (request.path === '/v1/dev/keys') {
      return {
        id: request.id,
        status: 200,
        body: JSON.stringify([
          {id: 'key-empty', name: ' \t', key_prefix: 'omi_sk_cd', created_at: '2026-09-09T12:00:00.000Z'},
        ]),
      };
    }
    if (request.path === '/v1/mcp/keys') {
      return {
        id: request.id,
        status: 200,
        body: JSON.stringify([
          {id: 'mcp-empty', name: '', key_prefix: 'omi_mcp_cd', created_at: '2026-09-09T12:00:00.000Z'},
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
  expect(tree).toContain('Developer API');
  expect(tree).toContain(' \t \u00b7 omi_sk_cd***');
  expect(tree).not.toContain('key-empty');
  expect(tree).toContain('MCP');
  expect(tree).toContain(' \u00b7 omi_mcp_cd');
  expect(tree).not.toContain('omi_mcp_cd***');
  expect(tree).not.toContain('mcp-empty');
  expect(tree).not.toContain('No API keys yet');
  expect(tree).not.toContain('Revoke');
  expect(tree).not.toContain('Create Key');
});

test('Settings names Flutter DevApiKeyListItem empty GET ids without noApiKeys', async () => {
  mockAuth.hasCloudSession.mockResolvedValue(true);
  mockBackend.request.mockImplementation(async request => {
    if (request.path === '/v1/dev/keys') {
      return {
        id: request.id,
        status: 200,
        body: JSON.stringify([
          {
            id: ' \t',
            name: 'Whitespace id',
            key_prefix: 'omi_sk_ws',
            created_at: '2026-09-09T12:00:00.000Z',
          },
          {
            id: '',
            name: 'Blank id',
            key_prefix: 'omi_sk_bl',
            created_at: '2026-09-09T12:00:00.000Z',
          },
          {
            id: 'key-neighbor',
            name: 'Neighbor',
            key_prefix: 'omi_sk_nb',
            created_at: '2026-09-09T12:00:00.000Z',
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
            id: '\u0085',
            name: 'Next line id',
            key_prefix: 'omi_mcp_nl',
            created_at: '2026-09-09T12:00:00.000Z',
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
  expect(tree).toContain('Developer API');
  expect(tree).toContain('Whitespace id \u00b7 omi_sk_ws***');
  expect(tree).toContain('Blank id \u00b7 omi_sk_bl***');
  expect(tree).toContain('Neighbor \u00b7 omi_sk_nb***');
  expect(tree).toContain('MCP');
  expect(tree).toContain('Next line id \u00b7 omi_mcp_nl');
  expect(tree).not.toContain('No API keys yet');
  expect(tree).not.toContain('Revoke');
  expect(tree).not.toContain('Create Key');
});

test('Settings names Flutter noApiKeys for empty GET developer and MCP keys', async () => {
  mockAuth.hasCloudSession.mockResolvedValue(true);
  mockBackend.request.mockImplementation(async request => {
    if (request.path === '/v1/dev/keys' || request.path === '/v1/mcp/keys') {
      return {id: request.id, status: 200, body: JSON.stringify([])};
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
  expect(tree).toContain('Developer API');
  expect(tree).not.toContain('Developer key');
  expect(tree).toContain('MCP');
  expect(tree).not.toContain('MCP key');
  expect(tree).toContain('No API keys yet');
  expect(tree).toContain('Create a key to get started');
  expect(tree).not.toContain(desktopBackendServiceCopy);
  expect(tree).not.toContain('Create Key');
  expect(tree).not.toContain('Revoke');
});

test('Settings names HTTP 404 developer and MCP keys GET Flutter error instead of omitting', async () => {
  mockAuth.hasCloudSession.mockResolvedValue(true);
  mockBackend.request.mockImplementation(async request => ({
    id: request.id,
    status: 404,
    body: null,
  }));
  const renderer = await renderPage(SettingsPage);
  await act(async () => {
    renderer.root
      .find(node => node.props.accessibilityLabel === 'Developer settings')
      .props.onPress();
  });
  const tree = textOf(renderer);
  expect(tree).toContain('Developer API');
  expect(tree).toContain('MCP');
  expect(tree).toContain(
    desktopReadErrorCopy(new Error('Omi developer keys are malformed')),
  );
  expect(tree).not.toContain('No API keys yet');
  expect(tree).not.toContain('Create');
  expect(tree).not.toContain('Revoke');
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
  expect(tree).toContain('Completed · 3 conversations · 2 conversations');
  expect(tree).toContain(
    'Processing · Estimated: Less than a minute remaining · 3/10',
  );
  expect(tree).toContain('Failed · Zip could not be read.');
  expect(tree).toContain('Pending');
  expect(tree).not.toContain('queued');
  expect(tree).not.toContain('job-1');
  expect(tree).not.toContain('No imports yet');
  expect(tree).not.toContain('Limitless');
  expect(tree).not.toContain('Coming Soon');
  expect(tree).not.toContain('Delete Imported Data');
  expect(tree).not.toContain('Start import');
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

test('Settings names a failed import jobs GET instead of empty success', async () => {
  mockAuth.hasCloudSession.mockResolvedValue(true);
  mockBackend.request.mockImplementation(async request => {
    if (request.path === '/v1/import/jobs?limit=50') {
      throw Object.assign(new Error('lost'), {code: 'OMI_HTTP_TRANSPORT'});
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
  expect(tree).toContain(desktopBackendServiceCopy);
  expect(tree).not.toContain('job-1');
  expect(tree).not.toContain('No imports yet');
  expect(tree).not.toContain('Limitless');
});

test('Settings names Flutter ImportHistoryPage padded GET status as Pending', async () => {
  mockAuth.hasCloudSession.mockResolvedValue(true);
  mockBackend.request.mockImplementation(async request => {
    if (request.path === '/v1/import/jobs?limit=50') {
      return {
        id: request.id,
        status: 200,
        body: JSON.stringify([
          {
            job_id: 'job-padded-processing',
            status: '  processing  ',
            processed_files: 3,
            total_files: 10,
          },
          {
            job_id: 'job-padded-completed',
            status: '  completed  ',
            created_at: '2026-09-10T14:30:00.000Z',
            conversations_created: 3,
            total_files: 4,
          },
          {
            job_id: 'job-padded-failed',
            status: '  failed  ',
            error: 'Zip could not be read.',
          },
          {
            job_id: 'job-exact-processing',
            status: 'processing',
            processed_files: 1,
            total_files: 2,
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
  expect(tree).toContain('Import Data');
  expect(tree).toContain(
    'Pending · Estimated: Less than a minute remaining · 3/10',
  );
  expect(tree).toContain(
    'Pending · 3 conversations · Estimated: Less than a minute remaining · 0/4',
  );
  expect(tree).toContain('Pending · Zip could not be read.');
  expect(tree).toContain(
    'Processing · Estimated: Less than a minute remaining · 1/2',
  );
  expect(tree).not.toContain('Completed');
  expect(tree).not.toContain('Failed');
  expect(tree).not.toContain('job-padded-processing');
  expect(tree).not.toContain('No imports yet');
  expect(tree).not.toContain('Limitless');
  expect(tree).not.toContain('Start import');
});

test('Settings names Flutter ImportHistoryPage padded GET created_at', async () => {
  mockAuth.hasCloudSession.mockResolvedValue(true);
  mockBackend.request.mockImplementation(async request => {
    if (request.path === '/v1/import/jobs?limit=50') {
      return {
        id: request.id,
        status: 200,
        body: JSON.stringify([
          {
            job_id: 'job-padded',
            status: 'completed',
            created_at: '  2026-09-10T14:30:00.000Z  ',
            conversations_created: 2,
          },
          {
            job_id: 'job-trailing',
            status: 'completed',
            created_at: '2026-09-10T14:30:00.000Z ',
            conversations_created: 3,
          },
          {
            job_id: 'job-next-line',
            status: 'completed',
            created_at: '\u00852026-09-10T14:30:00.000Z',
            conversations_created: 4,
          },
          {
            job_id: 'job-exact',
            status: 'completed',
            created_at: '2026-09-10T14:30:00.000Z',
            conversations_created: 1,
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
  expect(tree).toContain('Import Data');
  expect(tree).toContain('Completed · 2 conversations');
  expect(tree).toContain('Completed · 3 conversations');
  expect(tree).toContain('Completed · 4 conversations');
  expect(tree).toMatch(/Completed · .+ at .+ · 1 conversations/);
  expect(tree).not.toContain('job-padded');
  expect(tree).not.toContain('No imports yet');
  expect(tree).not.toContain('Limitless');
  expect(tree).not.toContain('Start import');
});

test('Settings names Flutter ImportJobResponse.fromJson type-wrong GET created_at instead of remapping to a Completed chip', async () => {
  mockAuth.hasCloudSession.mockResolvedValue(true);
  mockBackend.request.mockImplementation(async request => {
    if (request.path === '/v1/import/jobs?limit=50') {
      return {
        id: request.id,
        status: 200,
        body: JSON.stringify([
          {
            job_id: 'job-numeric-clock',
            status: 'completed',
            created_at: 1,
            conversations_created: 3,
          },
          {
            job_id: 'job-neighbor',
            status: 'failed',
            error: 'Zip could not be read.',
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
  expect(tree).toContain('Import Data');
  expect(tree).toContain('No imports yet');
  expect(tree).not.toContain('Completed');
  expect(tree).not.toContain('Failed');
  expect(tree).not.toContain('Zip could not be read.');
  expect(tree).not.toContain('3 conversations');
  expect(tree).not.toContain('Limitless');
  expect(tree).not.toContain('Start import');
});

test('Settings names Flutter ImportHistoryPage empty GET error without omitting Import Data', async () => {
  mockAuth.hasCloudSession.mockResolvedValue(true);
  mockBackend.request.mockImplementation(async request => {
    if (request.path === '/v1/import/jobs?limit=50') {
      return {
        id: request.id,
        status: 200,
        body: JSON.stringify([
          {job_id: 'job-empty-error', status: 'failed', error: ''},
          {job_id: 'job-whitespace-error', status: 'failed', error: ' \t'},
          {job_id: 'job-padded-error', status: 'failed', error: '  padded  '},
          {job_id: 'job-omitted-error', status: 'failed'},
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
  expect(tree).toContain('Failed · ');
  expect(tree).toContain('Failed ·  \t');
  expect(tree).toContain('padded');
  expect(tree).toContain('Failed');
  expect(tree).not.toContain('job-empty-error');
  expect(tree).not.toContain('No imports yet');
  expect(tree).not.toContain('Limitless');
  expect(tree).not.toContain('Start import');
});

test('Settings names Flutter ImportHistoryPage empty GET ids without noImportsYet', async () => {
  mockAuth.hasCloudSession.mockResolvedValue(true);
  mockBackend.request.mockImplementation(async request => {
    if (request.path === '/v1/import/jobs?limit=50') {
      return {
        id: request.id,
        status: 200,
        body: JSON.stringify([
          {job_id: ' \t', status: 'failed', error: 'Zip could not be read.'},
          {job_id: '', status: 'queued'},
          {job_id: 'job-neighbor', status: 'completed', conversations_created: 1},
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
  expect(tree).toContain('Failed · Zip could not be read.');
  expect(tree).toContain('Pending');
  expect(tree).toContain('Completed · 1 conversations');
  expect(tree).not.toContain('job-neighbor');
  expect(tree).not.toContain('No imports yet');
  expect(tree).not.toContain('Limitless');
  expect(tree).not.toContain('Start import');
});

test('Settings names Flutter noImportsYet for empty GET import jobs', async () => {
  mockAuth.hasCloudSession.mockResolvedValue(true);
  mockBackend.request.mockImplementation(async request => {
    if (request.path === '/v1/import/jobs?limit=50') {
      return {id: request.id, status: 200, body: JSON.stringify([])};
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
  expect(tree).toContain('No imports yet');
  expect(tree).not.toContain(desktopBackendServiceCopy);
  expect(tree).not.toContain('Limitless');
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
            category: 'productivity-and-organization',
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
  expect(tree).not.toContain('productivity-and-organization');
  expect(tree).not.toContain('Productivity and organization');
});

test('Connectors Explore and Installed omit Flutter unused install-state and Connected meta', async () => {
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
            rating_avg: 4.5,
            rating_count: 12,
          },
          {
            id: 'catalog-app-2',
            name: 'Catalog fixture app',
            enabled: false,
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
  const explore = sectionText(renderer, 'Explore');
  const installed = sectionText(renderer, 'Installed');
  expect(explore).toContain('Owned app');
  expect(explore).toContain('Catalog fixture app');
  expect(explore).toContain('4.5 · 12 ratings');
  expect(explore).not.toContain('Installed');
  expect(explore).not.toContain('Not installed');
  expect(explore).not.toContain('Connected');
  expect(installed).toContain('Owned app');
  expect(installed).toContain('4.5 (12)');
  expect(installed).not.toContain('Not installed');
  expect(installed).not.toContain('Connected');
  expect(tree).not.toContain('acct-1');
  expect(tree).not.toContain('Not installed');
  expect(labelsOf(renderer)).toContain('Remove Owned app');
  expect(labelsOf(renderer)).toContain('Install Catalog fixture app');
});

test('Connectors names Flutter FilterSheet myApps as Created by me', async () => {
  mockAuth.hasCloudSession.mockResolvedValue(true);
  mockBackend.request.mockImplementation(async request => {
    if (request.path === '/v1/apps') {
      return {
        id: request.id,
        status: 200,
        body: JSON.stringify([
          {
            id: 'catalog-app-owned',
            name: 'Owned app',
            uid: 'user-1',
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
  expect(tree).toContain('Created by me');
  expect(sectionText(renderer, 'Created by me')).toContain('Owned app');
  expect(tree).not.toContain('My Apps');
  expect(tree).not.toContain('No apps owned by this account.');
});

test('Connectors Explore omits CategorySection private and Installed names AppListItem lock', async () => {
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
        body: JSON.stringify(['catalog-app-private']),
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
  expect(sectionText(renderer, 'Explore')).toContain('Owned app');
  expect(sectionText(renderer, 'Explore')).not.toContain('🔒');
  expect(sectionText(renderer, 'Explore')).not.toContain('Private');
  expect(sectionText(renderer, 'Installed')).toContain('Owned app 🔒');
  expect(sectionText(renderer, 'Installed')).not.toContain('Private');
  expect(tree).toContain('Catalog fixture app');
  expect(tree).not.toContain('Private ·');
  expect(tree).not.toContain('Official');
});

test('Connectors Explore names Flutter CategorySection GET category and Installed omits it', async () => {
  mockAuth.hasCloudSession.mockResolvedValue(true);
  mockBackend.request.mockImplementation(async request => {
    if (request.path === '/v1/apps') {
      return {
        id: request.id,
        status: 200,
        body: JSON.stringify([
          {
            id: 'catalog-app-explore',
            name: 'Explore fixture app',
            category: 'productivity-and-organization',
          },
          {
            id: 'catalog-app-installed',
            name: 'Owned app',
            category: 'health-and-wellness',
          },
        ]),
      };
    }
    if (request.path === '/v1/apps/enabled') {
      return {
        id: request.id,
        status: 200,
        body: JSON.stringify(['catalog-app-installed']),
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
  expect(tree).toContain('Explore fixture app');
  expect(tree).toContain('Productivity');
  expect(tree).toContain('Owned app');
  expect(sectionText(renderer, 'Explore')).toContain('Health');
  expect(sectionText(renderer, 'Installed')).toContain('Owned app');
  expect(sectionText(renderer, 'Installed')).not.toContain('Health');
  expect(tree).not.toContain('productivity-and-organization');
  expect(tree).not.toContain('health-and-wellness');
  expect(tree).not.toContain('Official');
});

test('Connectors Explore names Flutter CategorySection empty GET category and Installed omits it', async () => {
  mockAuth.hasCloudSession.mockResolvedValue(true);
  mockBackend.request.mockImplementation(async request => {
    if (request.path === '/v1/apps') {
      return {
        id: request.id,
        status: 200,
        body: JSON.stringify([
          {
            id: 'catalog-app-explore',
            name: 'Explore fixture app',
            category: '',
          },
          {
            id: 'catalog-app-whitespace',
            name: 'Whitespace category app',
            category: ' \t',
          },
          {
            id: 'catalog-app-installed',
            name: 'Owned app',
            category: 'health-and-wellness',
          },
        ]),
      };
    }
    if (request.path === '/v1/apps/enabled') {
      return {
        id: request.id,
        status: 200,
        body: JSON.stringify(['catalog-app-installed']),
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
  expect(sectionText(renderer, 'Explore')).toContain('Explore fixture app');
  expect(sectionText(renderer, 'Explore')).toContain('Whitespace category app');
  expect(sectionText(renderer, 'Explore')).toContain('Health');
  expect(sectionText(renderer, 'Installed')).toContain('Owned app');
  expect(sectionText(renderer, 'Installed')).not.toContain('Health');
  const exploreHeading = renderer.root.find(
    node =>
      node.type === Text &&
      node.props.children === 'Explore' &&
      node.props.style === styles.destinationSectionTitle,
  );
  expect(
    exploreHeading.parent
      .findAll(
        node => node.type === Text && node.props.numberOfLines === 1,
      )
      .map(node => node.props.children),
  ).toEqual(['', ' \t', 'Health']);
  const installedHeading = renderer.root.find(
    node =>
      node.type === Text &&
      node.props.children === 'Installed' &&
      node.props.style === styles.destinationSectionTitle,
  );
  expect(
    installedHeading.parent.findAll(
      node => node.type === Text && node.props.numberOfLines === 1,
    ),
  ).toHaveLength(0);
  expect(textOf(renderer)).not.toContain('Not installed');
});

test('Connectors Explore names Flutter CategorySection padded GET category', async () => {
  mockAuth.hasCloudSession.mockResolvedValue(true);
  mockBackend.request.mockImplementation(async request => {
    if (request.path === '/v1/apps') {
      return {
        id: request.id,
        status: 200,
        body: JSON.stringify([
          {
            id: 'catalog-app-exact',
            name: 'Exact category app',
            category: 'health-and-wellness',
          },
          {
            id: 'catalog-app-padded',
            name: 'Padded category app',
            category: '  health-and-wellness  ',
          },
          {
            id: 'catalog-app-trailing',
            name: 'Trailing category app',
            category: 'health-and-wellness ',
          },
          {
            id: 'catalog-app-next-line',
            name: 'Next-line category app',
            category: '\u0085health-and-wellness',
          },
          {
            id: 'catalog-app-installed',
            name: 'Owned app',
            category: '  health-and-wellness  ',
          },
        ]),
      };
    }
    if (request.path === '/v1/apps/enabled') {
      return {
        id: request.id,
        status: 200,
        body: JSON.stringify(['catalog-app-installed']),
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
  expect(tree).toContain('Exact category app');
  expect(tree).toContain('Padded category app');
  expect(tree).toContain('Trailing category app');
  expect(tree).toContain('Next-line category app');
  expect(tree).toContain('Owned app');
  expect(sectionText(renderer, 'Explore')).toContain('Health');
  expect(sectionText(renderer, 'Explore')).toContain('  health And Wellness  ');
  expect(sectionText(renderer, 'Explore')).toContain('Health And Wellness ');
  expect(sectionText(renderer, 'Explore')).toContain(
    '\u0085health And Wellness',
  );
  expect(sectionText(renderer, 'Installed')).toContain('Owned app');
  expect(sectionText(renderer, 'Installed')).not.toContain('Health');
  expect(sectionText(renderer, 'Installed')).not.toContain(
    '  health And Wellness  ',
  );
  const exploreHeading = renderer.root.find(
    node =>
      node.type === Text &&
      node.props.children === 'Explore' &&
      node.props.style === styles.destinationSectionTitle,
  );
  expect(
    exploreHeading.parent
      .findAll(
        node => node.type === Text && node.props.numberOfLines === 1,
      )
      .map(node => node.props.children),
  ).toEqual([
    'Health',
    '  health And Wellness  ',
    'Health And Wellness ',
    '\u0085health And Wellness',
    '  health And Wellness  ',
  ]);
  expect(tree).not.toContain('health-and-wellness');
  expect(textOf(renderer)).not.toContain('Not installed');
});

test('Connectors list cards omit GET author like Flutter CategorySection and AppListItem', async () => {
  mockAuth.hasCloudSession.mockResolvedValue(true);
  mockBackend.request.mockImplementation(async request => {
    if (request.path === '/v1/apps') {
      return {
        id: request.id,
        status: 200,
        body: JSON.stringify([
          {
            id: 'catalog-app-explore',
            name: 'Explore fixture app',
            author: 'Fixture Author Co',
          },
          {
            id: 'catalog-app-installed',
            name: 'Owned app',
            author: 'Fixture Author Co',
          },
        ]),
      };
    }
    if (request.path === '/v1/apps/enabled') {
      return {
        id: request.id,
        status: 200,
        body: JSON.stringify(['catalog-app-installed']),
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
  expect(tree).toContain('Explore fixture app');
  expect(tree).toContain('Owned app');
  expect(tree).not.toContain('Fixture Author Co');
  expect(sectionText(renderer, 'Explore')).not.toContain('Fixture Author Co');
  expect(sectionText(renderer, 'Installed')).not.toContain('Fixture Author Co');
  expect(tree).not.toContain('Official');
});

test('Connectors Installed names Flutter AppListItem truncated GET descriptions and Explore omits them', async () => {
  mockAuth.hasCloudSession.mockResolvedValue(true);
  const exploreDescription =
    'Explore-only calendar notes that CategorySection must not paint.';
  const installedDescription = `${'A'.repeat(50)}Z`;
  mockBackend.request.mockImplementation(async request => {
    if (request.path === '/v1/apps') {
      return {
        id: request.id,
        status: 200,
        body: JSON.stringify([
          {
            id: 'catalog-app-explore',
            name: 'Explore fixture app',
            description: exploreDescription,
          },
          {
            id: 'catalog-app-installed',
            name: 'Owned app',
            description: installedDescription,
          },
        ]),
      };
    }
    if (request.path === '/v1/apps/enabled') {
      return {
        id: request.id,
        status: 200,
        body: JSON.stringify(['catalog-app-installed']),
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
  expect(tree).toContain('Explore fixture app');
  expect(tree).not.toContain(exploreDescription);
  expect(tree).toContain('Owned app');
  expect(tree).toContain(`${'A'.repeat(50)}...`);
  expect(tree).not.toContain(installedDescription);
});

test('Connectors names Flutter AppListItem empty GET ids without hiding neighbors', async () => {
  mockAuth.hasCloudSession.mockResolvedValue(true);
  mockBackend.request.mockImplementation(async request => {
    if (request.path === '/v1/apps') {
      return {
        id: request.id,
        status: 200,
        body: JSON.stringify([
          {id: '', name: 'Blank id'},
          {id: ' \t', name: 'Whitespace id'},
          {id: '\u0085', name: 'Next line id'},
          {id: '  padded  ', name: 'Padded id'},
          {id: 'catalog-app-1', name: 'Owned app'},
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
  expect(tree).toContain('Blank id');
  expect(tree).toContain('Whitespace id');
  expect(tree).toContain('Next line id');
  expect(tree).toContain('Padded id');
  expect(tree).toContain('Owned app');
  expect(tree).not.toContain(appsEmptyCopy());
  expect(tree).not.toContain('Apps response item');
  expect(tree).not.toContain('malformed');
});

test('Connectors Installed names Flutter AppListItem empty GET descriptions and Explore omits them', async () => {
  mockAuth.hasCloudSession.mockResolvedValue(true);
  mockBackend.request.mockImplementation(async request => {
    if (request.path === '/v1/apps') {
      return {
        id: request.id,
        status: 200,
        body: JSON.stringify([
          {
            id: 'catalog-app-explore',
            name: 'Explore fixture app',
            description: ' \t',
          },
          {
            id: 'catalog-app-installed',
            name: 'Owned app',
            description: '',
          },
          {
            id: 'catalog-app-whitespace',
            name: 'Whitespace app',
            description: ' \t',
          },
        ]),
      };
    }
    if (request.path === '/v1/apps/enabled') {
      return {
        id: request.id,
        status: 200,
        body: JSON.stringify([
          'catalog-app-installed',
          'catalog-app-whitespace',
        ]),
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
  expect(sectionText(renderer, 'Explore')).toContain('Explore fixture app');
  expect(sectionText(renderer, 'Installed')).toContain('Owned app');
  expect(sectionText(renderer, 'Installed')).toContain('Whitespace app');
  const installedHeading = renderer.root.find(
    node =>
      node.type === Text &&
      node.props.children === 'Installed' &&
      node.props.style === styles.destinationSectionTitle,
  );
  const installedDescriptions = installedHeading.parent.findAll(
    node => node.type === Text && node.props.numberOfLines === 2,
  );
  expect(installedDescriptions.map(node => node.props.children)).toEqual([
    '',
    ' \t',
  ]);
  const exploreHeading = renderer.root.find(
    node =>
      node.type === Text &&
      node.props.children === 'Explore' &&
      node.props.style === styles.destinationSectionTitle,
  );
  expect(
    exploreHeading.parent.findAll(
      node => node.type === Text && node.props.numberOfLines === 2,
    ),
  ).toHaveLength(0);
  expect(textOf(renderer)).not.toContain('Not installed');
});

test('Connectors Explore names Flutter CategorySection ratings and Installed keeps list (N)', async () => {
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
        body: JSON.stringify(['catalog-app-rated']),
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
  expect(tree).toContain('4.5 · 12 ratings');
  expect(tree).toContain('4.5 (12)');
  expect(tree).toContain('Catalog fixture app');
  expect(tree).not.toContain('0.0');
  expect(tree).not.toContain('Official');
});

test('Connectors Explore names Flutter AppListItem padded GET rating_avg instead of remapping to a rating chip', async () => {
  mockAuth.hasCloudSession.mockResolvedValue(true);
  mockBackend.request.mockImplementation(async request => {
    if (request.path === '/v1/apps') {
      return {
        id: request.id,
        status: 200,
        body: JSON.stringify([
          {
            id: 'catalog-app-padded',
            name: 'Padded rating app',
            rating_avg: '  4.5  ',
            rating_count: 12,
          },
          {
            id: 'catalog-app-rated',
            name: 'Owned app',
            rating_avg: '4.5',
            rating_count: 12,
          },
        ]),
      };
    }
    if (request.path === '/v1/apps/enabled') {
      return {
        id: request.id,
        status: 200,
        body: JSON.stringify(['catalog-app-rated']),
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
  const explore = sectionText(renderer, 'Explore');
  const installed = sectionText(renderer, 'Installed');
  expect(explore).toContain('Padded rating app');
  expect(explore).toContain('Owned app');
  expect(installed).toContain('Owned app');
  expect(installed).not.toContain('Padded rating app');
  expect(explore).toContain('4.5 · 12 ratings');
  expect(installed).toContain('4.5 (12)');
  expect(
    renderer.root.findAll(node => node.props.children === '4.5 · 12 ratings')
      .length,
  ).toBe(2);
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

test('Connectors rows name Flutter AppListItem padded GET image instead of remapping to a CDN chip', async () => {
  mockAuth.hasCloudSession.mockResolvedValue(true);
  mockBackend.request.mockImplementation(async request => {
    if (request.path === '/v1/apps') {
      return {
        id: request.id,
        status: 200,
        body: JSON.stringify([
          {
            id: 'catalog-app-padded',
            name: 'Padded image app',
            image: '  https://cdn.example.test/app.png  ',
          },
          {
            id: 'catalog-app-https',
            name: 'Uppercase image app',
            image: 'HTTPS://cdn.example.test/app.png',
          },
          {
            id: 'catalog-app-exact',
            name: 'Exact image app',
            image: 'https://cdn.example.test/app.png',
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
  expect(tree).toContain('Padded image app');
  expect(tree).toContain('Uppercase image app');
  expect(tree).toContain('Exact image app');
  const exactImages = renderer.root.findAll(
    node =>
      node.props.accessibilityLabel === 'App image' &&
      node.props.source?.uri === 'https://cdn.example.test/app.png',
  );
  const cdnImages = renderer.root.findAll(
    node =>
      node.props.accessibilityLabel === 'App image' &&
      typeof node.props.source?.uri === 'string' &&
      node.props.source.uri.includes('cdn.example.test/app.png'),
  );
  expect(exactImages.length).toBeGreaterThan(0);
  expect(cdnImages.length).toBe(exactImages.length);
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
  expect(tree).toContain('Task Integrations');
  expect(tree).toContain('Todoist · Default');
  expect(tree).toContain('ClickUp');
  expect(tree).toContain(taskIntegrationsFooterCopy());
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

test('Settings names Flutter TaskIntegrationsPage padded GET integration keys', async () => {
  mockAuth.hasCloudSession.mockResolvedValue(true);
  mockBackend.request.mockImplementation(async request => {
    if (request.path === '/v1/task-integrations') {
      return {
        id: request.id,
        status: 200,
        body: JSON.stringify({
          integrations: {
            todoist: {connected: true},
            '  todoist  ': {connected: true},
          },
          default_app: '  todoist  ',
        }),
      };
    }
    return {id: request.id, status: 404, body: null};
  });
  const renderer = await renderPage(SettingsPage);
  const tree = textOf(renderer);
  expect(tree).toContain('Task Integrations');
  expect(tree).toContain('Todoist');
  expect(tree).not.toContain('Todoist · Default');
  expect(tree).toContain('  todoist   · Default');
  expect(tree).toContain(taskIntegrationsFooterCopy());
  expect(tree).not.toContain('Coming Soon');
  expect(labelsOf(renderer).includes('Connect')).toBe(false);
});

test('Settings names a failed task-integrations GET instead of empty success', async () => {
  mockAuth.hasCloudSession.mockResolvedValue(true);
  mockBackend.request.mockImplementation(async request => {
    if (request.path === '/v1/task-integrations') {
      throw Object.assign(new Error('lost'), {code: 'OMI_HTTP_TRANSPORT'});
    }
    return {id: request.id, status: 404, body: null};
  });
  const renderer = await renderPage(SettingsPage);
  const tree = textOf(renderer);
  expect(tree).toContain('Task Integrations');
  expect(tree).toContain(desktopBackendServiceCopy);
  expect(tree).not.toContain('Todoist');
  expect(tree).not.toContain('secret-todoist');
  expect(tree).not.toContain(taskIntegrationsFooterCopy());
  expect(labelsOf(renderer).includes('Connect')).toBe(false);
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
  expect(tree).toContain(integrationsFooterCopy());
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
  expect(tree).not.toContain(integrationsFooterCopy());
  expect(labelsOf(renderer).includes('Connect')).toBe(false);
});

test('Settings names Flutter ChangelogSheet empty GET app_version as What\'s New in ', async () => {
  mockAuth.hasCloudSession.mockResolvedValue(true);
  mockBackend.request.mockImplementation(async request => {
    if (request.path === '/v1/announcements/changelogs?limit=5') {
      return {
        id: request.id,
        status: 200,
        body: JSON.stringify([
          {
            id: 'ann-empty-version',
            type: 'changelog',
            created_at: '2026-09-09T12:00:00.000Z',
            app_version: '',
            content: {changes: [{title: 'Offline replay', description: ''}]},
          },
        ]),
      };
    }
    return {id: request.id, status: 404, body: null};
  });
  const renderer = await renderPage(SettingsPage);
  const tree = textOf(renderer);
  expect(tree).toContain("What's New in ");
  expect(tree).toContain('✨ · Offline replay · ');
  expect(tree).not.toContain('ann-empty-version');
  expect(tree).not.toContain("What's New in 1.2.0");
  expect(tree).not.toContain('Dismiss');
});

test('Settings names Flutter ChangelogSheet padded GET app_version instead of remapping to a version chip', async () => {
  mockAuth.hasCloudSession.mockResolvedValue(true);
  mockBackend.request.mockImplementation(async request => {
    if (request.path === '/v1/announcements/changelogs?limit=5') {
      return {
        id: request.id,
        status: 200,
        body: JSON.stringify([
          {
            id: 'ann-exact',
            type: 'changelog',
            created_at: '2026-09-09T12:00:00.000Z',
            app_version: '1.2.0',
            content: {changes: [{title: 'Exact version', description: ''}]},
          },
          {
            id: 'ann-padded',
            type: 'changelog',
            created_at: '2026-09-09T12:00:00.000Z',
            app_version: '  1.2.0  ',
            content: {changes: [{title: 'Padded version', description: ''}]},
          },
          {
            id: 'ann-trail',
            type: 'changelog',
            created_at: '2026-09-09T12:00:00.000Z',
            app_version: '1.2.0 ',
            content: {changes: [{title: 'Trailing version', description: ''}]},
          },
        ]),
      };
    }
    return {id: request.id, status: 404, body: null};
  });
  const renderer = await renderPage(SettingsPage);
  const tree = textOf(renderer);
  expect(tree).toContain("What's New in 1.2.0");
  expect(tree).toContain("What's New in   1.2.0  ");
  expect(tree).toContain("What's New in 1.2.0 ");
  expect(tree).toContain('✨ · Exact version · ');
  expect(tree).toContain('✨ · Padded version · ');
  expect(tree).toContain('✨ · Trailing version · ');
  expect(tree).not.toContain('Dismiss');
});

test('Settings names Flutter ChangelogSheet empty GET ids without omitting What\'s New', async () => {
  mockAuth.hasCloudSession.mockResolvedValue(true);
  mockBackend.request.mockImplementation(async request => {
    if (request.path === '/v1/announcements/changelogs?limit=5') {
      return {
        id: request.id,
        status: 200,
        body: JSON.stringify([
          {
            id: ' \t',
            type: 'changelog',
            created_at: '2026-09-09T12:00:00.000Z',
            app_version: '1.3.0',
            content: {changes: [{title: 'Whitespace id', description: ''}]},
          },
          {
            id: '',
            type: 'changelog',
            created_at: '2026-09-09T12:00:00.000Z',
            app_version: '1.5.0',
            content: {changes: [{title: 'Blank id', description: ''}]},
          },
          {
            id: 'ann-neighbor',
            type: 'changelog',
            created_at: '2026-09-09T12:00:00.000Z',
            app_version: '1.2.0',
            content: {changes: [{title: 'Faster sync', description: ''}]},
          },
        ]),
      };
    }
    return {id: request.id, status: 404, body: null};
  });
  const renderer = await renderPage(SettingsPage);
  const tree = textOf(renderer);
  expect(tree).toContain("What's New in 1.3.0");
  expect(tree).toContain('✨ · Whitespace id · ');
  expect(tree).toContain("What's New in 1.5.0");
  expect(tree).toContain('✨ · Blank id · ');
  expect(tree).toContain("What's New in 1.2.0");
  expect(tree).toContain('✨ · Faster sync · ');
  expect(tree).not.toContain(appChangelogsLoadErrorCopy());
  expect(tree).not.toContain('ann-neighbor');
  expect(tree).not.toContain('Dismiss');
});

test('Settings names Flutter ChangelogSheet empty GET change titles without omitting What\'s New', async () => {
  mockAuth.hasCloudSession.mockResolvedValue(true);
  mockBackend.request.mockImplementation(async request => {
    if (request.path === '/v1/announcements/changelogs?limit=5') {
      return {
        id: request.id,
        status: 200,
        body: JSON.stringify([
          {
            id: 'ann-empty',
            type: 'changelog',
            created_at: '2026-09-09T12:00:00.000Z',
            app_version: '1.2.0',
            content: {
              changes: [{title: '  ', description: 'Hidden empty title.'}],
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
  expect(tree).toContain('✨ ·    · Hidden empty title.');
  expect(tree).not.toContain('ann-empty');
  expect(tree).not.toContain('Dismiss');
});

test('Settings names Flutter ChangelogSheet empty GET descriptions without omitting What\'s New', async () => {
  mockAuth.hasCloudSession.mockResolvedValue(true);
  mockBackend.request.mockImplementation(async request => {
    if (request.path === '/v1/announcements/changelogs?limit=5') {
      return {
        id: request.id,
        status: 200,
        body: JSON.stringify([
          {
            id: 'ann-empty-desc',
            type: 'changelog',
            created_at: '2026-09-09T12:00:00.000Z',
            app_version: '1.2.0',
            content: {
              changes: [
                {title: 'Offline replay', description: ''},
                {title: 'Whitespace description', description: ' \t'},
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
  expect(tree).toContain('✨ · Offline replay · ');
  expect(tree).toContain('✨ · Whitespace description ·  \t');
  expect(tree).not.toContain('ann-empty-desc');
  expect(tree).not.toContain('Dismiss');
});

test('Settings names Flutter ChangelogSheet empty GET icons without omitting What\'s New', async () => {
  mockAuth.hasCloudSession.mockResolvedValue(true);
  mockBackend.request.mockImplementation(async request => {
    if (request.path === '/v1/announcements/changelogs?limit=5') {
      return {
        id: request.id,
        status: 200,
        body: JSON.stringify([
          {
            id: 'ann-empty-icon',
            type: 'changelog',
            created_at: '2026-09-09T12:00:00.000Z',
            app_version: '1.2.0',
            content: {
              changes: [
                {title: 'Empty icon', description: 'Kept description.', icon: ''},
                {
                  title: 'Whitespace icon',
                  description: 'Kept description.',
                  icon: ' \t',
                },
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
  expect(tree).toContain(' · Empty icon · Kept description.');
  expect(tree).toContain(' \t · Whitespace icon · Kept description.');
  expect(tree).not.toContain('✨ · Empty icon');
  expect(tree).not.toContain('ann-empty-icon');
  expect(tree).not.toContain('Dismiss');
});

test('Settings names GET app changelogs without dismiss', async () => {
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
            created_at: '2026-09-09T12:00:00.000Z',
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
  expect(tree).toContain('✨ · Offline replay · ');
  expect(tree).not.toContain('Release notes');
  expect(tree).not.toContain('ann-1');
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

test('Settings names a failed app changelogs GET instead of empty success', async () => {
  mockAuth.hasCloudSession.mockResolvedValue(true);
  mockBackend.request.mockImplementation(async request => {
    if (request.path === '/v1/announcements/changelogs?limit=5') {
      throw Object.assign(new Error('lost'), {code: 'OMI_HTTP_TRANSPORT'});
    }
    return {id: request.id, status: 404, body: null};
  });
  const renderer = await renderPage(SettingsPage);
  const tree = textOf(renderer);
  expect(tree).toContain("What's New");
  expect(tree).toContain(appChangelogsLoadErrorCopy());
  expect(tree).not.toContain(desktopBackendServiceCopy);
  expect(tree).not.toContain("What's New in 1.2.0");
  expect(tree).not.toContain('Dismiss');
  expect(tree).not.toContain('✨');
});

test('Settings names Flutter ChangelogSheet unknown GET type instead of empty success', async () => {
  mockAuth.hasCloudSession.mockResolvedValue(true);
  mockBackend.request.mockImplementation(async request => {
    if (request.path === '/v1/announcements/changelogs?limit=5') {
      return {
        id: request.id,
        status: 200,
        body: JSON.stringify([
          {
            id: 'ann-unknown',
            type: ' \t',
            created_at: '2026-09-09T12:00:00.000Z',
            app_version: '1.2.0',
            content: {changes: [{title: 'Skip me', description: ''}]},
          },
          {
            id: 'ann-good',
            type: 'changelog',
            created_at: '2026-09-09T12:00:00.000Z',
            app_version: '1.2.0',
            content: {changes: [{title: 'Offline replay', description: ''}]},
          },
        ]),
      };
    }
    return {id: request.id, status: 404, body: null};
  });
  const renderer = await renderPage(SettingsPage);
  const tree = textOf(renderer);
  expect(tree).toContain("What's New");
  expect(tree).toContain(appChangelogsLoadErrorCopy());
  expect(tree).not.toContain("What's New in 1.2.0");
  expect(tree).not.toContain('Offline replay');
  expect(tree).not.toContain('Dismiss');
  expect(tree).not.toContain('✨');
});

test('Settings names Flutter ChangelogSheet fromJson invalid created_at instead of undated success', async () => {
  mockAuth.hasCloudSession.mockResolvedValue(true);
  mockBackend.request.mockImplementation(async request => {
    if (request.path === '/v1/announcements/changelogs?limit=5') {
      return {
        id: request.id,
        status: 200,
        body: JSON.stringify([
          {
            id: 'ann-undated',
            type: 'changelog',
            created_at: 'not-a-date',
            app_version: '1.2.0',
            content: {changes: [{title: 'Skip me', description: ''}]},
          },
          {
            id: 'ann-good',
            type: 'changelog',
            created_at: '2026-09-09T12:00:00.000Z',
            app_version: '1.2.0',
            content: {changes: [{title: 'Offline replay', description: ''}]},
          },
        ]),
      };
    }
    return {id: request.id, status: 404, body: null};
  });
  const renderer = await renderPage(SettingsPage);
  const tree = textOf(renderer);
  expect(tree).toContain("What's New");
  expect(tree).toContain(appChangelogsLoadErrorCopy());
  expect(tree).not.toContain("What's New in 1.2.0");
  expect(tree).not.toContain('Offline replay');
  expect(tree).not.toContain('Skip me');
  expect(tree).not.toContain('Dismiss');
  expect(tree).not.toContain('✨');
});

test('Settings names Flutter ChangelogSheet fromJson missing GET content instead of empty success', async () => {
  mockAuth.hasCloudSession.mockResolvedValue(true);
  mockBackend.request.mockImplementation(async request => {
    if (request.path === '/v1/announcements/changelogs?limit=5') {
      return {
        id: request.id,
        status: 200,
        body: JSON.stringify([
          {
            id: 'ann-feature',
            type: 'feature',
            created_at: '2026-09-09T12:00:00.000Z',
            app_version: '1.2.0',
          },
          {
            id: 'ann-good',
            type: 'changelog',
            created_at: '2026-09-09T12:00:00.000Z',
            app_version: '1.2.0',
            content: {changes: [{title: 'Offline replay', description: ''}]},
          },
        ]),
      };
    }
    return {id: request.id, status: 404, body: null};
  });
  const renderer = await renderPage(SettingsPage);
  const tree = textOf(renderer);
  expect(tree).toContain("What's New");
  expect(tree).toContain(appChangelogsLoadErrorCopy());
  expect(tree).not.toContain("What's New in 1.2.0");
  expect(tree).not.toContain('Offline replay');
  expect(tree).not.toContain('Dismiss');
  expect(tree).not.toContain('✨');
});

test('Settings names Flutter ChangelogSheet fromJson invalid GET active instead of empty success', async () => {
  mockAuth.hasCloudSession.mockResolvedValue(true);
  mockBackend.request.mockImplementation(async request => {
    if (request.path === '/v1/announcements/changelogs?limit=5') {
      return {
        id: request.id,
        status: 200,
        body: JSON.stringify([
          {
            id: 'ann-feature',
            type: 'feature',
            created_at: '2026-09-09T12:00:00.000Z',
            app_version: '1.2.0',
            active: 'yes',
            content: {title: 'Feature'},
          },
          {
            id: 'ann-good',
            type: 'changelog',
            created_at: '2026-09-09T12:00:00.000Z',
            app_version: '1.2.0',
            content: {changes: [{title: 'Offline replay', description: ''}]},
          },
        ]),
      };
    }
    return {id: request.id, status: 404, body: null};
  });
  const renderer = await renderPage(SettingsPage);
  const tree = textOf(renderer);
  expect(tree).toContain("What's New");
  expect(tree).toContain(appChangelogsLoadErrorCopy());
  expect(tree).not.toContain("What's New in 1.2.0");
  expect(tree).not.toContain('Offline replay');
  expect(tree).not.toContain('Dismiss');
  expect(tree).not.toContain('✨');
});

test('Settings names Flutter ChangelogSheet fromGenerated unknown GET trigger instead of empty success', async () => {
  mockAuth.hasCloudSession.mockResolvedValue(true);
  mockBackend.request.mockImplementation(async request => {
    if (request.path === '/v1/announcements/changelogs?limit=5') {
      return {
        id: request.id,
        status: 200,
        body: JSON.stringify([
          {
            id: 'ann-trigger',
            type: 'changelog',
            created_at: '2026-09-09T12:00:00.000Z',
            app_version: '1.2.0',
            targeting: {trigger: 'bogus'},
            content: {changes: [{title: 'Skip me', description: ''}]},
          },
          {
            id: 'ann-good',
            type: 'changelog',
            created_at: '2026-09-09T12:00:00.000Z',
            app_version: '1.2.0',
            content: {changes: [{title: 'Offline replay', description: ''}]},
          },
        ]),
      };
    }
    return {id: request.id, status: 404, body: null};
  });
  const renderer = await renderPage(SettingsPage);
  const tree = textOf(renderer);
  expect(tree).toContain("What's New");
  expect(tree).toContain(appChangelogsLoadErrorCopy());
  expect(tree).not.toContain("What's New in 1.2.0");
  expect(tree).not.toContain('Offline replay');
  expect(tree).not.toContain('Skip me');
  expect(tree).not.toContain('Dismiss');
  expect(tree).not.toContain('✨');
});

test('Settings names malformed app changelogs GET instead of empty success', async () => {
  mockAuth.hasCloudSession.mockResolvedValue(true);
  mockBackend.request.mockImplementation(async request => {
    if (request.path === '/v1/announcements/changelogs?limit=5') {
      return {
        id: request.id,
        status: 200,
        body: JSON.stringify({changes: []}),
      };
    }
    return {id: request.id, status: 404, body: null};
  });
  const renderer = await renderPage(SettingsPage);
  const tree = textOf(renderer);
  expect(tree).toContain("What's New");
  expect(tree).toContain(appChangelogsLoadErrorCopy());
  expect(tree).not.toContain("What's New in 1.2.0");
  expect(tree).not.toContain('Dismiss');
  expect(tree).not.toContain('✨');
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
  expect(tree).toContain('This Month · Listening');
  expect(tree).toContain('3 minutes');
  expect(tree).toContain('This Month · Understanding');
  expect(tree).toContain('40 Understanding (words)');
  expect(tree).toContain('This Month · Providing');
  expect(tree).toContain('5 Insights');
  expect(tree).toContain('This Month · Remembering');
  expect(tree).toContain('2 Memories');
  expect(tree).toContain('All Time · Listening');
  expect(tree).toContain('60 minutes');
  expect(tree).toContain('Total time Omi has actively listened.');
  expect(tree).toContain('This Year');
  expect(tree).toContain('No Activity Yet');
  expect(tree).toContain('Start a conversation with Omi');
  expect(tree).toContain('to see your usage insights here.');
  expect(tree).not.toContain('This Year ·');
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

test('Settings names Flutter UsagePage fromJson invalid GET speech_seconds instead of empty success', async () => {
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
            speech_seconds: 'bad',
          },
        }),
      };
    }
    if (
      typeof request.path === 'string' &&
      request.path.startsWith('/v1/users/me/usage?period=')
    ) {
      return {id: request.id, status: 200, body: '{}'};
    }
    return {id: request.id, status: 404, body: null};
  });
  const renderer = await renderPage(SettingsPage);
  const tree = textOf(renderer);
  expect(tree).toContain('This Month');
  expect(tree).toContain(usageLoadErrorCopy());
  expect(tree).not.toContain('This Month · Listening');
  expect(tree).not.toContain('3 minutes');
  expect(tree).not.toContain('Upgrade');
});

test('Settings names a failed usage period GET instead of empty success', async () => {
  mockAuth.hasCloudSession.mockResolvedValue(true);
  mockBackend.request.mockImplementation(async request => {
    if (
      request.path === '/v1/users/me/usage?period=monthly' ||
      request.path === '/v1/users/me/usage?period=yearly' ||
      request.path === '/v1/users/me/usage?period=all_time'
    ) {
      throw Object.assign(new Error('lost'), {code: 'OMI_HTTP_TRANSPORT'});
    }
    return {id: request.id, status: 404, body: null};
  });
  const renderer = await renderPage(SettingsPage);
  const tree = textOf(renderer);
  expect(tree).toContain('This Month');
  expect(tree).toContain('This Year');
  expect(tree).toContain('All Time');
  expect(tree).toContain(usageLoadErrorCopy());
  expect(tree).not.toContain(desktopBackendServiceCopy);
  expect(tree).not.toContain('This Month · Listening');
  expect(tree).not.toContain('3 minutes');
  expect(tree).not.toContain('Upgrade');
  expect(tree).not.toContain('No Activity Yet');
});

test('Settings names HTTP 404 usage period GET Flutter usageLoadError instead of omitting', async () => {
  mockAuth.hasCloudSession.mockResolvedValue(true);
  mockBackend.request.mockImplementation(async request => {
    if (
      typeof request.path === 'string' &&
      request.path.startsWith('/v1/users/me/usage?period=')
    ) {
      return {id: request.id, status: 404, body: null};
    }
    return {id: request.id, status: 404, body: null};
  });
  const renderer = await renderPage(SettingsPage);
  const tree = textOf(renderer);
  expect(tree).toContain('This Month');
  expect(tree).toContain('This Year');
  expect(tree).toContain('All Time');
  expect(tree).toContain(usageLoadErrorCopy());
  expect(tree).not.toContain('This Month · Listening');
  expect(tree).not.toContain('No Activity Yet');
  expect(tree).not.toContain('Upgrade');
});

test('Settings names malformed usage period GET instead of empty success', async () => {
  mockAuth.hasCloudSession.mockResolvedValue(true);
  mockBackend.request.mockImplementation(async request => {
    if (
      typeof request.path === 'string' &&
      request.path.startsWith('/v1/users/me/usage?period=')
    ) {
      return {id: request.id, status: 200, body: '{'};
    }
    return {id: request.id, status: 404, body: null};
  });
  const renderer = await renderPage(SettingsPage);
  const tree = textOf(renderer);
  expect(tree).toContain('This Month');
  expect(tree).toContain('This Year');
  expect(tree).toContain('All Time');
  expect(tree).toContain(
    usageLoadErrorCopy(),
  );
  expect(tree).not.toContain('This Month · Listening');
  expect(tree).not.toContain('3 minutes');
  expect(tree).not.toContain('Upgrade');
  expect(tree).not.toContain('No Activity Yet');
});

test('Settings names Flutter developer_mode_provider fromJson GET url instead of omitting Webhooks', async () => {
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
    if (request.path === '/v1/users/developer/webhook/audio_bytes') {
      return {id: request.id, status: 200, body: '[]'};
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
  expect(tree).toContain('Webhooks');
  expect(tree).toContain(
    desktopReadErrorCopy(new Error('Omi webhook URL is malformed')),
  );
  expect(tree).not.toContain('https://example.test/conversation');
  expect(tree).not.toContain('Conversation Events');
});

test('Settings names Flutter Person.fromGenerated type-wrong GET created_at instead of omitting People', async () => {
  mockAuth.hasCloudSession.mockResolvedValue(true);
  mockBackend.request.mockImplementation(async request => {
    if (request.path === '/v1/users/people?include_speech_samples=false') {
      return {
        id: request.id,
        status: 200,
        body: JSON.stringify([
          {
            id: 'person-alex',
            name: 'Alex Chen',
            created_at: 1,
          },
        ]),
      };
    }
    return {id: request.id, status: 404, body: null};
  });
  const renderer = await renderPage(SettingsPage);
  const tree = textOf(renderer);
  expect(tree).toContain('People');
  expect(tree).toContain(
    desktopReadErrorCopy(new Error('Omi people are malformed')),
  );
  expect(tree).not.toContain('Alex Chen');
  expect(tree).not.toContain(
    'Create a new person and train Omi to recognize their speech too!',
  );
});

test('Settings names Flutter Person.fromGenerated padded GET created_at instead of omitting People', async () => {
  mockAuth.hasCloudSession.mockResolvedValue(true);
  mockBackend.request.mockImplementation(async request => {
    if (request.path === '/v1/users/people?include_speech_samples=false') {
      return {
        id: request.id,
        status: 200,
        body: JSON.stringify([
          {
            id: 'person-alex',
            name: 'Alex Chen',
            created_at: '  2026-09-07T00:00:00.000Z  ',
          },
        ]),
      };
    }
    return {id: request.id, status: 404, body: null};
  });
  const renderer = await renderPage(SettingsPage);
  const tree = textOf(renderer);
  expect(tree).toContain('People');
  expect(tree).toContain(
    desktopReadErrorCopy(new Error('Omi people are malformed')),
  );
  expect(tree).not.toContain('Alex Chen');
  expect(tree).not.toContain(
    'Create a new person and train Omi to recognize their speech too!',
  );
});
