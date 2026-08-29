import {readFileSync} from 'node:fs';
import {resolve} from 'node:path';
import {
  conversationGroupLabel,
  desktopBackendConfigurationCopy,
  desktopBackendUnauthorizedCopy,
  desktopCloudBaseURL,
  desktopLocalBackendServiceCopy,
  desktopProjectionUnavailableCopy,
  desktopBackendServiceCopy,
  desktopReadErrorCopy,
  desktopRecoveryCopy,
  loadConversations,
  loadDesktopReads,
  loadMemories,
  loadTasks,
  parseMemoryText,
  projectionTimestamp,
  taskGroup,
  timelineGroups,
} from '../src/desktopReadClient';
import type {
  ConversationProjection,
  DesktopReadProjection,
  DomainReadOutcome,
  MemoryProjection,
} from '../src/desktopReadClient';
import type {NativeHttpRequest, OmiBackend} from '../src/omiNative';
import {omiAuth as browserOmiAuth} from '../src/omiNative.web';
import {
  disableCloudApp,
  enableCloudApp,
  exploreApps,
  installedApps,
  loadAccountSettings,
  loadConnectors,
  myApps,
  parseCloudApp,
  parseCloudApps,
  parseCloudProfile,
  parseEnabledAppIds,
  serviceApps,
} from '../src/desktopCloudClient';

test('keeps first-run onboarding copy off the retired host', () => {
  const onboardingSource = readFileSync(
    resolve(__dirname, '../src/ui/Onboarding.tsx'),
    'utf8',
  );
  const recoverySource = readFileSync(
    resolve(__dirname, '../src/ui/Recovery.tsx'),
    'utf8',
  );

  expect(onboardingSource).toContain('First-run onboarding');
  expect(onboardingSource).not.toContain('h.omi.me');
  expect(onboardingSource).not.toContain('8787');
  expect(recoverySource).not.toContain('h.omi.me');
  expect(recoverySource).not.toContain('8787');
});

test('gates the macOS search toolbar off first-run onboarding', () => {
  const orchestrator = readFileSync(
    resolve(__dirname, '../src/app/AppOrchestrator.tsx'),
    'utf8',
  );

  expect(orchestrator).toContain('onboardingRequired');
  expect(orchestrator).toMatch(
    /onboardingRequired === false\s*\?\s*macDesktopNav\s*:\s*null/,
  );
});

test('treats onboarding as complete in the JavaScript-only adapter', async () => {
  expect(await browserOmiAuth.hasCompletedOnboarding()).toBe(true);
  await expect(
    browserOmiAuth.markOnboardingComplete(),
  ).resolves.toBeUndefined();
  expect(await browserOmiAuth.hasCloudSession()).toBe(false);
  await expect(browserOmiAuth.signOut()).resolves.toEqual({signedOut: true});
  expect(await browserOmiAuth.hasCloudSession()).toBe(false);
});

test('macOS sign-out ignores environment tokens so the session stays empty', () => {
  const auth = readFileSync(
    resolve(__dirname, '../macos/RnRuntime-macOS/OmiAuthModule.mm'),
    'utf8',
  );
  const gate = readFileSync(
    resolve(__dirname, '../src/app/useOnboarding.ts'),
    'utf8',
  );

  expect(auth).toContain('OmiAuthSetEnvironmentCloudTokensIgnored(YES)');
  expect(auth).toMatch(
    /if \(!OmiAuthEnvironmentCloudTokensIgnored\(\)\) \{[^]*OMI_CLOUD_API_TOKEN[^]*OMI_API_TOKEN/,
  );
  expect(gate).toMatch(
    /const result = await auth\.signOut\(\);[^]*const hasSession = await auth\.hasCloudSession\(\);[^]*setOnboardingRequired\(true\)/,
  );
  expect(auth).not.toContain('unsetenv');
  expect(auth).not.toContain('.zshrc');
});

const page = (items: unknown[], completenessVersion: string) => ({
  contractVersion: '1.0.0',
  accountEpoch: 7,
  items,
  window: {
    status: 'complete',
    complete: true,
    hasMore: false,
    nextCursor: null,
  },
  completeness: {
    version: completenessVersion,
    status: 'complete',
    reasons: [],
  },
  absence: items.length === 0 ? {kind: 'query_gap'} : null,
});

const conversation = {
  id: 'conversation-1',
  structured: {title: 'Morning walk', overview: 'Discussed the launch.'},
  created_at: '2026-08-14T01:00:00.000Z',
  updated_at: '2026-08-14T02:00:00.000Z',
  started_at: '2026-08-14T01:00:00.000Z',
  finished_at: '2026-08-14T01:30:00.000Z',
  source: 'omi',
  status: 'completed',
  discarded: false,
  starred: true,
  visibility: 'private',
  is_locked: false,
  folder_id: null,
};

const memory = {
  id: 'memory1_abc',
  text: 'The launch is Friday.',
  citations: ['citation-v1:launch'],
  provenance: {
    synthesisVersion: 'synthesis-v1',
    inputDigest: 'a'.repeat(64),
    outputDigest: 'b'.repeat(64),
  },
  updatedAt: 1785900200,
};

const task = {
  id: 'task1_abc',
  description: 'Prepare launch notes',
  completed: false,
  completedAt: null,
  dueAt: 1786000000,
  owner: null,
  source: 'assistant',
  provenance: ['assistant:summarizer-v3'],
  sortOrder: 1.5,
  indentLevel: 0,
  createdAt: 1785900000,
  updatedAt: 1785900100,
  revision: 'c'.repeat(64),
};

function backendFor(
  responder: (request: NativeHttpRequest) => {
    status: number;
    body: string | null;
  },
): OmiBackend {
  return {
    request: async request => ({id: request.id, ...responder(request)}),
    generationEvents: async () => ({id: 'events', status: 200, body: ''}),
    cancelGenerationEvents: async () => {},
  };
}

test('maps native cloud-first backend failures to actionable, credential-safe copy', () => {
  expect(desktopCloudBaseURL).toBe('https://api.omi.me');
  expect(desktopBackendConfigurationCopy).toBe(
    'Sign in to Omi cloud to load conversations and memories.',
  );
  expect(desktopBackendUnauthorizedCopy).toBe(
    'Omi cloud needs a signed-in session.',
  );
  expect(desktopBackendConfigurationCopy).not.toContain('h.omi.me');
  expect(desktopBackendUnauthorizedCopy).not.toContain('h.omi.me');
  expect(desktopBackendConfigurationCopy).not.toContain('OMI_LOCAL_API');
  expect(desktopBackendConfigurationCopy).not.toContain('127.0.0.1:8787');
  expect(desktopBackendUnauthorizedCopy).not.toContain('OMI_LOCAL_API');
  expect(desktopBackendUnauthorizedCopy).not.toContain('127.0.0.1:8787');
  expect(desktopBackendServiceCopy).toContain('https://api.omi.me');
  expect(desktopBackendServiceCopy).not.toContain('127.0.0.1:8787');
  expect(desktopLocalBackendServiceCopy).toBe(
    'The configured local Omi service is unavailable. Check its connection, then retry.',
  );
  expect(desktopLocalBackendServiceCopy).not.toContain('127.0.0.1:8787');
  expect(desktopLocalBackendServiceCopy).not.toContain('h.omi.me');
  expect(desktopReadErrorCopy({code: 'OMI_HTTP_UNCONFIGURED'})).toBe(
    desktopBackendConfigurationCopy,
  );
  expect(desktopReadErrorCopy({code: 'unauthorized'})).toBe(
    desktopBackendUnauthorizedCopy,
  );
  expect(desktopReadErrorCopy({code: 'OMI_HTTP_TRANSPORT'})).toBe(
    desktopBackendServiceCopy,
  );
  expect(desktopReadErrorCopy(new Error('response rejected'))).toBe(
    'response rejected',
  );
});

describe('desktopRecoveryCopy', () => {
  const pageState = {
    windowStatus: 'complete' as const,
    complete: true,
    hasMore: false,
    nextCursor: null,
    completenessStatus: 'complete' as const,
    reasons: [] as string[],
  };
  const success = <
    T extends DesktopReadProjection,
  >(): DomainReadOutcome<T> => ({
    status: 'success',
    value: {items: [], page: {...pageState}},
  });
  const error = <T extends DesktopReadProjection>(
    message: string,
  ): DomainReadOutcome<T> => ({
    status: 'error',
    error: message,
  });
  const generic =
    'Omi could not load saved conversations or memories. Your saved data has not been changed.';

  test('prefers the conversations typed failure when both domains are typed', () => {
    expect(
      desktopRecoveryCopy(
        error<ConversationProjection>(desktopBackendConfigurationCopy),
        error<MemoryProjection>(desktopBackendServiceCopy),
      ),
    ).toBe(desktopBackendConfigurationCopy);
  });

  test('falls through an untyped conversations failure to a typed memories failure', () => {
    expect(
      desktopRecoveryCopy(
        error<ConversationProjection>(
          'desktop-conversations-read failed (500)',
        ),
        error<MemoryProjection>(desktopProjectionUnavailableCopy),
      ),
    ).toBe(desktopProjectionUnavailableCopy);
  });

  test('keeps one truthful generic fallback without leaking endpoint errors', () => {
    expect(
      desktopRecoveryCopy(
        error<ConversationProjection>(
          'desktop-conversations-read failed (500)',
        ),
        error<MemoryProjection>('Memories response is malformed'),
      ),
    ).toBe(generic);
    expect(desktopRecoveryCopy(success(), success())).toBe(generic);
    expect(
      desktopRecoveryCopy(
        error<ConversationProjection>(desktopBackendServiceCopy),
        success(),
      ),
    ).toBe(desktopBackendServiceCopy);
  });
});

test('loads and normalizes all three exact desktop read routes', async () => {
  const paths: string[] = [];
  const backend = backendFor(request => {
    paths.push(request.path);
    if (request.path.startsWith('/v1/conversations')) {
      return {status: 200, body: JSON.stringify([conversation])};
    }
    if (request.path.startsWith('/v1/memories')) {
      return {
        status: 200,
        body: JSON.stringify(page([memory], 'recall-completeness-v1')),
      };
    }
    return {
      status: 200,
      body: JSON.stringify(page([task], 'tasks-completeness-v1')),
    };
  });

  const result = await loadDesktopReads(backend);
  expect(result.conversations).toEqual({
    status: 'success',
    value: {
      items: [
        expect.objectContaining({
          kind: 'conversation',
          id: 'conversation-1',
          title: 'Morning walk',
          summary: 'Discussed the launch.',
          searchableText: 'Morning walk\nDiscussed the launch.',
          createdAt: '2026-08-14T01:00:00.000Z',
          updatedAt: '2026-08-14T02:00:00.000Z',
          startedAt: '2026-08-14T01:00:00.000Z',
          finishedAt: '2026-08-14T01:30:00.000Z',
          status: 'completed',
          source: 'omi',
          visibility: 'private',
          folderId: null,
          locked: false,
          discarded: false,
        }),
      ],
      page: expect.objectContaining({complete: true, hasMore: false}),
    },
  });
  expect(result.memories).toEqual({
    status: 'success',
    value: {
      items: [
        expect.objectContaining({
          kind: 'memory',
          id: 'memory1_abc',
          searchableText: 'The launch is Friday.\ncitation-v1:launch',
          timestamp: 1785900200,
        }),
      ],
      page: expect.objectContaining({completenessStatus: 'complete'}),
    },
  });
  expect(result.tasks).toEqual({
    status: 'success',
    value: {
      items: [
        expect.objectContaining({
          kind: 'task',
          id: 'task1_abc',
          title: 'Prepare launch notes',
          summary: 'Due 1786000000',
        }),
      ],
      page: expect.objectContaining({completenessStatus: 'complete'}),
      accountEpoch: 7,
    },
  });
  expect(paths.sort()).toEqual(
    [
      '/v1/conversations?limit=50&offset=0',
      '/v1/memories?limit=50',
      '/v1/tasks',
    ].sort(),
  );
});

test('groups validated UTC conversation timestamps by local calendar day', () => {
  const now = new Date(2026, 7, 14, 12, 0).getTime();
  expect(
    conversationGroupLabel(new Date(2026, 7, 14, 1, 0).toISOString(), now),
  ).toBe('Today');
  expect(
    conversationGroupLabel(new Date(2026, 7, 13, 23, 0).toISOString(), now),
  ).toBe('Yesterday');
  expect(
    conversationGroupLabel(new Date(2026, 7, 10, 12, 0).toISOString(), now),
  ).toBe(
    new Date(2026, 7, 10, 12, 0).toLocaleDateString(undefined, {
      day: 'numeric',
      month: 'short',
      year: 'numeric',
    }),
  );
});

test('groups timeline rows through one canonical timestamp policy', () => {
  const now = new Date(2026, 7, 14, 12, 0).getTime();
  const rows: DesktopReadProjection[] = [
    {
      kind: 'conversation',
      id: 'conversation-today',
      title: 'Today',
      summary: '',
      searchableText: 'Today',
      createdAt: new Date(2026, 7, 14, 8, 0).toISOString(),
      updatedAt: new Date(2026, 7, 14, 8, 0).toISOString(),
      startedAt: null,
      finishedAt: null,
      starred: false,
      status: 'completed',
      source: 'omi',
      visibility: 'private',
      folderId: null,
      locked: false,
      discarded: false,
    },
    {
      kind: 'memory',
      id: 'memory-without-date',
      title: 'Undated',
      summary: '',
      searchableText: 'Undated',
      citations: [],
      timestamp: null,
      provenance: {
        label: null,
        synthesisVersion: 'v1',
        inputDigest: 'a',
        outputDigest: 'b',
      },
    },
  ];

  expect(projectionTimestamp(rows[0])).toBe(
    new Date(2026, 7, 14, 8, 0).getTime(),
  );
  expect(projectionTimestamp(rows[1])).toBeNull();
  expect(timelineGroups(rows, now)).toEqual([
    {label: 'Today', items: [rows[0]]},
    {label: 'Date unavailable', items: [rows[1]]},
  ]);
});

test('normalizes memory epoch seconds to timeline milliseconds', () => {
  const memorySeconds = 1785900200;
  const row: MemoryProjection = {
    kind: 'memory',
    id: 'memory-with-date',
    title: 'Dated',
    summary: '',
    searchableText: 'Dated',
    citations: [],
    timestamp: memorySeconds,
    provenance: {
      label: null,
      synthesisVersion: 'v1',
      inputDigest: 'a',
      outputDigest: 'b',
    },
  };

  expect(projectionTimestamp(row)).toBe(memorySeconds * 1000);
});

test('preserves absent memory timestamps without inventing an order', async () => {
  const result = await loadMemories(
    backendFor(() => ({
      status: 200,
      body: JSON.stringify(
        page([{...memory, updatedAt: undefined}], 'recall-completeness-v1'),
      ),
    })),
  );
  expect(result.items[0].timestamp).toBeNull();
});

test('separates a machine slug from visible memory text', () => {
  expect(parseMemoryText('quiet-river-lantern: The launch is Friday.')).toEqual(
    {
      body: 'The launch is Friday.',
      provenanceLabel: 'quiet-river-lantern',
    },
  );
  expect(parseMemoryText('A normal memory: with punctuation.')).toEqual({
    body: 'A normal memory: with punctuation.',
    provenanceLabel: null,
  });
});

test('separates a namespaced entity id from visible memory text', () => {
  expect(
    parseMemoryText(
      'entity:qa:000008 qa_memory (observed 2026-07-30T12:00:00.000Z).',
    ),
  ).toEqual({
    body: 'qa_memory (observed 2026-07-30T12:00:00.000Z).',
    provenanceLabel: 'entity:qa:000008',
  });
});

test.each([
  ['conversations', loadConversations, JSON.stringify({items: []})],
  [
    'memories',
    loadMemories,
    JSON.stringify(page([{...memory, text: null}], 'recall-completeness-v1')),
  ],
  [
    'tasks',
    loadTasks,
    JSON.stringify(
      page([{...task, completed: 'false'}], 'tasks-completeness-v1'),
    ),
  ],
])('fails closed for malformed %s payloads', async (_label, load, body) => {
  const backend = backendFor(() => ({status: 200, body}));
  await expect(load(backend)).rejects.toThrow(/malformed/);
});

test.each([
  ['conversations', loadConversations],
  ['memories', loadMemories],
  ['tasks', loadTasks],
])(
  'surfaces non-success %s reads without consuming the body',
  async (_label, load) => {
    const backend = backendFor(() => ({status: 503, body: '{"items":[]}'}));
    await expect(load(backend)).rejects.toThrow('failed (503)');
  },
);

test('surfaces typed unavailable projections as truthful retryable copy', async () => {
  const body = JSON.stringify({
    error: {
      code: 'projection_unavailable',
      retryable: true,
      action: 'retry',
    },
  });
  const backend = backendFor(request =>
    request.path.startsWith('/v1/tasks')
      ? {
          status: 200,
          body: JSON.stringify(page([], 'tasks-completeness-v1')),
        }
      : {status: 503, body},
  );

  const result = await loadDesktopReads(backend);
  expect(result.conversations).toEqual({
    status: 'error',
    error: desktopProjectionUnavailableCopy,
  });
  expect(result.memories).toEqual({
    status: 'error',
    error: desktopProjectionUnavailableCopy,
  });
  expect(result.tasks).toEqual(expect.objectContaining({status: 'success'}));
});

test('rejects a malformed page envelope before projecting items', async () => {
  const malformed = {
    ...page([], 'recall-completeness-v1'),
    window: {complete: true},
  };
  const backend = backendFor(() => ({
    status: 200,
    body: JSON.stringify(malformed),
  }));
  await expect(loadMemories(backend)).rejects.toThrow(
    'window status is malformed',
  );
});

test('preserves a cursor-backed multi-page memory window', async () => {
  const paths: string[] = [];
  const response = {
    ...page([memory], 'recall-completeness-v1'),
    window: {
      status: 'more',
      complete: false,
      hasMore: true,
      nextCursor: 'cursor-2',
    },
  };
  const backend = backendFor(request => {
    paths.push(request.path);
    return {status: 200, body: JSON.stringify(response)};
  });

  await expect(loadMemories(backend, 'opaque/+ cursor=')).resolves.toEqual({
    items: [expect.objectContaining({id: 'memory1_abc'})],
    page: {
      windowStatus: 'more',
      complete: false,
      hasMore: true,
      nextCursor: 'cursor-2',
      completenessStatus: 'complete',
      reasons: [],
    },
  });
  expect(paths).toEqual([
    '/v1/memories?limit=50&cursor=opaque%2F%2B%20cursor%3D',
  ]);
});

test('rejects an empty memory cursor before issuing a read', async () => {
  const backend = backendFor(() => {
    throw new Error('unexpected request');
  });
  await expect(loadMemories(backend, '')).rejects.toThrow(
    'Memory cursor is malformed',
  );
});

test('preserves an incomplete task projection and its reasons', async () => {
  const response = {
    ...page([task], 'tasks-completeness-v1'),
    window: {
      status: 'incomplete',
      complete: false,
      hasMore: false,
      nextCursor: null,
    },
    completeness: {
      version: 'tasks-completeness-v1',
      status: 'incomplete',
      reasons: ['pending_writes'],
    },
  };
  const backend = backendFor(() => ({
    status: 200,
    body: JSON.stringify(response),
  }));

  await expect(loadTasks(backend)).resolves.toEqual({
    items: [expect.objectContaining({id: 'task1_abc'})],
    page: {
      windowStatus: 'incomplete',
      complete: false,
      hasMore: false,
      nextCursor: null,
      completenessStatus: 'incomplete',
      reasons: ['pending_writes'],
    },
    accountEpoch: 7,
  });
});

test('groups task epochs by deterministic UTC day boundaries', () => {
  const now = Date.UTC(2026, 7, 14, 23, 30) / 1000;
  expect(taskGroup(Date.UTC(2026, 7, 14, 0, 0) / 1000, now)).toBe('Today');
  expect(taskGroup(Date.UTC(2026, 7, 13, 0, 0) / 1000, now)).toBe('Today');
  expect(taskGroup(Date.UTC(2026, 7, 15, 0, 0) / 1000, now)).toBe('Tomorrow');
  expect(taskGroup(Date.UTC(2026, 7, 16, 0, 0) / 1000, now)).toBe('Later');
  expect(taskGroup(null, now)).toBe('Later');
});

test('accepts an omitted account epoch and retains a null task revision', async () => {
  const response = page([{...task, revision: null}], 'tasks-completeness-v1');
  delete (response as {accountEpoch?: number}).accountEpoch;
  const result = await loadTasks(
    backendFor(() => ({status: 200, body: JSON.stringify(response)})),
  );
  expect(result.accountEpoch).toBeNull();
  expect(result.items[0]).toEqual(
    expect.objectContaining({
      owner: null,
      source: 'assistant',
      provenance: ['assistant:summarizer-v3'],
      indentLevel: 0,
      revision: null,
    }),
  );
});

test('marks a full conversation window as potentially incomplete', async () => {
  const conversations = Array.from({length: 50}, (_, index) => ({
    ...conversation,
    id: `conversation-${index}`,
  }));
  const backend = backendFor(() => ({
    status: 200,
    body: JSON.stringify(conversations),
  }));

  const result = await loadConversations(backend);
  expect(result.items).toHaveLength(50);
  expect(result.page).toEqual({
    windowStatus: 'unknown',
    complete: false,
    hasMore: true,
    nextCursor: null,
    completenessStatus: 'unknown',
    reasons: ['limit_reached'],
  });
});

test('keeps nullable conversation times while rejecting invalid metadata', async () => {
  const backend = backendFor(() => ({
    status: 200,
    body: JSON.stringify([
      {...conversation, started_at: null, finished_at: null},
    ]),
  }));

  await expect(loadConversations(backend)).resolves.toMatchObject({
    items: [
      expect.objectContaining({
        startedAt: null,
        finishedAt: null,
        status: 'completed',
        locked: false,
        discarded: false,
      }),
    ],
  });

  const malformed = backendFor(() => ({
    status: 200,
    body: JSON.stringify([{...conversation, updated_at: 'not-a-time'}]),
  }));
  await expect(loadConversations(malformed)).rejects.toThrow(
    'updated_at is malformed',
  );
});

test('retains successful domains when one desktop read fails', async () => {
  const backend = backendFor(request => {
    if (request.path.startsWith('/v1/conversations')) {
      return {status: 503, body: null};
    }
    if (request.path.startsWith('/v1/memories')) {
      return {
        status: 200,
        body: JSON.stringify(page([memory], 'recall-completeness-v1')),
      };
    }
    return {
      status: 200,
      body: JSON.stringify(page([task], 'tasks-completeness-v1')),
    };
  });

  const result = await loadDesktopReads(backend);
  expect(result.conversations).toEqual({
    status: 'error',
    error: 'desktop-conversations-read failed (503)',
  });
  expect(result.memories).toEqual(expect.objectContaining({status: 'success'}));
  expect(result.tasks).toEqual(expect.objectContaining({status: 'success'}));
});

test('maps a cloud 401 to typed unauthorized copy without fabricating rows', async () => {
  const backend = backendFor(() => ({status: 401, body: null}));
  const result = await loadDesktopReads(backend);
  expect(result.conversations).toEqual({
    status: 'error',
    error: desktopBackendUnauthorizedCopy,
  });
  expect(result.memories).toEqual({
    status: 'error',
    error: desktopBackendUnauthorizedCopy,
  });
});

test('parses catalogue, enabled, owned, and service app records without inventing rows', () => {
  const app = parseCloudApp(
    {
      id: 'catalog-app-1',
      name: 'Catalog fixture app',
      description: 'A mocked catalogue record.',
      category: 'productivity',
      author: 'fixture-author',
      enabled: false,
      uid: 'user-1',
      external_integration: {webhook_url: 'https://example.test/hook'},
      connected_accounts: ['calendar'],
    },
    'App 0',
  );
  expect(app).toEqual(
    expect.objectContaining({
      enabled: false,
      hasExternalIntegration: true,
      connectedAccounts: ['calendar'],
      uid: 'user-1',
    }),
  );
  expect(parseEnabledAppIds(['catalog-app-1'], 'Enabled')).toEqual([
    'catalog-app-1',
  ]);
  expect(() => parseCloudApps({items: []}, 'Apps response')).toThrow(
    'Apps response is malformed',
  );
  expect(() => parseEnabledAppIds({items: []}, 'Enabled')).toThrow(
    'Enabled is malformed',
  );
});

test('loadConnectors merges enabled ids and keeps owner filtering honest', async () => {
  const backend = backendFor(request => {
    if (request.path === '/v1/apps') {
      return {
        status: 200,
        body: JSON.stringify([
          {
            id: 'catalog-app-1',
            name: 'Owned app',
            uid: 'user-1',
            enabled: false,
            external_integration: {webhook_url: 'https://example.test/hook'},
          },
          {id: 'catalog-app-2', name: 'Other app', uid: 'user-2'},
        ]),
      };
    }
    if (request.path === '/v1/apps/enabled') {
      return {status: 200, body: JSON.stringify(['catalog-app-1'])};
    }
    if (request.path === '/v1/users/profile') {
      return {status: 200, body: JSON.stringify({uid: 'user-1', name: 'Ada'})};
    }
    return {status: 404, body: null};
  });
  const snapshot = await loadConnectors(backend);
  expect(snapshot.ownerUid).toBe('user-1');
  expect(exploreApps(snapshot).map(app => app.id)).toEqual([
    'catalog-app-1',
    'catalog-app-2',
  ]);
  expect(installedApps(snapshot).map(app => app.id)).toEqual(['catalog-app-1']);
  expect(myApps(snapshot, snapshot.ownerUid).map(app => app.id)).toEqual([
    'catalog-app-1',
  ]);
  expect(serviceApps(snapshot).map(app => app.id)).toEqual(['catalog-app-1']);
});

test('enableCloudApp requires a real ok status and does not treat errors as installed', async () => {
  await expect(
    enableCloudApp(
      backendFor(() => ({status: 400, body: '{"detail":"setup incomplete"}'})),
      'catalog-app-1',
    ),
  ).rejects.toThrow('desktop-app-enable failed (400)');
  await expect(
    enableCloudApp(
      backendFor(() => ({status: 200, body: '{"status":"pending"}'})),
      'catalog-app-1',
    ),
  ).rejects.toThrow('desktop-app-enable failed');
  await enableCloudApp(
    backendFor(() => ({status: 200, body: '{"status":"ok"}'})),
    'catalog-app-1',
  );
  await disableCloudApp(
    backendFor(() => ({status: 200, body: '{"status":"ok"}'})),
    'catalog-app-1',
  );
});

test('loadAccountSettings keeps failed slices independent', async () => {
  const backend = backendFor(request => {
    if (request.path === '/v1/users/profile') {
      return {
        status: 200,
        body: JSON.stringify({uid: 'user-1', email: 'ada@example.test'}),
      };
    }
    if (request.path === '/v1/users/me/subscription') {
      return {status: 503, body: null};
    }
    if (request.path === '/v1/users/store-recording-permission') {
      return {
        status: 200,
        body: JSON.stringify({store_recording_permission: true}),
      };
    }
    if (request.path === '/v1/users/training-data-opt-in') {
      return {status: 200, body: JSON.stringify({opted_in: false})};
    }
    if (request.path === '/v1/users/private-cloud-sync') {
      return {
        status: 200,
        body: JSON.stringify({private_cloud_sync_enabled: false}),
      };
    }
    if (request.path === '/v1/users/developer/webhooks/status') {
      return {status: 404, body: null};
    }
    return {status: 404, body: null};
  });
  const snapshot = await loadAccountSettings(backend);
  expect(parseCloudProfile({uid: 'user-1'}, 'Profile')).toEqual({
    uid: 'user-1',
    name: null,
    email: null,
    company: null,
    job: null,
    dataProtectionLevel: null,
  });
  expect(snapshot.profile).toEqual(
    expect.objectContaining({uid: 'user-1', email: 'ada@example.test'}),
  );
  expect(snapshot.subscription).toBeNull();
  expect(snapshot.subscriptionError).toBe(
    'desktop-subscription-read failed (503)',
  );
  expect(snapshot.storeRecordingPermission).toBe(true);
  expect(snapshot.trainingOptedIn).toBe(false);
  expect(snapshot.privateCloudSync).toBe(false);
  expect(snapshot.webhooks).toBeNull();
});
