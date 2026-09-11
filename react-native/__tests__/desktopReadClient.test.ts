import {readFileSync} from 'node:fs';
import {resolve} from 'node:path';
import {
  conversationDisplaySummary,
  conversationDisplayTitle,
  conversationListUsesListenOverview,
  conversationRecapTitle,
  conversationDiscardedTranscriptCopy,
  conversationDayLabel,
  conversationRecapDateLabel,
  conversationListNewCopy,
  conversationGroupLabel,
  conversationCaptureCopy,
  conversationPhotoCountCopy,
  conversationStatusCopy,
  conversationListStatusCopy,
  dataProtectionCopy,
  developerWebhookRowCopy,
  developerWebhookStatusCopy,
  developerWebhookTypeCopy,
  developerKeyCreatedCopy,
  developerKeyRowCopy,
  developerKeyScopeCopy,
  developerKeysCopy,
  appCategoryCopy,
  appDisplaySource,
  appDisplayAttribution,
  appDisplayName,
  appRatingCopy,
  appImageUrl,
  deviceDisplayName,
  accountFieldCopy,
  connectionIdentityCopy,
  chatMessageDisplayText,
  chatChartCopy,
  paintedChatContentBlock,
  taskCardDescription,
  chatAttachmentThumbnailUrl,
  chatSenderCopy,
  chatDaySummaryCopy,
  chatDaySummaryDateCopy,
  chatDaySummaryItems,
  chatDaySummaryRowCopy,
  chatAppAttributionCopy,
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
  MemoryCursorExpiredError,
  memoryDisplayBody,
  memoryDisplayTitle,
  memoryCitationCopy,
  memorySynthesisCopy,
  memoryLedgerSlotCopy,
  memoryLedgerPlaybookCopy,
  memoryBaselineCopy,
  memoryCaptureDeviceCopy,
  conversationListCategory,
  conversationListSourceTag,
  conversationListTag,
  conversationVisibilityCopy,
  parseMemoryText,
  chatClockLabel,
  clockLabel,
  formatTaskDue,
  projectionClockLabel,
  projectionTimestamp,
  subscriptionPlanCopy,
  subscriptionStatusCopy,
  usageStatsCopy,
  primaryLanguageCopy,
  peopleNameRows,
  firmwareUpdateCopy,
  fairUseCopy,
  fairUseBudgetResetCopy,
  dailySummaryDateCopy,
  dailySummaryCopy,
  dailySummaryDurationCopy,
  dailySummaryHourCopy,
  dailySummaryScheduleCopy,
  mentorNotificationFrequencyCopy,
  automaticTranslationCopy,
  customVocabularyCopy,
  subscriptionPeriodCopy,
  taskDisplaySummary,
  taskDisplayTitle,
  taskGroup,
  taskIndentPadding,
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
  loadServiceSettings,
  myApps,
  optInTrainingData,
  parseCloudApp,
  parseCloudApps,
  parseCloudProfile,
  parseCloudSubscription,
  parseCloudUsage,
  parseCloudLanguage,
  parseCloudLanguageNames,
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

  test('a NEXT LINE-only query keeps rows instead of claiming a miss', () => {
    expect(
      homeSearchItems([conversation], [task], '\u0085').map(item => item.id),
    ).toEqual(['task-search', 'conversation-search']);
    expect(
      homeSearchItems([conversation], [task], '').map(item => item.id),
    ).toEqual(['task-search', 'conversation-search']);
  });

  test('memory rows match visible speech instead of hidden citation ids', () => {
    const memory: DesktopReadProjection = {
      kind: 'memory',
      id: 'memory-search',
      title: 'The launch is Friday.',
      summary: 'The launch is Friday.',
      searchableText: 'The launch is Friday.',
      citations: ['citation-v1:launch'],
      timestamp: null,
      provenance: {
        label: null,
        synthesisVersion: 'synthesis-v1',
        inputDigest: 'a',
        outputDigest: 'b',
      },
    };
    expect(
      homeSearchItems([memory], [], 'citation-v1').map(item => item.id),
    ).toEqual([]);
    expect(
      homeSearchItems([memory], [], 'Friday').map(item => item.id),
    ).toEqual(['memory-search']);
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
          searchableText: 'The launch is Friday.',
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
  expect(conversationDisplayTitle({title: '\u0085', status: 'completed'})).toBe(
    'Conversation title unavailable',
  );
  expect(
    conversationDisplayTitle({title: 'Morning walk', status: 'processing'}),
  ).toBe('Morning walk');
  expect(
    conversationDisplayTitle({title: '  Morning walk  ', status: 'completed'}),
  ).toBe('Morning walk');
});

test('compact recaps keep list overview speech when GET title is empty', () => {
  expect(
    conversationRecapTitle({
      title: '',
      summary: 'Assistant words',
      status: 'in_progress',
    }),
  ).toBe('Assistant words');
  expect(
    conversationRecapTitle({
      title: '\u0085',
      summary: 'Assistant words',
      status: 'in_progress',
    }),
  ).toBe('Assistant words');
  expect(
    conversationRecapTitle({
      title: '',
      summary: '\u0085Assistant words',
      status: 'in_progress',
    }),
  ).toBe('Assistant words');
  expect(
    conversationRecapTitle({
      title: 'Morning walk',
      summary: 'Discussed the launch.',
      status: 'completed',
    }),
  ).toBe('Morning walk');
  expect(
    conversationRecapTitle({
      title: '',
      summary: '',
      status: 'processing',
    }),
  ).toBe('Processing conversation…');
  expect(
    conversationRecapTitle({
      title: '',
      summary: '',
      status: 'completed',
    }),
  ).toBe('Conversation title unavailable');
  expect(
    conversationRecapTitle({
      title: '',
      summary: '\u0085',
      status: 'completed',
    }),
  ).toBe('Conversation title unavailable');
  expect(
    conversationRecapTitle({
      id: 'recording:session-1',
      title: `${'a'.repeat(80)}`,
      summary: `${'a'.repeat(80)} later speech`,
      status: 'completed',
    }),
  ).toBe(`${'a'.repeat(80)} later speech`);
  expect(
    conversationRecapTitle({
      id: 'chat:named-session',
      title: 'Hi',
      summary: 'Hi there, here is the later turn',
      status: 'in_progress',
    }),
  ).toBe('Hi');
  expect(
    conversationRecapTitle({
      id: 'recording:',
      title: 'Short title',
      summary: 'Short title with later speech',
      status: 'completed',
    }),
  ).toBe('Short title');
  expect(
    conversationRecapTitle({
      id: 'conversation-one',
      title: `${'a'.repeat(80)}`,
      summary: `${'a'.repeat(80)} later speech`,
      status: 'completed',
    }),
  ).toBe(`${'a'.repeat(80)} later speech`);
  expect(
    conversationRecapTitle({
      id: '11111111-2222-4333-8444-555555555555',
      title: `${'a'.repeat(80)}`,
      summary: `${'a'.repeat(80)} later speech`,
      status: 'completed',
    }),
  ).toBe(`${'a'.repeat(80)} later speech`);
  expect(
    conversationRecapTitle({
      id: 'chat:named-session',
      title: `${'a'.repeat(80)}`,
      summary: `${'a'.repeat(80)} later speech`,
      status: 'in_progress',
    }),
  ).toBe(`${'a'.repeat(80)}`);
  expect(
    conversationListUsesListenOverview({
      id: 'conversation-one',
      title: `${'a'.repeat(80)}`,
      summary: `${'a'.repeat(80)} later speech`,
    }),
  ).toBe(true);
  expect(
    conversationListUsesListenOverview({
      id: 'chat:named-session',
      title: `${'a'.repeat(80)}`,
      summary: `${'a'.repeat(80)} later speech`,
    }),
  ).toBe(false);
  expect(
    conversationListUsesListenOverview({
      id: 'recording:',
      title: 'Short title',
      summary: 'Short title with later speech',
    }),
  ).toBe(false);
});

test('discarded conversation titles use Flutter transcript excerpt without people names', () => {
  expect(
    conversationDiscardedTranscriptCopy([
      {
        text: 'Hello',
        speaker: 'SPEAKER_00',
        isUser: false,
        start: 0,
        end: 2,
      },
      {
        text: 'Later',
        speaker: 'SPEAKER_01',
        isUser: false,
        start: 3,
        end: 5,
      },
    ]),
  ).toBe(
    '[00:00:00 - 00:00:02] Speaker 1: Hello \n\n[00:00:03 - 00:00:05] Speaker 2: Later',
  );
  expect(
    conversationDiscardedTranscriptCopy([
      {text: 'Hi', speaker: 'SPEAKER_00', isUser: true, start: 0, end: 1},
    ]),
  ).toBe('[00:00:00 - 00:00:01] User: Hi');
  expect(
    conversationDiscardedTranscriptCopy([
      {
        text: 'Hello',
        speaker: 'SPEAKER_00',
        isUser: false,
        start: 0,
        end: 5,
      },
      {
        text: 'Later',
        speaker: 'SPEAKER_01',
        isUser: false,
        start: 1,
        end: 6,
      },
    ]),
  ).toBe('Speaker 1: Hello \n\n Speaker 2: Later');
  expect(
    conversationDiscardedTranscriptCopy([
      {text: 'A', speaker: 'SPEAKER_05', isUser: false, start: 0, end: 1},
      {text: 'B', speaker: 'SPEAKER_06', isUser: false, start: 2, end: 3},
    ]),
  ).toBe(
    '[00:00:00 - 00:00:01] Speaker 1: A \n\n[00:00:02 - 00:00:03] Speaker 2: B',
  );
  expect(
    conversationDiscardedTranscriptCopy([
      {
        text: 'Named',
        speaker: 'SPEAKER_00',
        isUser: false,
        start: 0,
        end: 1,
        personId: 'person-1',
      },
    ]),
  ).toBe('[00:00:00 - 00:00:01] Speaker 1: Named');
  expect(
    conversationDiscardedTranscriptCopy([
      {text: 'a'.repeat(90), isUser: true, start: 0, end: 2},
    ]),
  ).toBe(`[00:00:00 - 00:00:02] User: ${'a'.repeat(90)}`.slice(-100));
  expect(conversationDiscardedTranscriptCopy([])).toBeNull();
  expect(
    conversationDiscardedTranscriptCopy([{text: ' \t\n', isUser: false}]),
  ).toBe('Speaker 1:');
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
  expect(conversationStatusCopy('\u0085')).toBe('Status unavailable');
  expect(conversationStatusCopy('queued')).toBe('queued');
  expect(conversationStatusCopy('  queued  ')).toBe('queued');
});

test('conversation list status copy names processing without Status on every chat', () => {
  expect(conversationListStatusCopy('failed')).toBe('Failed');
  expect(conversationListStatusCopy('processing')).toBe('Processing');
  expect(conversationListStatusCopy('merging')).toBe('Processing');
  expect(conversationListStatusCopy('in_progress')).toBeNull();
  expect(conversationListStatusCopy('completed')).toBeNull();
  expect(conversationListStatusCopy('queued')).toBeNull();
  expect(conversationListStatusCopy('')).toBeNull();
  expect(conversationListStatusCopy(' \t\n')).toBeNull();
});

test('account subscription copy is not a raw wire token', () => {
  expect(subscriptionPlanCopy('plus')).toBe('Plus');
  expect(subscriptionStatusCopy('active')).toBe('Active');
  expect(subscriptionStatusCopy('past_due')).toBe('Past due');
  expect(subscriptionPlanCopy('')).toBe('Plan unavailable');
  expect(subscriptionStatusCopy('')).toBe('Plan unavailable');
  expect(subscriptionPlanCopy('\u0085')).toBe('Plan unavailable');
  expect(dataProtectionCopy('standard')).toBe('Standard');
  expect(dataProtectionCopy('')).toBe('Data protection unavailable');
  expect(dataProtectionCopy('\u0085')).toBe('Data protection unavailable');
});

test('usage stats copy names GET today counts without Upgrade', () => {
  expect(
    usageStatsCopy({
      transcriptionSeconds: 90,
      wordsTranscribed: 12,
      insightsGained: 3,
      memoriesCreated: 1,
    }),
  ).toEqual([
    {title: 'Listening', copy: '2 minutes'},
    {title: 'Understanding', copy: '12 words'},
    {title: 'Providing', copy: '3 insights'},
    {title: 'Remembering', copy: '1 memories'},
  ]);
  expect(
    usageStatsCopy({
      transcriptionSeconds: 0,
      wordsTranscribed: 0,
      insightsGained: 0,
      memoriesCreated: 0,
    }),
  ).toBeNull();
  expect(usageStatsCopy(null)).toBeNull();
});

test('primary language copy names GET language without Not set', () => {
  expect(
    primaryLanguageCopy('en', [
      {code: 'en', name: 'English'},
      {code: 'es', name: 'Spanish'},
    ]),
  ).toBe('English');
  expect(primaryLanguageCopy('en', null)).toBe('en');
  expect(primaryLanguageCopy('', [{code: 'en', name: 'English'}])).toBeNull();
  expect(primaryLanguageCopy(null, [{code: 'en', name: 'English'}])).toBeNull();
  expect(primaryLanguageCopy('\u0085', [{code: 'en', name: 'English'}])).toBeNull();
});

test('people name rows keep GET names without empty entries', () => {
  expect(
    peopleNameRows(
      new Map([
        ['person-alex', 'Alex Chen'],
        ['person-sam', 'Sam'],
      ]),
    ),
  ).toEqual([
    {id: 'person-alex', name: 'Alex Chen'},
    {id: 'person-sam', name: 'Sam'},
  ]);
  expect(peopleNameRows(new Map())).toEqual([]);
});

test('fair use copy names GET stage hours and restrict budget without Upgrade', () => {
  expect(
    fairUseCopy({
      stage: 'restrict',
      caseRef: 'FU-1',
      message: 'Usage is restricted.',
      speechHoursToday: 2.4,
      speechHours3day: 8.1,
      speechHoursWeekly: 11,
      dailyHours: 2,
      threeDayHours: 8,
      weeklyHours: 10,
      dailyLimitMs: 1_800_000,
      usedMs: 1_800_000,
      exhausted: true,
      resetsAtMs: Date.parse('2026-09-11T05:00:00Z'),
    },
    new Date('2026-09-11T00:00:00Z'),
    ),
  ).toEqual([
    {title: 'Fair Use', copy: 'Restricted · FU-1'},
    {title: 'Today', copy: '2.4h / 2h'},
    {title: '3-Day Rolling', copy: '8.1h / 8h'},
    {title: 'Weekly Rolling', copy: '11.0h / 10h'},
    {title: 'Fair Use', copy: 'Usage is restricted.'},
    {title: 'Daily transcription', copy: '30m / 30m'},
    {
      title: 'Daily transcription',
      copy: 'Daily transcription limit reached',
    },
    {title: 'Daily transcription', copy: 'Resets 5h'},
  ]);
  expect(
    fairUseCopy({
      stage: 'restrict',
      caseRef: 'FU-1',
      message: 'Usage is restricted.',
      speechHoursToday: 2.4,
      speechHours3day: 8.1,
      speechHoursWeekly: 11,
      dailyHours: 2,
      threeDayHours: 8,
      weeklyHours: 10,
      dailyLimitMs: 1_800_000,
      usedMs: 1_800_000,
      exhausted: true,
    }),
  ).toEqual([
    {title: 'Fair Use', copy: 'Restricted · FU-1'},
    {title: 'Today', copy: '2.4h / 2h'},
    {title: '3-Day Rolling', copy: '8.1h / 8h'},
    {title: 'Weekly Rolling', copy: '11.0h / 10h'},
    {title: 'Fair Use', copy: 'Usage is restricted.'},
    {title: 'Daily transcription', copy: '30m / 30m'},
    {
      title: 'Daily transcription',
      copy: 'Daily transcription limit reached',
    },
  ]);
  expect(
    fairUseCopy({
      stage: 'none',
      caseRef: '',
      message: ' \t',
      speechHoursToday: 0,
      speechHours3day: 0,
      speechHoursWeekly: 0,
      dailyHours: 2,
      threeDayHours: 8,
      weeklyHours: 10,
      dailyLimitMs: 1_800_000,
      usedMs: 0,
      exhausted: false,
      resetsAtMs: Date.parse('2026-09-11T05:00:00Z'),
    }),
  ).toEqual([
    {title: 'Today', copy: '0.0h / 2h'},
    {title: '3-Day Rolling', copy: '0.0h / 8h'},
    {title: 'Weekly Rolling', copy: '0.0h / 10h'},
  ]);
  expect(fairUseCopy(null)).toBeNull();
  const now = new Date('2026-09-11T00:00:00Z');
  expect(fairUseBudgetResetCopy(Date.parse('2026-09-11T05:00:00Z'), now)).toBe(
    'Resets 5h',
  );
  expect(fairUseBudgetResetCopy(Date.parse('2026-09-11T00:45:00Z'), now)).toBe(
    'Resets 45m',
  );
  expect(fairUseBudgetResetCopy(Date.parse('2026-09-11T01:30:00Z'), now)).toBe(
    'Resets 1h',
  );
  expect(fairUseBudgetResetCopy(Date.parse('2026-09-10T23:00:00Z'), now)).toBe(
    '',
  );
  expect(fairUseBudgetResetCopy(undefined, now)).toBe('');
});

test('daily summary copy names GET headlines without inventing Your Day in Review', () => {
  const now = new Date(2026, 8, 10);
  expect(dailySummaryDateCopy('2026-09-10', now)).toBe('Today');
  expect(dailySummaryDateCopy('2026-09-09', now)).toBe('Yesterday');
  expect(dailySummaryDateCopy('2026-09-08', now)).toBe('Tue, Sep 8');
  expect(dailySummaryDateCopy('not-a-date', now)).toBe('not-a-date');
  expect(dailySummaryDateCopy('2026-02-31', now)).toBe('2026-02-31');
  expect(
    dailySummaryCopy(
      [
        {id: 'sum-1', date: '2026-09-10', headline: 'Met with the team'},
        {id: 'sum-2', date: '', headline: 'Shipped the recap'},
        {id: 'sum-empty', date: '2026-09-08', headline: ' \t'},
        {
          id: 'sum-stats',
          date: '2026-09-10',
          headline: 'Shipped the recap',
          dayEmoji: '🎯',
          conversations: 3,
          actionItems: 1,
          durationMinutes: 90,
          watchingMinutes: 10,
          proactiveMoments: 1,
        },
      ],
      now,
    ),
  ).toEqual([
    {title: 'Daily summary', copy: 'Today · Met with the team'},
    {title: 'Daily summary', copy: 'Shipped the recap'},
    {
      title: 'Daily summary',
      copy: '🎯 Today · Shipped the recap · 3 conversations · 1h 30m · 1 action item · 10m watching · 1 proactive moment',
    },
  ]);
  expect(dailySummaryDurationCopy(45)).toBe('45m');
  expect(dailySummaryDurationCopy(60)).toBe('1h');
  expect(dailySummaryDurationCopy(90)).toBe('1h 30m');
  expect(dailySummaryDurationCopy(0)).toBe('');
});

test('daily summary schedule copy names GET hour without Flutter 10:00 PM default', () => {
  expect(dailySummaryHourCopy(0)).toBe('12:00 AM');
  expect(dailySummaryHourCopy(12)).toBe('12:00 PM');
  expect(dailySummaryHourCopy(22)).toBe('10:00 PM');
  expect(dailySummaryHourCopy(23)).toBe('11:00 PM');
  expect(dailySummaryScheduleCopy({enabled: true, hour: 22})).toEqual([
    {title: 'Daily summaries', copy: 'Enabled'},
    {title: 'Delivery time', copy: '10:00 PM'},
  ]);
  expect(dailySummaryScheduleCopy({enabled: false, hour: 0})).toEqual([
    {title: 'Daily summaries', copy: 'Off'},
    {title: 'Delivery time', copy: '12:00 AM'},
  ]);
  expect(dailySummaryScheduleCopy(null)).toEqual([]);
  expect(dailySummaryScheduleCopy(undefined)).toEqual([]);
});

test('mentor notification copy names GET frequency without Balanced default', () => {
  expect(mentorNotificationFrequencyCopy(0)).toEqual([
    {title: 'Notification frequency', copy: 'Off'},
  ]);
  expect(mentorNotificationFrequencyCopy(1)).toEqual([
    {title: 'Notification frequency', copy: 'Minimal'},
  ]);
  expect(mentorNotificationFrequencyCopy(2)).toEqual([
    {title: 'Notification frequency', copy: 'Low'},
  ]);
  expect(mentorNotificationFrequencyCopy(3)).toEqual([
    {title: 'Notification frequency', copy: 'Balanced'},
  ]);
  expect(mentorNotificationFrequencyCopy(4)).toEqual([
    {title: 'Notification frequency', copy: 'High'},
  ]);
  expect(mentorNotificationFrequencyCopy(5)).toEqual([
    {title: 'Notification frequency', copy: 'Maximum'},
  ]);
  expect(mentorNotificationFrequencyCopy(6)).toEqual([]);
  expect(mentorNotificationFrequencyCopy(-1)).toEqual([]);
  expect(mentorNotificationFrequencyCopy(null)).toEqual([]);
});

test('transcription preference copy names GET vocabulary without Flutter false defaults', () => {
  expect(automaticTranslationCopy(true)).toEqual([
    {title: 'Automatic translation', copy: 'Off'},
  ]);
  expect(automaticTranslationCopy(false)).toEqual([
    {title: 'Automatic translation', copy: 'Enabled'},
  ]);
  expect(automaticTranslationCopy(undefined)).toEqual([]);
  expect(automaticTranslationCopy(null)).toEqual([]);
  expect(customVocabularyCopy(['Omi', ' \t', 'Based Hardware'])).toEqual([
    {title: 'Custom vocabulary', copy: 'Omi'},
    {title: 'Custom vocabulary', copy: 'Based Hardware'},
  ]);
  expect(customVocabularyCopy([])).toEqual([]);
  expect(customVocabularyCopy(null)).toEqual([]);
});

test('firmware update copy names GET latest without Available on current or draft', () => {
  expect(
    firmwareUpdateCopy('1.2.3', {
      version: '1.3.0',
      draft: false,
      minVersion: null,
    }),
  ).toEqual({latest: '1.3.0', available: true});
  expect(
    firmwareUpdateCopy('1.3.0', {
      version: '1.3.0',
      draft: false,
      minVersion: null,
    }),
  ).toEqual({latest: '1.3.0', available: false});
  expect(
    firmwareUpdateCopy('1.2.3', {
      version: '1.3.0',
      draft: true,
      minVersion: null,
    }),
  ).toBeNull();
  expect(
    firmwareUpdateCopy('0.9.0', {
      version: '1.3.0',
      draft: false,
      minVersion: '1.0.0',
    }),
  ).toEqual({latest: '1.3.0', available: false});
  expect(
    firmwareUpdateCopy('1.2.3', {
      version: '1.2.3-beta',
      draft: false,
      minVersion: null,
    }),
  ).toEqual({latest: '1.2.3-beta', available: false});
  expect(firmwareUpdateCopy('1.2.3', null)).toBeNull();
  expect(
    firmwareUpdateCopy('1.2.3', {
      version: '1.3.0',
      draft: false,
      minVersion: null,
      changelog: ['Fixed BLE reconnect', '  ', 'Battery improvements'],
    }),
  ).toEqual({
    latest: '1.3.0',
    available: true,
    changelog: ['Fixed BLE reconnect', 'Battery improvements'],
  });
  expect(
    firmwareUpdateCopy('1.2.3', {
      version: '1.3.0',
      draft: true,
      minVersion: null,
      changelog: ['Fixed BLE reconnect'],
    }),
  ).toBeNull();
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

test('developer key copy names GET name and prefix without a full secret', () => {
  const createdAtMs = Date.parse('2026-09-09T12:00:00.000Z');
  const created = developerKeyCreatedCopy(createdAtMs);
  expect(
    developerKeysCopy(
      [
        {name: 'Local', keyPrefix: 'omi_sk_ab', createdAtMs},
        {name: ' \t', keyPrefix: 'omi_sk_cd', createdAtMs},
        {name: 'Cursor', keyPrefix: ''},
        {
          name: 'Scoped',
          keyPrefix: 'omi_sk_gh',
          createdAtMs,
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
      ],
      'Developer key',
    ),
  ).toEqual([
    {title: 'Developer key', copy: `Local · omi_sk_ab · ${created}`},
    {title: 'Developer key', copy: 'Cursor'},
    {
      title: 'Developer key',
      copy: `Scoped · omi_sk_gh · ${created} · Full Access`,
    },
  ]);
  expect(developerKeyRowCopy({name: '', keyPrefix: 'omi_sk_ab'})).toBe('');
  expect(developerKeyCreatedCopy(0)).toBe('');
  expect(developerKeyScopeCopy(undefined)).toBe('');
  expect(developerKeyScopeCopy([])).toBe('');
  expect(
    developerKeyScopeCopy([
      'conversations:read',
      'memories:read',
      'action_items:read',
      'goals:read',
    ]),
  ).toBe('Read');
  expect(developerKeyScopeCopy(['conversations:write'])).toBe('Write');
  expect(
    developerKeyScopeCopy(['conversations:read', 'conversations:write']),
  ).toBe('Read · Write');
  expect(
    developerKeyScopeCopy([
      'conversations:read',
      'memories:read',
      'action_items:read',
      'goals:read',
      'conversations:read',
      'memories:read',
      'action_items:read',
      'goals:read',
    ]),
  ).toBe('Read');
});

test('developer webhook status copy does not say unknown for a missing enablement bit', () => {
  expect(developerWebhookStatusCopy(true)).toBe('Enabled');
  expect(developerWebhookStatusCopy(false)).toBe('Disabled');
  expect(developerWebhookStatusCopy(null)).toBe('Status unavailable');
});

test('developer webhook rows omit empty or whitespace URLs', () => {
  expect(
    developerWebhookRowCopy({
      enabled: true,
      url: 'https://example.test/conversation',
    }),
  ).toBe('Enabled · https://example.test/conversation');
  expect(developerWebhookRowCopy({enabled: false, url: null})).toBe('Disabled');
  expect(developerWebhookRowCopy({enabled: true, url: ''})).toBe('Enabled');
  expect(developerWebhookRowCopy({enabled: true, url: ' \t\n'})).toBe(
    'Enabled',
  );
  expect(developerWebhookRowCopy({enabled: true, url: '\u0085'})).toBe(
    'Enabled',
  );
  expect(developerWebhookRowCopy({enabled: null, url: '\u00A0'})).toBe(
    'Status unavailable',
  );
  expect(
    developerWebhookRowCopy({enabled: true, url: '  https://example.test/a  '}),
  ).toBe('Enabled · https://example.test/a');
  expect(
    developerWebhookRowCopy({
      enabled: true,
      url: 'https://example.test/audio',
      intervalSeconds: '5',
    }),
  ).toBe('Enabled · https://example.test/audio · 5s');
  expect(
    developerWebhookRowCopy({
      enabled: true,
      url: null,
      intervalSeconds: '12',
    }),
  ).toBe('Enabled · 12s');
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
  expect(connectionIdentityCopy({displayName: '\u0085', email: '\u0085'})).toBe(
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
      author: '\u0085',
      category: '\u0085',
      description: '\u0085',
    }),
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

test('app attribution keeps category when an author is present', () => {
  expect(
    appDisplayAttribution({
      author: '  Omi  ',
      category: 'productivity',
    }),
  ).toBe('Productivity · Omi');
  expect(
    appDisplayAttribution({
      author: '',
      category: 'productivity',
    }),
  ).toBe('Productivity');
  expect(
    appDisplayAttribution({
      author: 'Omi',
      category: '',
    }),
  ).toBe('Omi');
  expect(
    appDisplayAttribution({
      author: ' \t\n',
      category: ' \t',
    }),
  ).toBe('');
});

test('empty app names stay visible instead of a blank title', () => {
  expect(appDisplayName('')).toBe('App name unavailable');
  expect(appDisplayName(' \t\n')).toBe('App name unavailable');
  expect(appDisplayName('\u00A0')).toBe('App name unavailable');
  expect(appDisplayName('  Owned app  ')).toBe('Owned app');
});

test('app rating copy keeps GET scores instead of inventing zeros', () => {
  expect(appRatingCopy(4.5, 12)).toBe('4.5 (12)');
  expect(appRatingCopy(4, 0)).toBe('4.0 (0)');
  expect(appRatingCopy(4.5, null)).toBe('4.5');
  expect(appRatingCopy(null, 12)).toBe(null);
  expect(appRatingCopy(undefined, undefined)).toBe(null);
  expect(appRatingCopy(Number.NaN, 12)).toBe(null);
  expect(appRatingCopy(4.5, -1)).toBe('4.5');
});

test('app image URLs keep GET http(s) images instead of inventing a GitHub host', () => {
  expect(appImageUrl('https://cdn.example.test/app.png')).toBe(
    'https://cdn.example.test/app.png',
  );
  expect(appImageUrl('http://cdn.example.test/app.png')).toBe(
    'http://cdn.example.test/app.png',
  );
  expect(appImageUrl('  HTTPS://cdn.example.test/app.png  ')).toBe(
    'HTTPS://cdn.example.test/app.png',
  );
  expect(appImageUrl('/assets/apps/foo.png')).toBe(null);
  expect(appImageUrl('assets/foo.png')).toBe(null);
  expect(appImageUrl('javascript:https://evil.test')).toBe(null);
  expect(appImageUrl('data:image/png;base64,abc')).toBe(null);
  expect(appImageUrl('')).toBe(null);
  expect(appImageUrl(' \t\n')).toBe(null);
  expect(appImageUrl('\u0085')).toBe(null);
  expect(appImageUrl(null)).toBe(null);
  expect(appImageUrl(undefined)).toBe(null);
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
      text: '\u0085',
      generationOutcome: 'completed',
    }),
  ).toBe('Message text unavailable');
  expect(
    chatMessageDisplayText({
      text: '',
      generationOutcome: 'completed',
      contentBlocks: [{eyebrow: 'Discovery', title: 'Quiet mornings'}],
    }),
  ).toBe('');
  expect(
    chatMessageDisplayText({
      text: 'Tool - Search',
      generationOutcome: 'completed',
    }),
  ).toBe('Tool - Search');
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

test('chat message copy names GET chart points and omits empty charts', () => {
  expect(
    chatChartCopy({
      title: 'Talk time',
      points: [
        {label: 'Mon', value: 12},
        {label: ' \t', value: 1},
        {label: 'Tue', value: 15},
      ],
    }),
  ).toBe('Talk time\nMon · 12\nTue · 15');
  expect(
    chatMessageDisplayText({
      text: 'Here is the trend.',
      generationOutcome: null,
      chart: {
        title: 'Talk time',
        points: [
          {label: 'Mon', value: 12},
          {label: 'Tue', value: 15},
        ],
      },
    }),
  ).toBe('Here is the trend.\nTalk time\nMon · 12\nTue · 15');
  expect(
    chatChartCopy({
      title: 'Talk time',
      points: [{label: ' \t', value: 12}],
    }),
  ).toBeNull();
});

test('task card chrome names loaded GET task description and omits ids', () => {
  const tasks = [
    {id: 'task-join', title: 'Send the follow-up notes'},
    {id: 'other', taskId: 'task-alias', title: 'Alias description'},
  ];
  expect(taskCardDescription('task-join', tasks)).toBe(
    'Send the follow-up notes',
  );
  expect(taskCardDescription('task-alias', tasks)).toBe('Alias description');
  expect(taskCardDescription('missing', tasks)).toBeUndefined();
  expect(
    paintedChatContentBlock({eyebrow: 'Task', taskId: 'task-join'}, tasks),
  ).toEqual({eyebrow: 'Task', title: 'Send the follow-up notes'});
  expect(
    paintedChatContentBlock({eyebrow: 'Task', taskId: 'missing'}, tasks),
  ).toEqual({eyebrow: 'Task'});
  expect(
    JSON.stringify(
      paintedChatContentBlock({eyebrow: 'Task', taskId: 'task-join'}, tasks),
    ),
  ).not.toContain('task-join');
  expect(
    paintedChatContentBlock({eyebrow: 'Task', taskId: 'task-join'}, tasks),
  ).not.toHaveProperty('taskId');
  expect(
    paintedChatContentBlock(
      {eyebrow: 'Memory', title: 'Prefers concise notes', taskId: 'task-join'},
      tasks,
    ),
  ).toEqual({eyebrow: 'Memory', title: 'Prefers concise notes'});
});

test('chat attachment thumbnails keep http image GET urls and omit local or non-image paths', () => {
  expect(
    chatAttachmentThumbnailUrl({
      mediaType: 'image/png',
      thumbnail: 'https://cdn.example/photo.png',
    }),
  ).toBe('https://cdn.example/photo.png');
  expect(
    chatAttachmentThumbnailUrl({
      mediaType: 'image/jpeg',
      thumbnail: ' http://cdn.example/photo.jpg ',
    }),
  ).toBe('http://cdn.example/photo.jpg');
  expect(
    chatAttachmentThumbnailUrl({
      mediaType: 'image/png',
      thumbnail: '/tmp/photo.png',
    }),
  ).toBeNull();
  expect(
    chatAttachmentThumbnailUrl({
      mediaType: 'image/png',
      thumbnail: 'file:///tmp/photo.png',
    }),
  ).toBeNull();
  expect(
    chatAttachmentThumbnailUrl({
      mediaType: 'text/plain',
      thumbnail: 'https://cdn.example/notes.png',
    }),
  ).toBeNull();
  expect(
    chatAttachmentThumbnailUrl({
      mediaType: 'image/png',
      thumbnail: ' \t\n',
    }),
  ).toBeNull();
});

test('empty chat bodies still show attachment names from history', () => {
  expect(
    chatMessageDisplayText({
      text: ' \t\n',
      generationOutcome: null,
      attachments: [
        {
          displayName: 'notes.txt',
        },
      ],
    }),
  ).toBe('notes.txt');
  expect(
    chatMessageDisplayText({
      text: '',
      generationOutcome: 'completed',
      attachments: [
        {
          displayName: ' \t\n',
        },
      ],
    }),
  ).toBe('Attachment name unavailable');
  expect(
    chatMessageDisplayText({
      text: '  Hello  ',
      generationOutcome: null,
      attachments: [
        {
          displayName: 'notes.txt',
        },
      ],
    }),
  ).toBe('Hello\nnotes.txt');
  expect(
    chatMessageDisplayText({
      text: '',
      generationOutcome: 'cancelled',
      attachments: [
        {
          displayName: 'notes.txt',
        },
      ],
    }),
  ).toBe('Response stopped');
  expect(
    chatMessageDisplayText({
      text: '',
      generationOutcome: null,
      attachments: [
        {
          displayName: 'notes.txt',
          mediaType: 'text/plain',
          sizeBytes: 12,
        },
      ],
    }),
  ).toBe('notes.txt · Text · 12 B');
  expect(
    chatMessageDisplayText({
      text: 'Here is the note.',
      generationOutcome: null,
      attachments: [
        {
          displayName: 'notes.txt',
          mediaType: 'text/plain',
        },
      ],
    }),
  ).toBe('Here is the note.\nnotes.txt · Text');
  expect(
    chatMessageDisplayText({
      text: '  Hello  ',
      generationOutcome: null,
      attachments: [
        {
          displayName: 'meeting-notes.pdf',
          mediaType: 'application/pdf',
          sizeBytes: 2048,
        },
      ],
    }),
  ).toBe('Hello\nmeeting-notes.pdf · PDF · 2 KB');
  expect(
    chatMessageDisplayText({
      text: '',
      generationOutcome: 'completed',
      attachments: [
        {
          displayName: ' \t\n',
          mediaType: 'application/octet-stream',
          sizeBytes: 0,
        },
      ],
    }),
  ).toBe('Attachment name unavailable · Size unavailable');
});

test('unknown chat senders stay visible instead of failing the history page', () => {
  expect(chatSenderCopy('human')).toBe('You');
  expect(chatSenderCopy('ai')).toBe('Omi');
  expect(chatSenderCopy('unknown')).toBe('Sender unavailable');
});

test('chat day_summary GET type names Day Summary instead of a normal turn', () => {
  expect(chatDaySummaryCopy('day_summary')).toBe('Day Summary');
  expect(chatDaySummaryCopy('text')).toBe('');
  expect(chatDaySummaryCopy('unknown')).toBe('');
  expect(chatDaySummaryCopy(undefined)).toBe('');
});

test('chat day_summary GET createdAt names Flutter MMM, dd without inventing 📅', () => {
  const createdAt = Date.parse('2026-09-07T12:00:00.000Z');
  expect(chatDaySummaryDateCopy(0)).toBe('');
  expect(chatDaySummaryDateCopy(-1)).toBe('');
  expect(chatDaySummaryDateCopy(8_640_000_000_000_001)).toBe('');
  expect(chatDaySummaryCopy('day_summary', 0)).toBe('Day Summary');
  expect(chatDaySummaryCopy('day_summary', -1)).toBe('Day Summary');
  expect(chatDaySummaryCopy('day_summary', 8_640_000_000_000_001)).toBe(
    'Day Summary',
  );
  expect(chatDaySummaryDateCopy(createdAt)).toMatch(/^[A-Za-z]{3}, \d{2}$/);
  expect(chatDaySummaryDateCopy(createdAt)).not.toContain('📅');
  expect(chatDaySummaryDateCopy(createdAt)).not.toContain('1970');
  expect(chatDaySummaryCopy('day_summary', createdAt)).toBe(
    `Day Summary ~ ${chatDaySummaryDateCopy(createdAt)}`,
  );
  expect(chatDaySummaryCopy('day_summary', createdAt)).not.toContain('📅');
  expect(chatDaySummaryCopy('day_summary', createdAt)).not.toContain('1970');
});

test('chat day_summary GET text splits like Flutter DaySummaryWidget.splitMessage', () => {
  expect(chatDaySummaryItems('')).toEqual([]);
  expect(chatDaySummaryItems('   ')).toEqual([]);
  expect(chatDaySummaryItems('Yesterday you captured two meetings.')).toEqual([
    'Yesterday you captured two meetings',
  ]);
  expect(chatDaySummaryItems('First thing. Second thing.')).toEqual([
    'First thing',
    'Second thing',
  ]);
  expect(chatDaySummaryItems('1. Alpha. 2. Beta.')).toEqual([
    'Alpha',
    'Beta.',
  ]);
  expect(chatDaySummaryItems('1. Alpha\n2. Beta')).toEqual(['Alpha', 'Beta']);
  expect(chatDaySummaryRowCopy(0, 'Alpha')).toBe('1. Alpha');
  expect(chatDaySummaryRowCopy(1, 'Beta.')).toBe('2. Beta.');
});

test('chat app attribution names a resolved GET app and omits empty names', () => {
  expect(chatAppAttributionCopy('Notes')).toBe('Notes');
  expect(chatAppAttributionCopy(' \t')).toBe('');
  expect(chatAppAttributionCopy(undefined)).toBe('');
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
  expect(memoryCitationCopy([''])).toBe('0 citations');
  expect(memoryCitationCopy([' \t', '\n'])).toBe('0 citations');
  expect(memoryCitationCopy(['', 'citation-v1:launch'])).toBe('1 citation');
  expect(
    memorySynthesisCopy({provenance: {synthesisVersion: null}}),
  ).toBeNull();
  expect(
    memorySynthesisCopy({provenance: {synthesisVersion: ' \t\n'}}),
  ).toBeNull();
  expect(
    memorySynthesisCopy({provenance: {synthesisVersion: '\u0085'}}),
  ).toBeNull();
  expect(memorySynthesisCopy({provenance: {synthesisVersion: '1'}})).toBe(
    'Synthesized memory',
  );
});

test('Omi memory ledger chrome names GET slot, playbook body, baseline, and known devices', () => {
  expect(memoryLedgerSlotCopy({})).toBeNull();
  expect(memoryLedgerSlotCopy({ledgerSlot: ' \t\n'})).toBeNull();
  expect(memoryLedgerSlotCopy({ledgerSlot: 'identity.full_name'})).toBe(
    'identity.full_name',
  );
  expect(memoryLedgerPlaybookCopy({})).toBeNull();
  expect(memoryLedgerPlaybookCopy({ledgerBody: '\u0085'})).toBeNull();
  expect(
    memoryLedgerPlaybookCopy({ledgerBody: 'Open with the weekly recap.'}),
  ).toBe('Open with the weekly recap.');
  expect(memoryBaselineCopy({})).toBeNull();
  expect(memoryBaselineCopy({isBaseline: false})).toBeNull();
  expect(memoryBaselineCopy({isBaseline: true})).toBe('Baseline Memory');
  expect(memoryCaptureDeviceCopy(null)).toBeNull();
  expect(memoryCaptureDeviceCopy(' \t')).toBeNull();
  expect(memoryCaptureDeviceCopy('windows_ab12cd34')).toBeNull();
  expect(memoryCaptureDeviceCopy('macos_ab12cd34')).toBe('Mac');
  expect(memoryCaptureDeviceCopy('ios_ab12cd34')).toBe('iPhone');
  expect(memoryCaptureDeviceCopy('android_ab12cd34')).toBe('Android');
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
  expect(taskDisplaySummary({completed: false, dueAt: null})).toBe(
    'No due date',
  );
  expect(taskDisplaySummary({completed: true, dueAt: secondScaleDue})).toBe(
    `Completed · ${secondScaleCopy}`,
  );
  expect(taskDisplaySummary({completed: true, dueAt: null})).toBe(
    'Completed · No due date',
  );
  expect(formatTaskDue(null)).toBe('No due date');
  expect(formatTaskDue(0)).toBe('Date unavailable');
  expect(formatTaskDue(0)).not.toContain('1970');
  expect(taskDisplaySummary({completed: false, dueAt: 0})).toBe(
    'Date unavailable',
  );
  expect(taskGroup(0, Date.now())).toBe('Later');
});

test('an out-of-range task due timestamp says Date unavailable instead of Invalid Date', () => {
  expect(formatTaskDue(8_640_000_000_000_001)).toBe('Date unavailable');
  expect(formatTaskDue(8_640_000_000_000_001)).not.toContain('Invalid Date');
  expect(
    taskDisplaySummary({completed: false, dueAt: 8_640_000_000_000_001}),
  ).toBe('Date unavailable');
  expect(
    taskDisplaySummary({completed: true, dueAt: 8_640_000_000_000_001}),
  ).toBe('Completed · Date unavailable');
});

test('empty task titles stay visible instead of a blank row', () => {
  expect(taskDisplayTitle({title: ''})).toBe('Task title unavailable');
  expect(taskDisplayTitle({title: ' \t\n'})).toBe('Task title unavailable');
  expect(taskDisplayTitle({title: '\u0085'})).toBe('Task title unavailable');
  expect(taskDisplayTitle({title: 'Prepare demo'})).toBe('Prepare demo');
  expect(taskDisplayTitle({title: '  Prepare demo  '})).toBe('Prepare demo');
});

test('task indent padding uses Flutter 28px steps instead of a flat list', () => {
  expect(taskIndentPadding(0)).toBe(0);
  expect(taskIndentPadding(-1)).toBe(0);
  expect(taskIndentPadding(Number.NaN)).toBe(0);
  expect(taskIndentPadding(Number.POSITIVE_INFINITY)).toBe(0);
  expect(taskIndentPadding(1)).toBe(28);
  expect(taskIndentPadding(2)).toBe(56);
  expect(taskIndentPadding(3)).toBe(84);
  expect(taskIndentPadding(4)).toBe(84);
  expect(taskIndentPadding(1.9)).toBe(28);
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
      summary: '\u0085',
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

test('conversation capture copy names GET capturedAtMs and never shows 1970', () => {
  const now = new Date(2026, 7, 14, 12, 0).getTime();
  const captured = new Date(2026, 7, 10, 12, 0).getTime();
  expect(conversationCaptureCopy(undefined, now)).toBeNull();
  expect(conversationCaptureCopy(captured, now)).toBe(
    `Captured (device time) · ${clockLabel(captured, now)}`,
  );
  expect(conversationCaptureCopy(0, now)).toBe(
    'Captured (device time) · Time unavailable',
  );
  expect(conversationCaptureCopy(0, now)).not.toContain('1970');
});

test('conversation photo count copy names GET photos without requiring discarded', () => {
  expect(conversationPhotoCountCopy({photoCount: 3})).toBe('3 photos');
  expect(conversationPhotoCountCopy({photoCount: 1})).toBe('1 photos');
  expect(conversationPhotoCountCopy({photoCount: 0})).toBeNull();
  expect(conversationPhotoCountCopy({})).toBeNull();
});

test('conversation list category names GET wire values and omits empty or discarded', () => {
  expect(conversationListCategory({discarded: false, category: 'work'})).toBe(
    'Work',
  );
  expect(conversationListCategory({discarded: false, category: 'other'})).toBe(
    'Other',
  );
  expect(
    conversationListCategory({discarded: false, category: ' \t\n'}),
  ).toBeNull();
  expect(conversationListCategory({discarded: false})).toBeNull();
  expect(
    conversationListCategory({discarded: true, category: 'work'}),
  ).toBeNull();
});

test('conversation list source tags name only Flutter GET remaps', () => {
  expect(conversationListSourceTag({source: 'screenpipe'})).toBe('Screenpipe');
  expect(conversationListSourceTag({source: 'openglass'})).toBe('OmiGlass');
  expect(conversationListSourceTag({source: 'sdcard'})).toBe('SD Card');
  expect(conversationListSourceTag({source: 'rayban_meta'})).toBe(
    'Ray-Ban Meta',
  );
  expect(conversationListSourceTag({source: 'omi'})).toBeNull();
  expect(conversationListSourceTag({source: 'phone'})).toBeNull();
  expect(conversationListSourceTag({source: ' \t\n'})).toBeNull();
  expect(
    conversationListTag({
      discarded: false,
      category: 'work',
      source: 'screenpipe',
    }),
  ).toBe('Screenpipe');
  expect(
    conversationListTag({
      discarded: true,
      category: 'work',
      source: 'screenpipe',
    }),
  ).toBe('Screenpipe');
  expect(
    conversationListTag({
      discarded: false,
      category: 'work',
      source: 'omi',
    }),
  ).toBe('Work');
});

test('conversation visibility copy names GET shared or public and omits private', () => {
  expect(conversationVisibilityCopy('shared')).toBe('Shared');
  expect(conversationVisibilityCopy('public')).toBe('Public');
  expect(conversationVisibilityCopy('private')).toBeNull();
  expect(conversationVisibilityCopy(' \t\n')).toBeNull();
  expect(conversationVisibilityCopy(undefined)).toBeNull();
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

test('conversation recap date labels keep Today as time and date older days', () => {
  const now = new Date(2026, 7, 14, 12, 0).getTime();
  const older = new Date(2026, 7, 10, 12, 0).toISOString();
  const time = (value: Date) =>
    value.toLocaleTimeString(undefined, {
      hour: 'numeric',
      minute: '2-digit',
    });
  const today = new Date(2026, 7, 14, 1, 0);
  expect(conversationRecapDateLabel(today.toISOString(), older, now)).toBe(
    time(today),
  );
  const yesterday = new Date(2026, 7, 13, 23, 0);
  expect(conversationRecapDateLabel(null, yesterday.toISOString(), now)).toBe(
    `Yesterday · ${time(yesterday)}`,
  );
  const olderDate = new Date(2026, 7, 10, 12, 0);
  expect(conversationRecapDateLabel(null, olderDate.toISOString(), now)).toBe(
    `${olderDate.toLocaleDateString(undefined, {
      day: 'numeric',
      month: 'short',
      year: 'numeric',
    })} · ${time(olderDate)}`,
  );
  expect(conversationRecapDateLabel(null, new Date(0).toISOString(), now)).toBe(
    'Time unavailable',
  );
});

test('conversation list New copy follows Flutter createdAt/finishedAt age', () => {
  const now = new Date(2026, 7, 14, 12, 0).getTime();
  expect(
    conversationListNewCopy(
      new Date(now - 30_000).toISOString(),
      null,
      now,
    ),
  ).toBe('New 🚀');
  expect(
    conversationListNewCopy(
      new Date(now - 90_000).toISOString(),
      new Date(now - 20_000).toISOString(),
      now,
    ),
  ).toBe('New 🚀');
  expect(
    conversationListNewCopy(
      new Date(now - 90_000).toISOString(),
      null,
      now,
    ),
  ).toBeNull();
  expect(
    conversationListNewCopy(new Date(now).toISOString(), null, now),
  ).toBeNull();
  expect(
    conversationListNewCopy(
      new Date(now + 5_000).toISOString(),
      null,
      now,
    ),
  ).toBeNull();
  expect(
    conversationListNewCopy(new Date(0).toISOString(), null, now),
  ).toBeNull();
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

test('an out-of-range clock timestamp says Time unavailable instead of throwing', () => {
  const now = Date.now();
  expect(clockLabel(8_640_000_000_000_001, now)).toBe('');
  expect(chatClockLabel(8_640_000_000_000_001, now)).toBe('');
  expect(conversationCaptureCopy(8_640_000_000_000_001, now)).toBe(
    'Captured (device time) · Time unavailable',
  );
  expect(developerKeyCreatedCopy(8_640_000_000_000_001)).toBe('');
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

test('indexes visible memory text instead of hidden citation ids', async () => {
  const result = await loadMemories(
    backendFor(() => ({
      status: 200,
      body: JSON.stringify(page([memory], 'recall-completeness-v1')),
    })),
  );
  expect(result.items[0]).toEqual(
    expect.objectContaining({
      id: 'memory1_abc',
      citations: ['citation-v1:launch'],
      searchableText: 'The launch is Friday.',
    }),
  );
  expect(result.items[0].searchableText).not.toContain('citation-v1');
  expect(homeSearchItems(result.items, [], 'citation-v1')).toEqual([]);
  expect(
    homeSearchItems(result.items, [], 'Friday').map(item => item.id),
  ).toEqual(['memory1_abc']);
});

test('separates a machine slug from visible memory text', () => {
  expect(parseMemoryText('quiet-river-lantern: The launch is Friday.')).toEqual(
    {
      body: 'The launch is Friday.',
      provenanceLabel: 'quiet-river-lantern',
    },
  );
  expect(
    parseMemoryText('quiet-river-lantern:\u0085The launch is Friday.'),
  ).toEqual({
    body: 'The launch is Friday.',
    provenanceLabel: 'quiet-river-lantern',
  });
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
  expect(
    parseMemoryText(
      'entity:qa:000008\u0085qa_memory (observed 2026-07-30T12:00:00.000Z).',
    ),
  ).toEqual({
    body: 'qa_memory (observed 2026-07-30T12:00:00.000Z).',
    provenanceLabel: 'entity:qa:000008',
  });
  expect(
    memoryDisplayTitle({
      title:
        'entity:qa:000008\u0085qa_memory (observed 2026-07-30T12:00:00.000Z).',
      summary: '',
    }),
  ).toBe('qa_memory (observed 2026-07-30T12:00:00.000Z).');
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

test('memory reads classify stale later-page cursors without treating first-page 400 as expiry', async () => {
  const paths: string[] = [];
  const backend = backendFor(request => {
    paths.push(request.path);
    return {status: 400, body: null};
  });
  await expect(loadMemories(backend, 'opaque/+ cursor=')).rejects.toThrow(
    MemoryCursorExpiredError,
  );
  expect(paths).toEqual([
    '/v1/memories?limit=50&cursor=opaque%2F%2B%20cursor%3D',
  ]);
  try {
    await loadMemories(backend);
    throw new Error('expected first-page 400 to fail');
  } catch (error) {
    expect(error).not.toBeInstanceOf(MemoryCursorExpiredError);
  }
  expect(paths).toEqual([
    '/v1/memories?limit=50&cursor=opaque%2F%2B%20cursor%3D',
    '/v1/memories?limit=50',
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

test('rejects an oversized memory cursor before issuing a read', async () => {
  const backend = backendFor(() => {
    throw new Error('unexpected request');
  });
  await expect(loadMemories(backend, 'm'.repeat(16385))).rejects.toThrow(
    'Memory cursor is malformed',
  );
});

test('rejects duplicate memory IDs instead of merging an ambiguous page', async () => {
  await expect(
    loadMemories(
      backendFor(() => ({
        status: 200,
        body: JSON.stringify(
          page([memory, memory], 'recall-completeness-v1'),
        ),
      })),
    ),
  ).rejects.toThrow('Memory IDs are duplicated');
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
  expect(taskGroup(Date.UTC(2026, 7, 13, 0, 0), now)).toBe('Overdue');
  expect(taskGroup(Date.UTC(2026, 7, 15, 0, 0), now)).toBe('Tomorrow');
  expect(taskGroup(Date.UTC(2026, 7, 16, 0, 0), now)).toBe('Later');
  expect(taskGroup(null, now)).toBe('No Deadline');
});

test('groups past-due task epochs as Overdue matching Flutter tasksOverdue', () => {
  const now = Date.UTC(2026, 7, 14, 12, 0);
  expect(taskGroup(Date.UTC(2026, 7, 13, 23, 59), now)).toBe('Overdue');
  expect(taskGroup(Date.UTC(2026, 7, 14, 0, 0), now)).toBe('Today');
  expect(taskGroup(0, now)).toBe('Later');
});

test('groups undated GET due_at as No Deadline matching Flutter tasksNoDeadline', () => {
  const now = Date.UTC(2026, 7, 14, 12, 0);
  expect(taskGroup(null, now, now)).toBe('No Deadline');
  expect(taskGroup(null, now, now - 7 * 86400000)).toBe('No Deadline');
  expect(taskGroup(null, now, now - 7 * 86400000 - 1)).toBe('Overdue');
  expect(taskGroup(null, now, null)).toBe('No Deadline');
  expect(taskGroup(0, now, now - 8 * 86400000)).toBe('Later');
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

test('keeps ratified empty task descriptions instead of failing the page', async () => {
  const result = await loadTasks(
    backendFor(() => ({
      status: 200,
      body: JSON.stringify(
        page(
          [
            {...task, description: ''},
            {...task, id: 'task2_abc', description: ' \t\n'},
            {...task, id: 'task3_abc', source: '', revision: ''},
          ],
          'tasks-completeness-v1',
        ),
      ),
    })),
  );
  expect(result.items).toEqual([
    expect.objectContaining({
      id: 'task1_abc',
      title: '',
      searchableText: 'Task title unavailable',
    }),
    expect.objectContaining({
      id: 'task2_abc',
      title: ' \t\n',
      searchableText: 'Task title unavailable',
    }),
    expect.objectContaining({
      id: 'task3_abc',
      title: 'Prepare launch notes',
      source: '',
      revision: '',
      searchableText: 'Prepare launch notes',
    }),
  ]);
});

test('keeps ratified memories that omit citations and provenance', async () => {
  const item = {...memory};
  delete (item as {citations?: unknown}).citations;
  delete (item as {provenance?: unknown}).provenance;
  const result = await loadMemories(
    backendFor(() => ({
      status: 200,
      body: JSON.stringify(
        page([item, {...memory, id: 'memory2_abc'}], 'recall-completeness-v1'),
      ),
    })),
  );
  expect(result.items).toEqual([
    expect.objectContaining({
      id: 'memory1_abc',
      citations: [],
      provenance: {
        label: null,
        synthesisVersion: null,
        inputDigest: null,
        outputDigest: null,
      },
    }),
    expect.objectContaining({
      id: 'memory2_abc',
      citations: ['citation-v1:launch'],
      provenance: expect.objectContaining({
        synthesisVersion: 'synthesis-v1',
        inputDigest: 'a'.repeat(64),
        outputDigest: 'b'.repeat(64),
      }),
    }),
  ]);
  expect(result.items[0]).not.toHaveProperty('ledgerSlot');
  expect(result.items[0]).not.toHaveProperty('ledgerBody');
  expect(result.items[0]).not.toHaveProperty('isBaseline');
  expect(result.items[0]).not.toHaveProperty('captureDeviceLabel');
});

test('canonical memories omit Omi ledger chrome even when extra keys are present', async () => {
  const result = await loadMemories(
    backendFor(() => ({
      status: 200,
      body: JSON.stringify(
        page(
          [
            {
              ...memory,
              slot: 'identity.full_name',
              body: 'Open with the weekly recap.',
              kind: 'document',
              ledger_schema_version: 'knowledge_ledger.v1',
              is_baseline: true,
              primary_capture_device: 'macos_ab12cd34',
            },
          ],
          'recall-completeness-v1',
        ),
      ),
    })),
  );
  expect(result.items[0]).not.toHaveProperty('ledgerSlot');
  expect(result.items[0]).not.toHaveProperty('ledgerBody');
  expect(result.items[0]).not.toHaveProperty('isBaseline');
  expect(result.items[0]).not.toHaveProperty('captureDeviceLabel');
});

test('canonical conversations omit Omi category chrome even when extra keys are present', async () => {
  const result = await loadConversations(
    backendFor(() => ({
      status: 200,
      body: JSON.stringify(
        conversationPage([{...conversation, category: 'work'}]),
      ),
    })),
  );
  expect(result.items[0]).not.toHaveProperty('category');
});

test('still fails closed for empty memory text', async () => {
  await expect(
    loadMemories(
      backendFor(() => ({
        status: 200,
        body: JSON.stringify(
          page([{...memory, text: ''}], 'recall-completeness-v1'),
        ),
      })),
    ),
  ).rejects.toThrow('Memory 0 text is malformed');
});

test('keeps empty conversation status and source instead of failing the page', async () => {
  const result = await loadConversations(
    backendFor(() => ({
      status: 200,
      body: JSON.stringify(
        conversationPage([
          {...conversation, status: ''},
          {...conversation, id: 'conversation-2', source: ''},
          {...conversation, id: 'conversation-3', status: ' \t\n'},
        ]),
      ),
    })),
  );
  expect(result.items).toEqual([
    expect.objectContaining({
      id: 'conversation-1',
      status: '',
      source: 'omi',
    }),
    expect.objectContaining({
      id: 'conversation-2',
      source: '',
      status: 'completed',
    }),
    expect.objectContaining({
      id: 'conversation-3',
      status: ' \t\n',
    }),
  ]);
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
      rating_avg: 4.5,
      rating_count: 12,
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
      ratingAvg: 4.5,
      ratingCount: 12,
    }),
  );
  expect(
    parseCloudApp(
      {id: 'catalog-app-2', name: 'Unrated app'},
      'App 1',
    ),
  ).toEqual(
    expect.objectContaining({
      ratingAvg: null,
      ratingCount: null,
      installs: 0,
      image: '',
    }),
  );
  expect(
    parseCloudApp(
      {
        id: 'catalog-app-image',
        name: 'Imaged app',
        image: 'https://cdn.example.test/app.png',
      },
      'App 2',
    ),
  ).toEqual(
    expect.objectContaining({
      image: 'https://cdn.example.test/app.png',
    }),
  );
  expect(
    parseCloudApp(
      {
        id: 'catalog-app-relative',
        name: 'Relative app',
        image: '/assets/apps/foo.png',
      },
      'App 3',
    ),
  ).toEqual(
    expect.objectContaining({
      image: '/assets/apps/foo.png',
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

test('keeps empty catalogue names instead of failing the Apps page', () => {
  expect(
    parseCloudApps(
      [
        {id: 'catalog-app-1', name: ''},
        {id: 'catalog-app-2', name: ' \t\n'},
        {id: 'catalog-app-3', name: 'Owned app'},
      ],
      'Apps response',
    ),
  ).toEqual([
    expect.objectContaining({id: 'catalog-app-1', name: ''}),
    expect.objectContaining({id: 'catalog-app-2', name: ' \t\n'}),
    expect.objectContaining({id: 'catalog-app-3', name: 'Owned app'}),
  ]);
  expect(() => parseCloudApp({id: 'catalog-app-1'}, 'App 0')).toThrow(
    'App 0 is malformed',
  );
});

test('names GET subscription quota integer strings instead of omitting Plan usage', () => {
  expect(
    parseCloudSubscription(
      {
        plan: 'plus',
        status: 'active',
        transcription_seconds_used: '90',
        transcription_seconds_limit: '1800',
        words_transcribed_used: '12',
        words_transcribed_limit: '10000',
        insights_gained_used: '3',
        insights_gained_limit: '500',
        chat_quota_used: '5.5',
        chat_quota_unit: 'messages',
        subscription: {
          plan: 'plus',
          status: 'active',
          limits: {
            chat_questions_per_month: '100',
            chat_cost_usd_per_month: '20.5',
          },
        },
      },
      'Subscription response',
    ),
  ).toEqual(
    expect.objectContaining({
      plan: 'plus',
      status: 'active',
      transcriptionSecondsUsed: 90,
      transcriptionSecondsLimit: 1800,
      wordsTranscribedUsed: 12,
      wordsTranscribedLimit: 10000,
      insightsGainedUsed: 3,
      insightsGainedLimit: 500,
      chatQuotaUsed: 5.5,
      chatQuotaUnit: 'messages',
      chatQuestionsPerMonth: 100,
      chatCostUsdPerMonth: 20.5,
    }),
  );
});

test('keeps empty subscription plan tokens instead of failing Settings Plan', () => {
  expect(
    parseCloudSubscription({plan: '', status: ''}, 'Subscription response'),
  ).toEqual(
    expect.objectContaining({
      plan: '',
      status: '',
      transcriptionSecondsUsed: null,
      transcriptionSecondsLimit: null,
      wordsTranscribedUsed: null,
      wordsTranscribedLimit: null,
      insightsGainedUsed: null,
      insightsGainedLimit: null,
      chatQuotaUsed: null,
      chatQuotaUnit: null,
    }),
  );
  expect(
    parseCloudSubscription(
      {plan: 'plus', status: 'active'},
      'Subscription response',
    ),
  ).toEqual(expect.objectContaining({plan: 'plus', status: 'active'}));
  expect(() =>
    parseCloudSubscription({status: 'active'}, 'Subscription response'),
  ).toThrow('Subscription response is malformed');
});

test('subscription period copy names GET words insights and chat quotas without Upgrade', () => {
  expect(
    subscriptionPeriodCopy({
      wordsTranscribedUsed: 12,
      wordsTranscribedLimit: 10000,
      insightsGainedUsed: 3,
      insightsGainedLimit: 500,
      chatQuotaUsed: 5,
      chatQuotaUnit: 'messages',
      chatQuestionsPerMonth: 100,
      chatCostUsdPerMonth: null,
    }),
  ).toEqual([
    {
      title: 'Words this month',
      copy: '12 of 10000 words used this month',
    },
    {
      title: 'Insights this month',
      copy: '3 of 500 insights gained this month',
    },
    {
      title: 'Chat this month',
      copy: '5 of 100 messages used this month',
    },
  ]);
  expect(
    subscriptionPeriodCopy({
      wordsTranscribedUsed: 0,
      wordsTranscribedLimit: 0,
      insightsGainedUsed: null,
      insightsGainedLimit: 500,
      chatQuotaUsed: 1.2,
      chatQuotaUnit: 'cost_usd',
      chatQuestionsPerMonth: null,
      chatCostUsdPerMonth: 20,
    }),
  ).toEqual([
    {title: 'Chat this month', copy: '$1.20 of $20 used this month'},
  ]);
  expect(
    parseCloudSubscription(
      {
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
      },
      'Subscription response',
    ),
  ).toEqual(
    expect.objectContaining({
      wordsTranscribedUsed: 12,
      wordsTranscribedLimit: 10000,
      insightsGainedUsed: 3,
      insightsGainedLimit: 500,
      chatQuotaUsed: 5,
      chatQuotaUnit: 'messages',
      chatQuestionsPerMonth: 100,
    }),
  );
  expect(subscriptionPeriodCopy(null)).toBeNull();
});

test('keeps an empty Settings entitlement limitKey instead of failing the page', async () => {
  const result = await loadServiceSettings(
    backendFor(() => ({
      status: 200,
      body: JSON.stringify({
        identity: {displayName: 'Local identity', email: ''},
        entitlement: {limitKey: '', used: 7, limit: 100},
      }),
    })),
  );
  expect(result).toEqual({
    identity: {displayName: 'Local identity', email: ''},
    entitlement: {
      planLabel: '',
      limitKey: '',
      used: 7,
      limit: 100,
      limitReached: false,
    },
  });
  await expect(
    loadServiceSettings(
      backendFor(() => ({
        status: 200,
        body: JSON.stringify({
          identity: {displayName: 'Local identity', email: ''},
          entitlement: {used: 7, limit: 100},
        }),
      })),
    ),
  ).rejects.toThrow('Usage allowance response is malformed');
});

test('keeps GET Settings planLabel instead of dropping the billing label', async () => {
  const result = await loadServiceSettings(
    backendFor(() => ({
      status: 200,
      body: JSON.stringify({
        identity: {displayName: 'Local identity', email: ''},
        entitlement: {
          planLabel: 'Omi Plus',
          limitKey: 'chat',
          used: 7,
          limit: 100,
        },
      }),
    })),
  );
  expect(result).toEqual({
    identity: {displayName: 'Local identity', email: ''},
    entitlement: {
      planLabel: 'Omi Plus',
      limitKey: 'chat',
      used: 7,
      limit: 100,
      limitReached: false,
    },
  });
});

test('keeps GET Settings limitReached instead of deriving exhaustion from used and limit', async () => {
  const reached = await loadServiceSettings(
    backendFor(() => ({
      status: 200,
      body: JSON.stringify({
        identity: {displayName: 'Local identity', email: ''},
        entitlement: {
          planLabel: 'Omi Plus',
          limitKey: 'chat',
          used: 1,
          limit: 100,
          limitReached: true,
        },
      }),
    })),
  );
  expect(reached.entitlement).toEqual({
    planLabel: 'Omi Plus',
    limitKey: 'chat',
    used: 1,
    limit: 100,
    limitReached: true,
  });
  const exhaustedWithoutFlag = await loadServiceSettings(
    backendFor(() => ({
      status: 200,
      body: JSON.stringify({
        identity: {displayName: 'Local identity', email: ''},
        entitlement: {
          planLabel: 'Omi Plus',
          limitKey: 'chat',
          used: 100,
          limit: 100,
        },
      }),
    })),
  );
  expect(exhaustedWithoutFlag.entitlement?.limitReached).toBe(false);
  await expect(
    loadServiceSettings(
      backendFor(() => ({
        status: 200,
        body: JSON.stringify({
          identity: {displayName: 'Local identity', email: ''},
          entitlement: {
            limitKey: 'chat',
            used: 1,
            limit: 100,
            limitReached: 'true',
          },
        }),
      })),
    ),
  ).rejects.toThrow('Usage allowance response is malformed');
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

test('successful Apps enabled reads do not treat catalogue enabled bits as installed', async () => {
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
      return {status: 200, body: JSON.stringify([])};
    }
    if (request.path === '/v1/users/profile') {
      return {status: 200, body: JSON.stringify({uid: 'user-1'})};
    }
    return {status: 404, body: null};
  });
  const snapshot = await loadConnectors(backend);
  expect(snapshot.enabledIds).toEqual([]);
  expect(snapshot.enabledError).toBeNull();
  expect(installedApps(snapshot)).toEqual([]);
  expect(exploreApps(snapshot).map(app => app.enabled)).toEqual([false]);
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

test('loadAccountSettings names GET usage today without inventing zeros', async () => {
  const backend = backendFor(request => {
    if (request.path === '/v1/users/me/usage?period=today') {
      return {
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
    if (request.path === '/v1/users/profile') {
      return {status: 200, body: JSON.stringify({uid: 'user-1'})};
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
  expect(snapshot.usage).toEqual({
    transcriptionSeconds: 90,
    wordsTranscribed: 12,
    insightsGained: 3,
    memoriesCreated: 1,
  });
  expect(snapshot.usageError).toBeNull();
  expect(parseCloudUsage({today: null}, 'Usage')).toBeNull();
  expect(parseCloudUsage({}, 'Usage')).toBeNull();
  expect(
    parseCloudUsage(
      {today: {transcription_seconds: '90'}},
      'Usage',
    ),
  ).toEqual({
    transcriptionSeconds: 90,
    wordsTranscribed: 0,
    insightsGained: 0,
    memoriesCreated: 0,
  });
  expect(() =>
    parseCloudUsage(
      {today: {transcription_seconds: '90.5'}},
      'Usage',
    ),
  ).toThrow('Usage transcription_seconds is malformed');
});

test('loadAccountSettings names GET primary language without inventing Not set', async () => {
  const backend = backendFor(request => {
    if (request.path === '/v1/users/language') {
      return {status: 200, body: JSON.stringify({language: 'en'})};
    }
    if (request.path === '/v1/users/available-languages') {
      return {
        status: 200,
        body: JSON.stringify({
          languages: [
            {code: 'en', name: 'English'},
            {code: 'es', name: 'Spanish'},
          ],
        }),
      };
    }
    if (request.path === '/v1/users/profile') {
      return {status: 200, body: JSON.stringify({uid: 'user-1'})};
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
    if (request.path === '/v1/users/me/usage?period=today') {
      return {status: 200, body: JSON.stringify({})};
    }
    return {status: 404, body: null};
  });
  const snapshot = await loadAccountSettings(backend);
  expect(snapshot.language).toBe('en');
  expect(snapshot.languageNames).toEqual([
    {code: 'en', name: 'English'},
    {code: 'es', name: 'Spanish'},
  ]);
  expect(parseCloudLanguage({language: null}, 'Language')).toBeNull();
  expect(parseCloudLanguage({language: ''}, 'Language')).toBeNull();
  expect(parseCloudLanguageNames({languages: []}, 'Languages')).toBeNull();
  expect(() => parseCloudLanguage({language: 1}, 'Language')).toThrow(
    'Language language is malformed',
  );
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
