import {readFileSync} from 'node:fs';
import {resolve} from 'node:path';
import {
  conversationDisplaySummary,
  conversationDisplayTitle,
  conversationDayLabel,
  conversationGroupLabel,
  conversationStatusCopy,
  dataProtectionCopy,
  developerWebhookStatusCopy,
  developerWebhookTypeCopy,
  appCategoryCopy,
  appDisplaySource,
  appDisplayName,
  deviceDisplayName,
  accountFieldCopy,
  connectionIdentityCopy,
  chatMessageDisplayText,
  desktopBackendConfigurationCopy,
  desktopBackendUnauthorizedCopy,
  desktopBackendForbiddenCopy,
  desktopCloudBaseURL,
  desktopLocalBackendServiceCopy,
  desktopProjectionUnavailableCopy,
  desktopBackendUnavailableCopy,
  desktopAppsUnavailableCopy,
  desktopAccountSettingUnavailableCopy,
  desktopBackendServiceCopy,
  desktopReadErrorCopy,
  desktopReadsCanRetry,
  desktopRecoveryCopy,
  homeSearchItems,
  loadConversations,
  loadDesktopReads,
  loadMemories,
  loadTasks,
  memoryDisplayBody,
  memoryDisplayTitle,
  memoryCitationCopy,
  parseMemoryText,
  chatClockLabel,
  formatTaskDue,
  projectionClockLabel,
  projectionTimestamp,
  subscriptionPlanCopy,
  subscriptionStatusCopy,
  taskDisplaySummary,
  taskDisplayTitle,
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
  cloudErrorCanRetry,
  disableCloudApp,
  enableCloudApp,
  exploreApps,
  installedApps,
  loadAccountSettings,
  loadConnectors,
  myApps,
  optInTrainingData,
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
  const desktopSource = readFileSync(
    resolve(__dirname, '../src/desktop/DesktopApp.tsx'),
    'utf8',
  );

  expect(onboardingSource).toContain('First-run onboarding');
  expect(onboardingSource).not.toContain('h.omi.me');
  expect(onboardingSource).not.toContain('8787');
  expect(desktopSource).not.toContain('h.omi.me');
  expect(desktopSource).not.toContain('8787');
});

test('macOS mounts DesktopApp only for a ready session', () => {
  const orchestrator = readFileSync(
    resolve(__dirname, '../src/app/AppOrchestrator.tsx'),
    'utf8',
  );

  expect(orchestrator).toContain('onboardingRequired');
  expect(orchestrator).toMatch(/if \(macDesktop\) \{/);
  expect(orchestrator).toContain('<DesktopApp');
  expect(orchestrator).toMatch(
    /<DesktopApp[\s\S]*onLoadMoreConversations=\{\s*conversationsPageRetryable/,
  );
  expect(orchestrator).toMatch(
    /<DesktopApp[\s\S]*onLoadMoreMemories=\{\s*memoriesPageRetryable/,
  );
  expect(orchestrator).toContain('onboardingRequired !== false');
  expect(orchestrator).not.toMatch(
    /onboardingRequired === false\s*\?\s*macDesktopNav\s*:\s*null/,
  );
});

test('browser setup persists disclosure without establishing a cloud session', async () => {
  const descriptor = Object.getOwnPropertyDescriptor(
    globalThis,
    'localStorage',
  );
  const values = new Map([['omi.onboarding.completed', 'true']]);
  Object.defineProperty(globalThis, 'localStorage', {
    configurable: true,
    value: {
      getItem: (key: string) => values.get(key) ?? null,
      setItem: (key: string, value: string) => {
        values.set(key, value);
      },
    },
  });
  try {
    expect(await browserOmiAuth.hasCompletedOnboarding()).toBe(false);
    await browserOmiAuth.markOnboardingComplete();
    expect(await browserOmiAuth.hasCompletedOnboarding()).toBe(true);
    expect(await browserOmiAuth.hasCloudSession()).toBe(false);
    await expect(browserOmiAuth.signOut()).resolves.toEqual({signedOut: true});
    expect(await browserOmiAuth.hasCloudSession()).toBe(false);
  } finally {
    if (descriptor) {
      Object.defineProperty(globalThis, 'localStorage', descriptor);
    } else {
      Reflect.deleteProperty(globalThis, 'localStorage');
    }
  }
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
    /const result = await auth\.signOut\(\);[^]*hasSession = await auth\.hasCloudSession\(\);[^]*setOnboardingRequired\(true\)/,
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
  title: 'Morning walk',
  overview: 'Discussed the launch.',
  revision: '1',
  createdAt: Date.parse('2026-08-14T01:00:00.000Z'),
  updatedAt: Date.parse('2026-08-14T02:00:00.000Z'),
  startedAt: Date.parse('2026-08-14T01:00:00.000Z'),
  finishedAt: Date.parse('2026-08-14T01:30:00.000Z'),
  source: 'omi',
  status: 'completed',
  discarded: false,
  starred: true,
  visibility: 'private',
  isLocked: false,
  folderId: null,
};

function conversationPage(items: unknown[], hasMore = false) {
  return {
    contractVersion: '1.0.0',
    items,
    window: {
      status: hasMore ? 'more' : 'complete',
      complete: !hasMore,
      hasMore,
      nextCursor: hasMore ? 'next-page' : null,
    },
    completeness: {
      version: 'conversations-completeness-v1',
      status: 'complete',
      reasons: [],
    },
    absence: items.length ? null : {kind: 'query_gap'},
  };
}

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
  expect(desktopBackendServiceCopy).toBe(
    'The selected Omi service is unavailable. Check the connection, then retry.',
  );
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
  expect(
    desktopReadErrorCopy(new Error('Conversations response is malformed')),
  ).toBe('This saved data could not be loaded. Retry without changing it.');
  expect(desktopReadErrorCopy(new Error(desktopBackendForbiddenCopy))).toBe(
    desktopBackendForbiddenCopy,
  );
  expect(desktopReadErrorCopy(new Error(desktopBackendUnavailableCopy))).toBe(
    desktopBackendUnavailableCopy,
  );
  expect(desktopReadErrorCopy(new Error(desktopAppsUnavailableCopy))).toBe(
    desktopAppsUnavailableCopy,
  );
  expect(
    desktopReadErrorCopy(new Error(desktopAccountSettingUnavailableCopy)),
  ).toBe(desktopAccountSettingUnavailableCopy);
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

describe('homeSearchItems', () => {
  const conversation: DesktopReadProjection = {
    kind: 'conversation',
    id: 'conversation-search',
    title: 'Morning walk',
    summary: 'Discussed the launch.',
    searchableText: 'Morning walk\nDiscussed the launch.',
    createdAt: '2026-08-14T01:00:00.000Z',
    updatedAt: '2026-08-14T02:00:00.000Z',
    startedAt: '2026-08-14T01:00:00.000Z',
    finishedAt: '2026-08-14T01:30:00.000Z',
    starred: false,
    status: 'completed',
    source: 'omi',
    visibility: 'private',
    folderId: null,
    locked: false,
    discarded: false,
  };
  const task: DesktopReadProjection = {
    kind: 'task',
    id: 'task-search',
    title: 'Ship the desktop chrome',
    summary: 'Pending',
    searchableText: 'Ship the desktop chrome',
    completed: false,
    completedAt: null,
    dueAt: null,
    owner: null,
    source: 'manual',
    provenance: [],
    sortOrder: 0,
    indentLevel: 0,
    createdAt: Date.parse('2026-08-14T03:00:00.000Z'),
    updatedAt: Date.parse('2026-08-14T03:00:00.000Z'),
    revision: '1',
  };

  test('includes matching tasks instead of only conversation and memory rows', () => {
    expect(
      homeSearchItems([conversation], [task], 'desktop chrome').map(
        item => item.id,
      ),
    ).toEqual(['task-search']);
    expect(
      homeSearchItems([conversation], [task], 'walk').map(item => item.id),
    ).toEqual(['conversation-search']);
    expect(
      homeSearchItems([], [task], 'desktop chrome').map(item => item.id),
    ).toEqual(['task-search']);
  });

  test('omits tasks when the task page did not load', () => {
    expect(homeSearchItems([conversation], null, 'desktop chrome')).toEqual([]);
  });
});

describe('desktopReadsCanRetry', () => {
  const pageState = {
    windowStatus: 'complete' as const,
    complete: true,
    hasMore: false,
    nextCursor: null,
    completenessStatus: 'complete' as const,
    reasons: [] as string[],
  };
  const success = {
    status: 'success' as const,
    value: {items: [], page: {...pageState}, accountEpoch: null},
  };
  const error = (message: string) =>
    ({
      status: 'error' as const,
      error: message,
    } as const);

  test('omits retry when every failed library door is nested non-retryable', () => {
    expect(desktopReadsCanRetry(null)).toBe(true);
    expect(
      desktopReadsCanRetry({
        conversations: success,
        memories: success,
        tasks: success,
      }),
    ).toBe(true);
    expect(
      desktopReadsCanRetry({
        conversations: error(desktopBackendUnavailableCopy),
        memories: error(desktopBackendUnavailableCopy),
        tasks: error(desktopBackendUnavailableCopy),
      }),
    ).toBe(false);
    expect(
      desktopReadsCanRetry({
        conversations: error(desktopBackendUnavailableCopy),
        memories: error(desktopBackendServiceCopy),
        tasks: success,
      }),
    ).toBe(true);
    expect(
      desktopReadsCanRetry({
        conversations: error(desktopBackendForbiddenCopy),
        memories: error(desktopBackendUnavailableCopy),
        tasks: error(desktopBackendUnavailableCopy),
      }),
    ).toBe(true);
  });
});

test('loads and normalizes all three exact desktop read routes', async () => {
  const paths: string[] = [];
  const backend = backendFor(request => {
    paths.push(request.path);
    if (request.path.startsWith('/v1/conversations')) {
      return {
        status: 200,
        body: JSON.stringify(conversationPage([conversation])),
      };
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
    ['/v1/conversations?limit=50', '/v1/memories?limit=50', '/v1/tasks'].sort(),
  );
});

test('keeps processing conversations whose title and overview are not ready yet', async () => {
  const backend = backendFor(() => ({
    status: 200,
    body: JSON.stringify(
      conversationPage([
        {
          ...conversation,
          title: '',
          overview: '',
          status: 'processing',
        },
      ]),
    ),
  }));

  await expect(loadConversations(backend)).resolves.toEqual(
    expect.objectContaining({
      items: [
        expect.objectContaining({
          title: '',
          summary: '',
          status: 'processing',
          searchableText:
            'Processing conversation…\nConversation summary is not ready yet.',
        }),
      ],
    }),
  );
});

test('empty conversation titles stay visible instead of a blank row', () => {
  expect(conversationDisplayTitle({title: '', status: 'processing'})).toBe(
    'Processing conversation…',
  );
  expect(conversationDisplayTitle({title: '', status: 'completed'})).toBe(
    'Conversation title unavailable',
  );
  expect(conversationDisplayTitle({title: ' \t\n', status: 'processing'})).toBe(
    'Processing conversation…',
  );
  expect(conversationDisplayTitle({title: ' \t\n', status: 'completed'})).toBe(
    'Conversation title unavailable',
  );
  expect(
    conversationDisplayTitle({title: 'Morning walk', status: 'processing'}),
  ).toBe('Morning walk');
  expect(
    conversationDisplayTitle({title: '  Morning walk  ', status: 'completed'}),
  ).toBe('Morning walk');
});

test('conversation status copy is not a raw wire token', () => {
  expect(conversationStatusCopy('in_progress')).toBe('In progress');
  expect(conversationStatusCopy('processing')).toBe('Processing');
  expect(conversationStatusCopy('merging')).toBe('Merging');
  expect(conversationStatusCopy('completed')).toBe('Completed');
  expect(conversationStatusCopy('failed')).toBe('Failed');
  expect(conversationStatusCopy('')).toBe('Status unavailable');
  expect(conversationStatusCopy(' \t\n')).toBe('Status unavailable');
  expect(conversationStatusCopy('\u00A0')).toBe('Status unavailable');
  expect(conversationStatusCopy('queued')).toBe('queued');
  expect(conversationStatusCopy('  queued  ')).toBe('queued');
});

test('account subscription copy is not a raw wire token', () => {
  expect(subscriptionPlanCopy('plus')).toBe('Plus');
  expect(subscriptionStatusCopy('active')).toBe('Active');
  expect(subscriptionStatusCopy('past_due')).toBe('Past due');
  expect(subscriptionPlanCopy('')).toBe('Plan unavailable');
  expect(subscriptionStatusCopy('')).toBe('Plan unavailable');
  expect(dataProtectionCopy('standard')).toBe('Standard');
  expect(dataProtectionCopy('')).toBe('Data protection unavailable');
});

test('developer webhook titles are not raw API keys', () => {
  expect(developerWebhookTypeCopy('memory_created')).toBe(
    'Conversation Events',
  );
  expect(developerWebhookTypeCopy('realtime_transcript')).toBe(
    'Real-time Transcript',
  );
  expect(developerWebhookTypeCopy('audio_bytes')).toBe('Audio Bytes');
  expect(developerWebhookTypeCopy('day_summary')).toBe('Day Summary');
  expect(developerWebhookTypeCopy('button_event')).toBe('Button event');
  expect(developerWebhookTypeCopy('')).toBe('Webhook unavailable');
});

test('developer webhook status copy does not say unknown for a missing enablement bit', () => {
  expect(developerWebhookStatusCopy(true)).toBe('Enabled');
  expect(developerWebhookStatusCopy(false)).toBe('Disabled');
  expect(developerWebhookStatusCopy(null)).toBe('Status unavailable');
});

test('whitespace-only account fields stay unset instead of a blank row', () => {
  expect(accountFieldCopy(null, 'Name not set on this account.')).toBe(
    'Name not set on this account.',
  );
  expect(accountFieldCopy(' \t\n', 'Name not set on this account.')).toBe(
    'Name not set on this account.',
  );
  expect(accountFieldCopy('\u00A0', 'Email not set on this account.')).toBe(
    'Email not set on this account.',
  );
  expect(accountFieldCopy('  Ada  ', 'Name not set on this account.')).toBe(
    'Ada',
  );
});

test('whitespace-only connection identity stays unavailable', () => {
  expect(connectionIdentityCopy(null)).toBe(
    'Identity unavailable for this connection.',
  );
  expect(connectionIdentityCopy({displayName: '', email: ''})).toBe(
    'Identity unavailable for this connection.',
  );
  expect(connectionIdentityCopy({displayName: ' \t', email: '\n'})).toBe(
    'Identity unavailable for this connection.',
  );
  expect(
    connectionIdentityCopy({displayName: '  Local identity  ', email: ''}),
  ).toBe('Local identity');
  expect(
    connectionIdentityCopy({
      displayName: '',
      email: '  ada@example.com  ',
    }),
  ).toBe('ada@example.com');
});

test('app category copy is not a raw wire token', () => {
  expect(appCategoryCopy('productivity')).toBe('Productivity');
  expect(appCategoryCopy('health-fitness')).toBe('Health fitness');
  expect(appCategoryCopy('')).toBe('');
});

test('empty app source stays visible instead of a blank meta line', () => {
  expect(appDisplaySource({author: '', category: '', description: ''})).toBe(
    'App details unavailable',
  );
  expect(
    appDisplaySource({author: ' \t\n', category: ' \t', description: '\u00A0'}),
  ).toBe('App details unavailable');
  expect(
    appDisplaySource({
      author: '  Omi  ',
      category: 'productivity',
      description: 'Calendar sync',
    }),
  ).toBe('Omi');
  expect(
    appDisplaySource({
      author: '',
      category: 'productivity',
      description: 'Calendar sync',
    }),
  ).toBe('Productivity');
  expect(
    appDisplaySource({
      author: '',
      category: '',
      description: '  Calendar sync  ',
    }),
  ).toBe('Calendar sync');
});

test('empty app names stay visible instead of a blank title', () => {
  expect(appDisplayName('')).toBe('App name unavailable');
  expect(appDisplayName(' \t\n')).toBe('App name unavailable');
  expect(appDisplayName('\u00A0')).toBe('App name unavailable');
  expect(appDisplayName('  Owned app  ')).toBe('Owned app');
});

test('empty device names stay visible instead of a blank row', () => {
  expect(deviceDisplayName('')).toBe('Device name unavailable');
  expect(deviceDisplayName(' \t\n')).toBe('Device name unavailable');
  expect(deviceDisplayName('\u00A0')).toBe('Device name unavailable');
  expect(deviceDisplayName('  Omi  ')).toBe('Omi');
});

test('empty chat bodies stay visible instead of a blank bubble', () => {
  expect(
    chatMessageDisplayText({
      text: '',
      generationOutcome: null,
    }),
  ).toBe('Message text unavailable');
  expect(
    chatMessageDisplayText({
      text: ' \t\n',
      generationOutcome: 'completed',
    }),
  ).toBe('Message text unavailable');
  expect(
    chatMessageDisplayText({
      text: '\u00A0',
      generationOutcome: null,
    }),
  ).toBe('Message text unavailable');
  expect(
    chatMessageDisplayText({
      text: '',
      generationOutcome: 'cancelled',
    }),
  ).toBe('Response stopped');
  expect(
    chatMessageDisplayText(
      {
        text: ' \t',
        generationOutcome: 'cancelled',
      },
      'Response stopped.',
    ),
  ).toBe('Response stopped.');
  expect(
    chatMessageDisplayText({
      text: '  Hello  ',
      generationOutcome: null,
    }),
  ).toBe('Hello');
  expect(
    chatMessageDisplayText({
      text: '',
      generationOutcome: 'failed',
      generationRetryable: true,
    }),
  ).toBe('Response failed. Try again.');
});

test('empty memory text stays visible instead of a blank row', () => {
  expect(memoryDisplayTitle({title: '', summary: ''})).toBe(
    'Memory text unavailable',
  );
  expect(memoryDisplayBody({title: '', summary: ''})).toBe(
    'Memory text unavailable',
  );
  expect(
    memoryDisplayTitle({
      title: 'entity:qa:000008 qa_memory (observed 2026-07-30T12:00:00.000Z).',
      summary:
        'entity:qa:000008 qa_memory (observed 2026-07-30T12:00:00.000Z).',
    }),
  ).toBe('qa_memory (observed 2026-07-30T12:00:00.000Z).');
  expect(
    memoryDisplayTitle({
      title: 'Prefers concise release notes',
      summary: 'Release notes should lead with the outcome.',
    }),
  ).toBe('Prefers concise release notes');
  expect(
    memoryDisplayBody({
      title: 'Prefers concise release notes',
      summary: 'Release notes should lead with the outcome.',
    }),
  ).toBe('Release notes should lead with the outcome.');
  expect(memoryDisplayTitle({title: 'A walk.', summary: 'A walk.'})).toBe(
    'A walk.',
  );
  expect(memoryDisplayTitle({title: ' \t', summary: ''})).toBe(
    'Memory text unavailable',
  );
  expect(memoryDisplayBody({title: '', summary: ' \t\n'})).toBe(
    'Memory text unavailable',
  );
  expect(memoryDisplayTitle({title: ' \t', summary: 'A walk.'})).toBe(
    'A walk.',
  );
});

test('memory citation copy matches the citation count', () => {
  expect(memoryCitationCopy([])).toBe('0 citations');
  expect(memoryCitationCopy(['citation-v1:launch'])).toBe('1 citation');
  expect(memoryCitationCopy(['a', 'b'])).toBe('2 citations');
});

test('task due copy uses a calendar date instead of a raw epoch', () => {
  const secondScaleDue = 1786000000;
  const millisecondDue = Date.UTC(2026, 8, 8);
  const secondScaleCopy = new Date(secondScaleDue * 1000).toLocaleDateString(
    undefined,
    {
      day: 'numeric',
      month: 'short',
      year: 'numeric',
      timeZone: 'UTC',
    },
  );
  const millisecondCopy = new Date(millisecondDue).toLocaleDateString(
    undefined,
    {
      day: 'numeric',
      month: 'short',
      year: 'numeric',
      timeZone: 'UTC',
    },
  );
  expect(secondScaleCopy).toContain('2026');
  expect(secondScaleCopy).not.toContain('1970');
  expect(formatTaskDue(secondScaleDue)).toBe(secondScaleCopy);
  expect(formatTaskDue(millisecondDue)).toBe(millisecondCopy);
  expect(taskDisplaySummary({completed: false, dueAt: secondScaleDue})).toBe(
    `Due ${secondScaleCopy}`,
  );
  expect(
    taskDisplaySummary({completed: false, dueAt: secondScaleDue}),
  ).not.toBe('Due 1786000000');
  expect(taskDisplaySummary({completed: false, dueAt: null})).toBe('Pending');
  expect(taskDisplaySummary({completed: true, dueAt: secondScaleDue})).toBe(
    'Completed',
  );
  expect(formatTaskDue(null)).toBe('No due date');
  expect(formatTaskDue(0)).toBe('Date unavailable');
  expect(formatTaskDue(0)).not.toContain('1970');
  expect(taskDisplaySummary({completed: false, dueAt: 0})).toBe(
    'Date unavailable',
  );
  expect(taskGroup(0, Date.now())).toBe('Later');
});

test('empty task titles stay visible instead of a blank row', () => {
  expect(taskDisplayTitle({title: ''})).toBe('Task title unavailable');
  expect(taskDisplayTitle({title: ' \t\n'})).toBe('Task title unavailable');
  expect(taskDisplayTitle({title: 'Prepare demo'})).toBe('Prepare demo');
  expect(taskDisplayTitle({title: '  Prepare demo  '})).toBe('Prepare demo');
});

test('empty conversation summaries stay visible instead of a blank subtitle', () => {
  expect(
    conversationDisplaySummary({
      summary: '',
      status: 'processing',
    }),
  ).toBe('Conversation summary is not ready yet.');
  expect(
    conversationDisplaySummary({
      summary: '',
      status: 'completed',
    }),
  ).toBe('Conversation summary unavailable');
  expect(
    conversationDisplaySummary({
      summary: 'Walked to the market.',
      status: 'processing',
    }),
  ).toBe('Walked to the market.');
  expect(
    conversationDisplaySummary({
      summary: ' \t\n',
      status: 'processing',
    }),
  ).toBe('Conversation summary is not ready yet.');
  expect(
    conversationDisplaySummary({
      summary: ' \t\n',
      status: 'completed',
    }),
  ).toBe('Conversation summary unavailable');
  expect(
    conversationDisplaySummary({
      summary: '  Walked to the market.  ',
      status: 'completed',
    }),
  ).toBe('Walked to the market.');
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

test('conversation day labels prefer startedAt and keep Today/Yesterday/date', () => {
  const now = new Date(2026, 7, 14, 12, 0).getTime();
  const older = new Date(2026, 7, 10, 12, 0).toISOString();
  expect(
    conversationDayLabel(new Date(2026, 7, 14, 1, 0).toISOString(), older, now),
  ).toBe('Today');
  expect(
    conversationDayLabel(null, new Date(2026, 7, 13, 23, 0).toISOString(), now),
  ).toBe('Yesterday');
  expect(conversationDayLabel(null, older, now)).toBe(
    new Date(2026, 7, 10, 12, 0).toLocaleDateString(undefined, {
      day: 'numeric',
      month: 'short',
      year: 'numeric',
    }),
  );
});

test('conversation day labels treat a zero timestamp as Date unavailable', () => {
  const now = new Date(2026, 7, 14, 12, 0).getTime();
  expect(conversationGroupLabel(new Date(0).toISOString(), now)).toBe(
    'Date unavailable',
  );
  expect(conversationDayLabel(null, new Date(0).toISOString(), now)).toBe(
    'Date unavailable',
  );
  expect(
    conversationDayLabel(
      new Date(0).toISOString(),
      new Date(now).toISOString(),
      now,
    ),
  ).toBe('Date unavailable');
});

test('clock labels keep Today as time and date older days', () => {
  const now = new Date(2026, 7, 14, 12, 0).getTime();
  const conversation = (
    startedAt: string | null,
    createdAt: string,
  ): DesktopReadProjection => ({
    kind: 'conversation',
    id: 'conversation-1',
    title: 'Product review',
    summary: '',
    searchableText: '',
    createdAt,
    updatedAt: createdAt,
    startedAt,
    finishedAt: null,
    starred: false,
    status: 'completed',
    source: 'desktop',
    visibility: 'private',
    folderId: null,
    locked: false,
    discarded: false,
  });
  const time = (value: Date) =>
    value.toLocaleTimeString(undefined, {
      hour: 'numeric',
      minute: '2-digit',
    });
  const today = new Date(2026, 7, 14, 8, 0);
  expect(
    projectionClockLabel(conversation(null, today.toISOString()), now),
  ).toBe(time(today));
  const yesterday = new Date(2026, 7, 13, 23, 0);
  expect(
    projectionClockLabel(
      conversation(yesterday.toISOString(), today.toISOString()),
      now,
    ),
  ).toBe(`Yesterday · ${time(yesterday)}`);
  const older = new Date(2026, 7, 10, 12, 0);
  expect(
    projectionClockLabel(conversation(null, older.toISOString()), now),
  ).toBe(
    `${older.toLocaleDateString(undefined, {
      day: 'numeric',
      month: 'short',
      year: 'numeric',
    })} · ${time(older)}`,
  );
  expect(
    projectionClockLabel(
      {
        kind: 'memory',
        id: 'memory-1',
        title: 'Undated',
        summary: '',
        searchableText: '',
        citations: [],
        timestamp: null,
        provenance: {
          label: null,
          synthesisVersion: null,
          inputDigest: null,
          outputDigest: null,
        },
      },
      now,
    ),
  ).toBe('Time unavailable');
  expect(
    projectionClockLabel(
      {
        kind: 'memory',
        id: 'memory-zero',
        title: 'Epoch',
        summary: '',
        searchableText: '',
        citations: [],
        timestamp: 0,
        provenance: {
          label: null,
          synthesisVersion: null,
          inputDigest: null,
          outputDigest: null,
        },
      },
      now,
    ),
  ).toBe('Time unavailable');
  expect(
    projectionClockLabel(conversation(null, new Date(0).toISOString()), now),
  ).toBe('Time unavailable');
});

test('chat clock labels date older days and keep seconds or milliseconds', () => {
  const now = new Date(2026, 7, 14, 12, 0).getTime();
  const time = (value: Date) =>
    value.toLocaleTimeString(undefined, {
      hour: 'numeric',
      minute: '2-digit',
    });
  const today = new Date(2026, 7, 14, 8, 0);
  expect(chatClockLabel(today.getTime(), now)).toBe(time(today));
  expect(chatClockLabel(Math.floor(today.getTime() / 1000), now)).toBe(
    time(today),
  );
  const yesterday = new Date(2026, 7, 13, 23, 0);
  expect(chatClockLabel(yesterday.getTime(), now)).toBe(
    `Yesterday · ${time(yesterday)}`,
  );
  const older = new Date(2026, 7, 10, 12, 0);
  expect(chatClockLabel(older.getTime(), now)).toBe(
    `${older.toLocaleDateString(undefined, {
      day: 'numeric',
      month: 'short',
      year: 'numeric',
    })} · ${time(older)}`,
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
    await expect(load(backend)).rejects.toThrow(desktopBackendServiceCopy);
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

test('surfaces nested non-retryable projection_unavailable without retry copy', async () => {
  const body = JSON.stringify({
    error: {
      code: 'projection_unavailable',
      retryable: false,
      action: 'none',
    },
  });
  const backend = backendFor(() => ({status: 503, body}));
  await expect(loadMemories(backend)).rejects.toThrow(
    desktopBackendUnavailableCopy,
  );
  await expect(loadTasks(backend)).rejects.toThrow(
    desktopBackendUnavailableCopy,
  );
  expect(desktopBackendUnavailableCopy).not.toBe(
    desktopProjectionUnavailableCopy,
  );
});

test('surfaces nested non-retryable 503s without connection-retry copy', async () => {
  const body = JSON.stringify({
    error: {
      code: 'development_backend_unsupported',
      retryable: false,
      action: 'none',
    },
  });
  const backend = backendFor(() => ({status: 503, body}));
  await expect(loadConversations(backend)).rejects.toThrow(
    desktopBackendUnavailableCopy,
  );
  expect(desktopBackendUnavailableCopy).not.toBe(desktopBackendServiceCopy);
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

test('accepts ratified partial completeness instead of treating honest pages as malformed', async () => {
  const memories = {
    ...page([memory], 'recall-completeness-v1'),
    completeness: {
      version: 'recall-completeness-v1',
      status: 'partial',
      reasons: ['source_bound'],
    },
  };
  const tasks = {
    ...page([task], 'tasks-completeness-v1'),
    completeness: {
      version: 'tasks-completeness-v1',
      status: 'partial',
      reasons: ['source_bound'],
    },
  };
  await expect(
    loadMemories(
      backendFor(() => ({status: 200, body: JSON.stringify(memories)})),
    ),
  ).resolves.toMatchObject({
    items: [expect.objectContaining({id: 'memory1_abc'})],
    page: {completenessStatus: 'partial', reasons: ['source_bound']},
  });
  await expect(
    loadTasks(backendFor(() => ({status: 200, body: JSON.stringify(tasks)}))),
  ).resolves.toMatchObject({
    items: [expect.objectContaining({id: 'task1_abc'})],
    page: {completenessStatus: 'partial', reasons: ['source_bound']},
  });
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
  const now = Date.UTC(2026, 7, 14, 23, 30);
  expect(taskGroup(Date.UTC(2026, 7, 14, 0, 0), now)).toBe('Today');
  expect(taskGroup(Date.UTC(2026, 7, 13, 0, 0), now)).toBe('Today');
  expect(taskGroup(Date.UTC(2026, 7, 15, 0, 0), now)).toBe('Tomorrow');
  expect(taskGroup(Date.UTC(2026, 7, 16, 0, 0), now)).toBe('Later');
  expect(taskGroup(null, now)).toBe('Later');
});

test('groups second-scale task dues on the same UTC day as millisecond dues', () => {
  const now = Date.UTC(2026, 7, 5, 12, 0);
  expect(taskGroup(1786000000, now)).toBe('Tomorrow');
  expect(taskGroup(1786000000000, now)).toBe('Tomorrow');
  expect(taskGroup(Date.UTC(2026, 7, 6, 7, 6, 40), now)).toBe('Tomorrow');
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
    body: JSON.stringify(conversationPage(conversations, true)),
  }));

  const result = await loadConversations(backend);
  expect(result.items).toHaveLength(50);
  expect(result.page).toEqual({
    windowStatus: 'more',
    complete: false,
    hasMore: true,
    nextCursor: 'next-page',
    completenessStatus: 'complete',
    reasons: [],
  });
});

test('keeps nullable conversation times while rejecting invalid metadata', async () => {
  const backend = backendFor(() => ({
    status: 200,
    body: JSON.stringify(
      conversationPage([{...conversation, startedAt: null, finishedAt: null}]),
    ),
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
    body: JSON.stringify(
      conversationPage([{...conversation, updatedAt: 'not-a-time'}]),
    ),
  }));
  await expect(loadConversations(malformed)).rejects.toThrow(
    'updatedAt is malformed',
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
    error: desktopBackendServiceCopy,
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

test('maps a cloud 403 to typed grant-denied copy without treating an empty body as success', async () => {
  const backend = backendFor(() => ({
    status: 403,
    body: JSON.stringify({items: []}),
  }));
  const result = await loadDesktopReads(backend);
  expect(result.conversations).toEqual({
    status: 'error',
    error: desktopBackendForbiddenCopy,
  });
  expect(result.memories).toEqual({
    status: 'error',
    error: desktopBackendForbiddenCopy,
  });
  expect(result.tasks).toEqual({
    status: 'error',
    error: desktopBackendForbiddenCopy,
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
  expect(snapshot.ownerError).toBeNull();
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

test('loadConnectors nested non-retryable 503s are unavailable without retry copy', async () => {
  const body = JSON.stringify({
    error: {
      code: 'development_backend_unsupported',
      retryable: false,
      action: 'none',
    },
  });
  const backend = backendFor(() => ({status: 503, body}));
  await expect(loadConnectors(backend)).rejects.toMatchObject({
    message: desktopAppsUnavailableCopy,
    retryable: false,
  });
  expect(cloudErrorCanRetry({message: desktopAppsUnavailableCopy})).toBe(true);
  expect(
    cloudErrorCanRetry(
      Object.assign(new Error(desktopAppsUnavailableCopy), {
        retryable: false,
      }),
    ),
  ).toBe(false);
});

test('loadConnectors nested non-retryable profile 503s do not claim the owner is still loading', async () => {
  const body = JSON.stringify({
    error: {
      code: 'development_backend_unsupported',
      retryable: false,
      action: 'none',
    },
  });
  const backend = backendFor(request => {
    if (request.path === '/v1/apps') {
      return {
        status: 200,
        body: JSON.stringify([{id: 'catalog-app-1', name: 'Owned app'}]),
      };
    }
    if (request.path === '/v1/apps/enabled') {
      return {status: 200, body: JSON.stringify([])};
    }
    if (request.path === '/v1/users/profile') {
      return {status: 503, body};
    }
    return {status: 404, body: null};
  });
  const snapshot = await loadConnectors(backend);
  expect(snapshot.ownerUid).toBeNull();
  expect(snapshot.ownerError).toBe(desktopAccountSettingUnavailableCopy);
  expect(snapshot.ownerError).not.toBe(desktopBackendUnavailableCopy);
});

test('loadConnectors nested non-retryable enabled 503s do not claim catalogue apps are installed', async () => {
  const body = JSON.stringify({
    error: {
      code: 'development_backend_unsupported',
      retryable: false,
      action: 'none',
    },
  });
  const backend = backendFor(request => {
    if (request.path === '/v1/apps') {
      return {
        status: 200,
        body: JSON.stringify([
          {id: 'catalog-app-1', name: 'Owned app', enabled: true},
        ]),
      };
    }
    if (request.path === '/v1/apps/enabled') {
      return {status: 503, body};
    }
    if (request.path === '/v1/users/profile') {
      return {status: 200, body: JSON.stringify({uid: 'user-1'})};
    }
    return {status: 404, body: null};
  });
  const snapshot = await loadConnectors(backend);
  expect(snapshot.enabledIds).toBeNull();
  expect(snapshot.enabledError).toBe(desktopAppsUnavailableCopy);
  expect(snapshot.enabledError).not.toBe(desktopBackendUnavailableCopy);
  expect(installedApps(snapshot)).toEqual([]);
  expect(exploreApps(snapshot).map(app => app.enabled)).toEqual([false]);
});

test('loadAccountSettings nested non-retryable 503s keep slices independent without retry copy', async () => {
  const body = JSON.stringify({
    error: {
      code: 'development_backend_unsupported',
      retryable: false,
      action: 'none',
    },
  });
  const backend = backendFor(request => {
    if (request.path === '/v1/users/profile') {
      return {status: 503, body};
    }
    if (request.path === '/v1/users/me/subscription') {
      return {
        status: 200,
        body: JSON.stringify({plan: 'plus', status: 'active'}),
      };
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
      return {status: 200, body: JSON.stringify({})};
    }
    return {status: 404, body: null};
  });
  const snapshot = await loadAccountSettings(backend);
  expect(snapshot.profile).toBeNull();
  expect(snapshot.profileError).toBe(desktopAccountSettingUnavailableCopy);
  expect(snapshot.profileError).not.toBe(desktopBackendUnavailableCopy);
  expect(snapshot.subscription).toEqual(
    expect.objectContaining({plan: 'plus', status: 'active'}),
  );
  expect(snapshot.storeRecordingPermission).toBe(true);
});

test('nested non-retryable account setting writes use unavailable copy', async () => {
  const body = JSON.stringify({
    error: {
      code: 'development_backend_unsupported',
      retryable: false,
      action: 'none',
    },
  });
  const backend = backendFor(() => ({status: 503, body}));
  const error = await optInTrainingData(backend).catch(reason => reason);
  expect(error).toMatchObject({
    message: desktopAccountSettingUnavailableCopy,
    retryable: false,
  });
  expect(cloudErrorCanRetry(error)).toBe(false);
});

test('omitted account setting 503 stays a retryable write failure', async () => {
  const backend = backendFor(() => ({
    status: 503,
    body: '{"error":"service_unavailable"}',
  }));
  const error = await optInTrainingData(backend).catch(e => e);
  expect(error).toBeInstanceOf(Error);
  expect((error as Error).message).toBe(
    'desktop-training-opt-in-write failed (503)',
  );
  expect(cloudErrorCanRetry(error)).toBe(true);
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
    'This saved data could not be loaded. Retry without changing it.',
  );
  expect(snapshot.storeRecordingPermission).toBe(true);
  expect(snapshot.trainingOptedIn).toBe(false);
  expect(snapshot.privateCloudSync).toBe(false);
  expect(snapshot.webhooks).toBeNull();
});

test('uses the ratified conversation cursor and preserves its completeness declaration', async () => {
  const paths: string[] = [];
  const backend = backendFor(request => {
    paths.push(request.path);
    return {
      status: 200,
      body: JSON.stringify(conversationPage([conversation], true)),
    };
  });
  const result = await loadConversations(backend, 'opaque/+ cursor=');
  expect(paths).toEqual([
    '/v1/conversations?limit=50&cursor=opaque%2F%2B%20cursor%3D',
  ]);
  expect(result.page.nextCursor).toBe('next-page');
  await expect(loadConversations(backend, '')).rejects.toThrow(
    'Conversation cursor is malformed',
  );
  expect(paths).toHaveLength(1);
});

test('rejects duplicate conversation IDs instead of merging an ambiguous page', async () => {
  await expect(
    loadConversations(
      backendFor(() => ({
        status: 200,
        body: JSON.stringify(conversationPage([conversation, conversation])),
      })),
    ),
  ).rejects.toThrow('Conversation IDs are duplicated');
});

test('groups canonical task millisecond timestamps without converting them twice', () => {
  const now = new Date(2026, 8, 7, 12).getTime();
  const item: DesktopReadProjection = {
    kind: 'task',
    id: 'task-time',
    title: 'Task',
    summary: '',
    searchableText: 'Task',
    completed: false,
    completedAt: null,
    dueAt: null,
    owner: null,
    source: 'manual',
    provenance: [],
    sortOrder: 0,
    indentLevel: 0,
    createdAt: now,
    updatedAt: now,
    revision: '1',
  };
  expect(projectionTimestamp(item)).toBe(now);
  expect(timelineGroups([item], now)).toEqual([
    {label: 'Today', items: [item]},
  ]);
});

test('task reads forward opaque cursors and classify stale cursor responses', async () => {
  const paths: string[] = [];
  const backend = backendFor(request => {
    paths.push(request.path);
    return {status: 400, body: null};
  });
  await expect(loadTasks(backend, 'opaque+/=')).rejects.toThrow(
    'Tasks changed',
  );
  expect(paths).toEqual(['/v1/tasks?cursor=opaque%2B%2F%3D']);
});

test('conversation capture provenance is optional and never replaces server timestamps', async () => {
  const result = await loadConversations(
    backendFor(() => ({
      status: 200,
      body: JSON.stringify(
        conversationPage([{...conversation, capturedAtMs: 0}]),
      ),
    })),
  );
  expect(result.items[0]!.capturedAtMs).toBe(0);
  expect(result.items[0]!.startedAt).toBe(
    new Date(conversation.startedAt).toISOString(),
  );
  const legacy = await loadConversations(
    backendFor(() => ({
      status: 200,
      body: JSON.stringify(conversationPage([conversation])),
    })),
  );
  expect(legacy.items[0]).not.toHaveProperty('capturedAtMs');
  for (const capturedAtMs of [null, -1, 1.5, '1000', 8640000000000001]) {
    await expect(
      loadConversations(
        backendFor(() => ({
          status: 200,
          body: JSON.stringify(
            conversationPage([{...conversation, capturedAtMs}]),
          ),
        })),
      ),
    ).rejects.toThrow('capturedAtMs');
  }
});
