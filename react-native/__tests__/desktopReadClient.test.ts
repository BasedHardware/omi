import {readFileSync} from 'node:fs';
import {resolve} from 'node:path';
import {
  conversationDisplaySummary,
  conversationDetailSummaryCopy,
  conversationNoSummaryCopy,
  conversationNoSummaryForAppCopy,
  processingConversationNoContentCopy,
  processingConversationNoSummaryCopy,
  processingConversationStatusCopy,
  conversationDetailSummaryForStatusCopy,
  conversationsEmptyCopy,
  conversationsEmptyHeadingCopy,
  conversationsStarredEmptyCopy,
  memoriesEmptyCopy,
  memoriesSearchEmptyCopy,
  memoriesLoadErrorCopy,
  tasksEmptyCopy,
  tasksSearchEmptyCopy,
  compactHomeTodayTasksTitleCopy,
  compactHomeTodayTasksHidesEmpty,
  compactHomeConversationsEmptyCopy,
  compactHomeConversationsHidesEmpty,
  appsEmptyCopy,
  appsCreatedByMeCopy,
  conversationDisplayTitle,
  processingConversationDetailTitleCopy,
  processingConversationDetailContentTabCopy,
  conversationListUsesListenOverview,
  conversationRecapTitle,
  conversationDiscardedTranscriptCopy,
  conversationDetailSpeakerCopy,
  conversationDayLabel,
  conversationRecapDateLabel,
  conversationListDurationCopy,
  conversationTranscriptDurationCopy,
  conversationDetailDurationCopy,
  conversationListNewCopy,
  conversationListGroupCopy,
  conversationListTimeCopy,
  conversationDetailDateChipCopy,
  conversationGroupLabel,
  conversationCaptureCopy,
  conversationPhotoCountCopy,
  conversationPhotoChrome,
  conversationPhotoAnalyzingCopy,
  conversationPhotoDiscardedCopy,
  conversationDiscardedPhotoCopy,
  conversationStatusCopy,
  conversationListStatusCopy,
  dataProtectionCopy,
  developerWebhookDescriptionCopy,
  developerWebhookRowCopy,
  developerWebhookStatusCopy,
  developerWebhookTypeCopy,
  developerKeyCreatedCopy,
  developerKeyPrefixCopy,
  developerKeyRowCopy,
  developerKeyScopeCopy,
  developerKeysCopy,
  developerKeysEmptyCopy,
  developerApiTitleCopy,
  mcpTitleCopy,
  webhooksTitleCopy,
  userIdTitleCopy,
  userIdChipCopy,
  signOutTitleCopy,
  privacyPolicyTitleCopy,
  termsOfServiceTitleCopy,
  permissionsTitleCopy,
  appCategoryCopy,
  appSectionCategoryCopy,
  appDisplaySource,
  appDisplayAttribution,
  appDisplayName,
  appExploreRatingCopy,
  appListDescriptionCopy,
  appListPrivateNameCopy,
  appRatingCopy,
  appImageUrl,
  deviceDisplayName,
  accountFieldCopy,
  connectionIdentityCopy,
  chatHumanQuotedContextCopy,
  chatMessageDisplayText,
  chatMessageShowsBodySlot,
  chatChartCopy,
  paintedChatContentBlock,
  chatBlockUnavailableCopy,
  chatBlockLoadingCopy,
  chatDiscoveryShowMoreCopy,
  chatDiscoveryShowLessCopy,
  taskCardDescription,
  chatAttachmentCopy,
  chatAttachmentDisplayName,
  chatAttachmentThumbnailUrl,
  chatSenderCopy,
  chatDaySummaryCopy,
  chatDaySummaryDateCopy,
  chatDaySummaryItems,
  chatDaySummaryRowCopy,
  chatAppAttributionCopy,
  chatMemoryCitationCopy,
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
  memoryHistoryCopy,
  memoryHistoryPartialCopy,
  memoryCaptureDeviceCopy,
  conversationListCategory,
  conversationListEmoji,
  conversationListSourceTag,
  conversationListTag,
  conversationVisibilityCopy,
  conversationCalendarAttendeesChipCopy,
  calendarEventDisplayTitle,
  conversationUnknownAppCopy,
  conversationUnknownLocationCopy,
  conversationLocationAddressCopy,
  conversationNoFolderCopy,
  transcriptSttProviderCopy,
  transcriptSttUnknownCopy,
  transcriptSttOmiFallbackCopy,
  conversationStructuredEmojiCopy,
  conversationStructuredEmojiDefaultCopy,
  conversationStructuredCategoryCopy,
  conversationStructuredCategoryDefaultCopy,
  conversationFirstPartySummaryCopy,
  conversationActionItemsTodoCopy,
  conversationActionItemsNoPendingCopy,
  conversationActionItemsCompletedCopy,
  conversationActionItemsNoCompletedCopy,
  conversationActionItemsEmptyCopy,
  conversationActionItemsEmptyDescriptionCopy,
  parseMemoryText,
  chatClockLabel,
  clockLabel,
  projectionClockLabel,
  projectionTimestamp,
  subscriptionPlanCopy,
  subscriptionStatusCopy,
  subscriptionTranscriptionQuotaCopy,
  usageStatsCopy,
  usagePeriodStatsCopy,
  usageThisMonthTitleCopy,
  usageThisYearTitleCopy,
  usageAllTimeTitleCopy,
  usageLoadErrorCopy,
  subscriptionLoadErrorCopy,
  taskIntegrationsTitleCopy,
  taskIntegrationsFooterCopy,
  integrationsTitleCopy,
  integrationsFooterCopy,
  usageActivityEmptyCopy,
  usageListeningSubtitleCopy,
  usageUnderstandingSubtitleCopy,
  usageProvidingSubtitleCopy,
  usageRememberingSubtitleCopy,
  primaryLanguageCopy,
  primaryLanguageNotSetCopy,
  peopleNameRows,
  peopleTitleCopy,
  peopleEmptyCopy,
  peopleSettingsCopy,
  firmwareUpdateCopy,
  firmwareDeviceUpToDateCopy,
  firmwareLatestVersionCopy,
  firmwareWhatsNewCopy,
  deviceModelNumberCopy,
  deviceProductNameCopy,
  deviceSerialNumberCopy,
  deviceUnknownCopy,
  deviceInformationCopy,
  deviceIdentityChipCopy,
  deviceFoundShortIdCopy,
  deviceFoundNameCopy,
  deviceFoundSavedCopy,
  deviceFoundSavedChipCopy,
  deviceFoundConnectedBatteryCopy,
  ledBrightnessCopy,
  micGainCopy,
  micGainLevelCopy,
  findDeviceCopy,
  deviceStorageTitleCopy,
  deviceStoragePercentFullCopy,
  deviceStorageFormatBytesCopy,
  deviceStorageCardCopy,
  chargingCopy,
  batteryLevelCopy,
  deviceBatteryPercentCopy,
  deviceDisconnectedCopy,
  compactHomeDeviceLabelCopy,
  fairUseCopy,
  fairUseBudgetResetCopy,
  fairUseSpeechUsageCopy,
  fairUseDailyTranscriptionCopy,
  fairUseAboutTitleCopy,
  fairUseAboutBodyCopy,
  fairUseLoadErrorCopy,
  dailySummaryDateCopy,
  dailySummaryCopy,
  dailySummaryDefaultHeadlineCopy,
  dailySummaryDurationCopy,
  dailySummaryHourCopy,
  dailySummaryScheduleCopy,
  dailySummaryScheduleTitleCopy,
  dailySummaryDescriptionCopy,
  deliveryTimeTitleCopy,
  mentorNotificationFrequencyCopy,
  notificationFrequencyTitleCopy,
  notificationFrequencyDescriptionCopy,
  automaticTranslationCopy,
  automaticTranslationTitleCopy,
  detectLanguagesCopy,
  customVocabularyCopy,
  customVocabularyTitleCopy,
  primaryLanguageTitleCopy,
  subscriptionPeriodCopy,
  chatQuotaSubtitleCopy,
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
          summary: '',
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
          searchableText: '\n',
        }),
      ],
    }),
  );
});

test('conversation display title names Flutter empty GET titles', () => {
  expect(processingConversationDetailTitleCopy()).toBe('In progress');
  expect(processingConversationDetailContentTabCopy('omi')).toBe('Content');
  expect(processingConversationDetailContentTabCopy('openglass')).toBe('Photos');
  expect(processingConversationDetailContentTabCopy('screenpipe')).toBe(
    'Raw Data',
  );
  expect(processingConversationDetailContentTabCopy('')).toBe('Content');
  expect(processingConversationDetailContentTabCopy('  ')).toBe('Content');
  expect(conversationDisplayTitle({title: '', status: 'processing'})).toBe(
    '',
  );
  expect(conversationDisplayTitle({title: '', status: 'completed'})).toBe('');
  expect(conversationDisplayTitle({title: ' \t\n', status: 'processing'})).toBe(
    ' \t\n',
  );
  expect(conversationDisplayTitle({title: ' \t\n', status: 'completed'})).toBe(
    ' \t\n',
  );
  expect(conversationDisplayTitle({title: '\u0085', status: 'completed'})).toBe(
    '\u0085',
  );
  expect(
    conversationDisplayTitle({title: 'Morning walk', status: 'processing'}),
  ).toBe('Morning walk');
  expect(
    conversationDisplayTitle({title: '  Morning walk  ', status: 'completed'}),
  ).toBe('  Morning walk  ');
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
      title: '  Morning walk  ',
      summary: 'Discussed the launch.',
      status: 'completed',
    }),
  ).toBe('  Morning walk  ');
  expect(
    conversationRecapTitle({
      title: '',
      summary: '',
      status: 'processing',
    }),
  ).toBe('');
  expect(
    conversationRecapTitle({
      title: '',
      summary: '',
      status: 'completed',
    }),
  ).toBe('');
  expect(
    conversationRecapTitle({
      title: '',
      summary: 'Actual overview',
      status: 'completed',
      discarded: true,
    }),
  ).toBe('');
  expect(
    conversationRecapTitle({
      title: '',
      summary: '\u0085',
      status: 'completed',
    }),
  ).toBe('');
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

test('conversation list duration prefers GET transcript span over wall clocks', () => {
  expect(
    conversationListDurationCopy({
      startedAt: '2026-09-07T00:00:00.000Z',
      finishedAt: '2026-09-07T00:10:00.000Z',
      transcriptEndSeconds: 120,
    }),
  ).toBe('2m');
  expect(
    conversationListDurationCopy({
      startedAt: '2026-09-07T00:00:00.000Z',
      finishedAt: '2026-09-07T00:10:00.000Z',
    }),
  ).toBe('10m');
  expect(
    conversationListDurationCopy({
      startedAt: '2026-09-07T12:00:00.000Z',
      finishedAt: '2026-09-07T12:00:20.000Z',
    }),
  ).toBe('20s');
  expect(
    conversationListDurationCopy({
      startedAt: '2026-09-07T00:00:00.000Z',
      finishedAt: '2026-09-07T00:10:00.000Z',
      transcriptEndSeconds: 90,
    }),
  ).toBe('1m 30s');
  expect(
    conversationListDurationCopy({
      startedAt: '2026-09-07T00:00:00.000Z',
      finishedAt: '2026-09-07T00:10:00.000Z',
      transcriptEndSeconds: 3660,
    }),
  ).toBe('1h 1m');
  expect(
    conversationListDurationCopy({
      startedAt: '2026-09-07T12:00:00.000Z',
      finishedAt: '2026-09-07T12:00:00.000Z',
    }),
  ).toBe('');
  expect(
    conversationListDurationCopy({
      startedAt: '2026-09-07T12:00:00.000Z',
      finishedAt: '2026-09-07T12:00:00.400Z',
    }),
  ).toBe('');
  expect(
    conversationListDurationCopy({
      startedAt: new Date(0).toISOString(),
      finishedAt: '2026-09-07T12:00:00.000Z',
    }),
  ).toBe('Duration unavailable');
});

test('conversation transcript duration names Flutter secondsToHumanReadable singular second', () => {
  expect(conversationTranscriptDurationCopy([{end: 1}])).toBe('1 sec');
  expect(conversationTranscriptDurationCopy([{end: 20}])).toBe('20 secs');
  expect(conversationTranscriptDurationCopy([{end: 59}])).toBe('59 secs');
  expect(conversationTranscriptDurationCopy([{end: 60}])).toBe('1 min');
  expect(conversationTranscriptDurationCopy([{end: 61}])).toBe('1 mins 1 secs');
  expect(conversationTranscriptDurationCopy([{end: 150}])).toBe(
    '2 mins 30 secs',
  );
  expect(conversationTranscriptDurationCopy([{end: 0}])).toBeNull();
  expect(conversationTranscriptDurationCopy([])).toBeNull();
});

test('conversation detail duration names Flutter GetSummaryWidgets transcript span only', () => {
  expect(
    conversationDetailDurationCopy({
      transcriptEndSeconds: 20,
    }),
  ).toBe('20 secs');
  expect(
    conversationDetailDurationCopy({
      transcriptEndSeconds: 150,
    }),
  ).toBe('2 mins 30 secs');
  expect(conversationDetailDurationCopy({})).toBeNull();
  expect(
    conversationDetailDurationCopy({
      transcriptEndSeconds: 0,
    }),
  ).toBeNull();
});

test('discarded conversation titles use Flutter transcript excerpt and people names', () => {
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
    conversationDetailSpeakerCopy(
      {speaker: 'SPEAKER_05', isUser: false},
      [
        {speaker: 'SPEAKER_05', isUser: false},
        {speaker: 'SPEAKER_06', isUser: false},
        {speaker: 'SPEAKER_00', isUser: true},
      ],
    ),
  ).toBe('Speaker 1');
  expect(
    conversationDetailSpeakerCopy(
      {speaker: 'SPEAKER_06', isUser: false},
      [
        {speaker: 'SPEAKER_05', isUser: false},
        {speaker: 'SPEAKER_06', isUser: false},
        {speaker: 'SPEAKER_00', isUser: true},
      ],
    ),
  ).toBe('Speaker 2');
  expect(
    conversationDetailSpeakerCopy(
      {speaker: 'SPEAKER_00', isUser: true},
      [{speaker: 'SPEAKER_00', isUser: true}],
    ),
  ).toBe('You');
  expect(
    conversationDetailSpeakerCopy(
      {speaker: 'SPEAKER_01', isUser: false},
      [{speaker: 'SPEAKER_01', isUser: false}],
    ),
  ).toBe('Speaker 1');
  expect(
    conversationDetailSpeakerCopy(
      {speaker: 'SPEAKER_00', isUser: false, personName: 'Alex Chen'},
      [{speaker: 'SPEAKER_00', isUser: false}],
    ),
  ).toBe('Alex Chen');
  expect(
    conversationDetailSpeakerCopy(
      {speaker: 'SPEAKER_00', isUser: false, personName: ''},
      [{speaker: 'SPEAKER_00', isUser: false}],
    ),
  ).toBe('');
  expect(
    conversationDetailSpeakerCopy(
      {speaker: 'SPEAKER_00', isUser: false, personName: ' \t\n'},
      [{speaker: 'SPEAKER_00', isUser: false}],
    ),
  ).toBe(' \t\n');
  expect(
    conversationDetailSpeakerCopy(
      {speaker: 'SPEAKER_99', isUser: false},
      [{speaker: 'SPEAKER_99', isUser: false}],
    ),
  ).toBe('omi');
  expect(
    conversationDetailSpeakerCopy(
      {speaker: 'SPEAKER_99', isUser: false, personName: 'Alex Chen'},
      [{speaker: 'SPEAKER_99', isUser: false}],
    ),
  ).toBe('omi');
  expect(
    conversationDetailSpeakerCopy(
      {speaker: 'SPEAKER_100', isUser: false},
      [
        {speaker: 'SPEAKER_99', isUser: false},
        {speaker: 'SPEAKER_100', isUser: false},
      ],
    ),
  ).toBe('Speaker 2');
  expect(
    conversationDetailSpeakerCopy(
      {speaker: 'SPEAKER_00', isUser: false},
      [
        {speaker: 'SPEAKER_00', isUser: false},
        {speaker: 'SPEAKER_99', isUser: false},
      ],
    ),
  ).toBe('Speaker 1');
  expect(
    conversationDetailSpeakerCopy(
      {speaker: '', isUser: false},
      [{speaker: '', isUser: false}],
    ),
  ).toBe('Speaker 1');
  expect(
    conversationDetailSpeakerCopy(
      {speaker: ' \t\n', isUser: false},
      [{speaker: ' \t\n', isUser: false}],
    ),
  ).toBe('Speaker 1');
  expect(
    conversationDetailSpeakerCopy(
      {speaker: '\u0085', isUser: false},
      [{speaker: '\u0085', isUser: false}],
    ),
  ).toBe('Speaker 1');
  expect(
    conversationDiscardedTranscriptCopy([
      {text: 'Hi', speaker: 'SPEAKER_99', isUser: false},
    ]),
  ).toBe('Speaker 1: Hi');
  expect(
    conversationDiscardedTranscriptCopy([
      {
        text: 'Named',
        speaker: 'SPEAKER_00',
        isUser: false,
        start: 0,
        end: 1,
        personId: 'person-alex',
      },
    ]),
  ).toBe('[00:00:00 - 00:00:01] Speaker 1: Named');
  expect(
    conversationDiscardedTranscriptCopy(
      [
        {
          text: 'Named',
          speaker: 'SPEAKER_00',
          isUser: false,
          start: 0,
          end: 1,
          personId: 'person-alex',
        },
      ],
      new Map([['person-alex', 'Alex Chen']]),
    ),
  ).toBe('[00:00:00 - 00:00:01] Alex Chen: Named');
  expect(
    conversationDiscardedTranscriptCopy(
      [
        {
          text: 'Named',
          speaker: 'SPEAKER_00',
          isUser: false,
          start: 0,
          end: 1,
          personId: 'person-alex',
        },
      ],
      new Map([['person-alex', '']]),
    ),
  ).toBe('[00:00:00 - 00:00:01] : Named');
  expect(
    conversationDiscardedTranscriptCopy(
      [
        {
          text: 'Named',
          speaker: 'SPEAKER_00',
          isUser: false,
          start: 0,
          end: 1,
          personId: 'person-alex',
        },
      ],
      new Map([['person-alex', ' \t\n']]),
    ),
  ).toBe('[00:00:00 - 00:00:01] : Named');
  expect(
    conversationDiscardedTranscriptCopy(
      [
        {
          text: 'Mine',
          speaker: 'SPEAKER_00',
          isUser: true,
          start: 0,
          end: 1,
          personId: 'person-alex',
        },
      ],
      new Map([['person-alex', 'Alex Chen']]),
    ),
  ).toBe('[00:00:00 - 00:00:01] User: Mine');
  expect(
    conversationDiscardedTranscriptCopy([
      {text: 'a'.repeat(90), isUser: true, start: 0, end: 2},
    ]),
  ).toBe(`[00:00:00 - 00:00:02] User: ${'a'.repeat(90)}`.slice(-100));
  expect(conversationDiscardedTranscriptCopy([])).toBe('');
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

test('conversation list status copy names Flutter MergingIndicator without Failed or Processing chips', () => {
  expect(conversationListStatusCopy('failed')).toBeNull();
  expect(conversationListStatusCopy('processing')).toBeNull();
  expect(conversationListStatusCopy('merging')).toBe('Merging...');
  expect(conversationListStatusCopy('in_progress')).toBeNull();
  expect(conversationListStatusCopy('completed')).toBeNull();
  expect(conversationListStatusCopy('queued')).toBeNull();
  expect(conversationListStatusCopy('')).toBeNull();
  expect(conversationListStatusCopy(' \t\n')).toBeNull();
});

test('account subscription copy is not a raw wire token', () => {
  expect(subscriptionPlanCopy('plus')).toBe('Plus');
  expect(subscriptionPlanCopy('basic')).toBe('Free Plan');
  expect(subscriptionPlanCopy('unlimited')).toBe('Unlimited Plan');
  expect(subscriptionPlanCopy('unlimited_v2')).toBe('Unlimited Plan');
  expect(subscriptionPlanCopy('architect')).toBe('Unlimited Plan');
  expect(subscriptionPlanCopy('operator')).toBe('Unlimited Plan');
  expect(subscriptionPlanCopy('pro')).toBe('Unlimited Plan');
  expect(subscriptionPlanCopy('enterprise')).toBe('Free Plan');
  expect(subscriptionStatusCopy('active')).toBe('Active');
  expect(subscriptionStatusCopy('past_due')).toBe('Past due');
  expect(subscriptionPlanCopy('')).toBe('Free Plan');
  expect(subscriptionStatusCopy('')).toBe('Plan unavailable');
  expect(subscriptionPlanCopy('\u0085')).toBe('Free Plan');
  expect(subscriptionTranscriptionQuotaCopy(90, 3600)).toBe(
    '2 of 60 min used this month',
  );
  expect(subscriptionTranscriptionQuotaCopy(0, 1800)).toBe(
    '0 of 30 min used this month',
  );
  expect(subscriptionTranscriptionQuotaCopy(90, 0)).toBeNull();
  expect(subscriptionTranscriptionQuotaCopy(null, 3600)).toBeNull();
  expect(subscriptionTranscriptionQuotaCopy(90, null)).toBeNull();
  expect(dataProtectionCopy('standard')).toBe('Standard');
  expect(dataProtectionCopy('')).toBe('Data protection unavailable');
  expect(dataProtectionCopy('\u0085')).toBe('Data protection unavailable');
});

test('subscription quota copy names Flutter UsagePage en_US grouping', () => {
  expect(subscriptionTranscriptionQuotaCopy(74040, 360000)).toBe(
    '1,234 of 6000 min used this month',
  );
  expect(
    subscriptionPeriodCopy({
      wordsTranscribedUsed: 12,
      wordsTranscribedLimit: 10000,
      insightsGainedUsed: 1234,
      insightsGainedLimit: 5000,
      chatQuotaUsed: 1234,
      chatQuotaUnit: 'messages',
      chatQuestionsPerMonth: 10000,
      chatCostUsdPerMonth: null,
    }),
  ).toEqual([
    {
      title: 'Words this month',
      copy: '12 of 10,000 words used this month',
    },
    {
      title: 'Insights this month',
      copy: '1,234 of 5,000 insights gained this month',
    },
    {
      title: 'Chat this month',
      copy: `1,234 Chat\n${chatQuotaSubtitleCopy()}\n1,234 of 10000 messages used this month`,
    },
  ]);
});

test('usage stats copy names GET today counts without Upgrade', () => {
  expect(usageListeningSubtitleCopy()).toBe(
    'Total time Omi has actively listened.',
  );
  expect(usageUnderstandingSubtitleCopy()).toBe(
    'Words understood from your conversations.',
  );
  expect(usageProvidingSubtitleCopy()).toBe(
    'Action items, and notes automatically captured.',
  );
  expect(usageRememberingSubtitleCopy()).toBe(
    'Facts and details remembered for you.',
  );
  expect(
    usageStatsCopy({
      transcriptionSeconds: 90,
      wordsTranscribed: 12,
      insightsGained: 3,
      memoriesCreated: 1,
    }),
  ).toEqual([
    {
      title: 'Listening',
      copy: `2 minutes\n${usageListeningSubtitleCopy()}`,
    },
    {
      title: 'Understanding',
      copy: `12 Understanding (words)\n${usageUnderstandingSubtitleCopy()}`,
    },
    {
      title: 'Providing',
      copy: `3 Insights\n${usageProvidingSubtitleCopy()}`,
    },
    {
      title: 'Remembering',
      copy: `1 Memories\n${usageRememberingSubtitleCopy()}`,
    },
  ]);
  expect(
    usageStatsCopy({
      transcriptionSeconds: 90,
      wordsTranscribed: 1234,
      insightsGained: 3000,
      memoriesCreated: 1000,
    }),
  ).toEqual([
    {
      title: 'Listening',
      copy: `2 minutes\n${usageListeningSubtitleCopy()}`,
    },
    {
      title: 'Understanding',
      copy: `1,234 Understanding (words)\n${usageUnderstandingSubtitleCopy()}`,
    },
    {
      title: 'Providing',
      copy: `3,000 Insights\n${usageProvidingSubtitleCopy()}`,
    },
    {
      title: 'Remembering',
      copy: `1,000 Memories\n${usageRememberingSubtitleCopy()}`,
    },
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
  expect(usageActivityEmptyCopy()).toBe(
    'No Activity Yet\nStart a conversation with Omi\nto see your usage insights here.',
  );
  expect(usageThisMonthTitleCopy()).toBe('This Month');
  expect(usageThisYearTitleCopy()).toBe('This Year');
  expect(usageAllTimeTitleCopy()).toBe('All Time');
  expect(usageLoadErrorCopy()).toBe(
    'Failed to load usage data. Please try again later.',
  );
  expect(subscriptionLoadErrorCopy()).toBe(
    'Failed to load subscription data. Please try again later.',
  );
  expect(taskIntegrationsTitleCopy()).toBe('Task Integrations');
  expect(taskIntegrationsFooterCopy()).toBe(
    'Tasks can be exported to one app at a time.',
  );
  expect(integrationsTitleCopy()).toBe('Integrations');
  expect(integrationsFooterCopy()).toBe(
    'Connect your apps to view data and metrics in chat.',
  );
  expect(
    usagePeriodStatsCopy(usageThisYearTitleCopy(), {
      transcriptionSeconds: 0,
      wordsTranscribed: 0,
      insightsGained: 0,
      memoriesCreated: 0,
    }),
  ).toEqual([{title: usageThisYearTitleCopy(), copy: usageActivityEmptyCopy()}]);
  expect(
    usagePeriodStatsCopy('Today', {
      transcriptionSeconds: 0,
      wordsTranscribed: 0,
      insightsGained: 0,
      memoriesCreated: 0,
    }),
  ).toEqual([{title: 'Today', copy: usageActivityEmptyCopy()}]);
  expect(usagePeriodStatsCopy(usageThisYearTitleCopy(), null)).toBeNull();
});

test('primary language copy names Flutter notSet for empty or catalog-miss GET language', () => {
  expect(primaryLanguageNotSetCopy()).toBe('Not set');
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
  expect(
    primaryLanguageCopy('xx', [
      {code: 'en', name: 'English'},
      {code: 'es', name: 'Spanish'},
    ]),
  ).toBe(primaryLanguageNotSetCopy());
  expect(
    primaryLanguageCopy('fr', [
      {code: 'fr', name: ''},
      {code: 'en', name: 'English'},
    ]),
  ).toBe('');
  expect(
    primaryLanguageCopy('fr', [
      {code: 'fr', name: ' \t'},
      {code: 'en', name: 'English'},
    ]),
  ).toBe(' \t');
  expect(
    primaryLanguageCopy('fr', [
      {code: 'fr', name: '\u0085'},
      {code: 'en', name: 'English'},
    ]),
  ).toBe('\u0085');
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

test('people settings copy names Flutter createPersonHint for empty GET people', () => {
  expect(peopleTitleCopy()).toBe('People');
  expect(peopleEmptyCopy()).toBe(
    'Create a new person and train Omi to recognize their speech too!',
  );
  expect(peopleSettingsCopy(null)).toEqual([]);
  expect(peopleSettingsCopy(new Map())).toEqual([
    {key: 'empty', title: peopleTitleCopy(), copy: peopleEmptyCopy()},
  ]);
  expect(
    peopleSettingsCopy(
      new Map([
        ['person-alex', 'Alex Chen'],
        ['person-sam', 'Sam'],
      ]),
    ),
  ).toEqual([
    {key: 'person-alex', title: peopleTitleCopy(), copy: 'Alex Chen'},
    {key: 'person-sam', title: peopleTitleCopy(), copy: 'Sam'},
  ]);
  expect(peopleSettingsCopy(new Map([['person-empty', '']]))).toEqual([
    {key: 'person-empty', title: peopleTitleCopy(), copy: ''},
  ]);
  expect(peopleSettingsCopy(new Map([['person-empty', ' \t']]))).toEqual([
    {key: 'person-empty', title: peopleTitleCopy(), copy: ' \t'},
  ]);
});

test('fair use copy names GET stage hours and restrict budget without Upgrade', () => {
  expect(fairUseSpeechUsageCopy()).toBe('Speech Usage');
  expect(fairUseDailyTranscriptionCopy()).toBe('Daily Transcription');
  expect(fairUseAboutTitleCopy()).toBe('About Fair Use');
  expect(fairUseLoadErrorCopy()).toBe(
    'Unable to load fair use status. Please try again.',
  );
  expect(fairUseAboutBodyCopy()).toBe(
    'Omi is designed for personal conversations, meetings, and live interactions. Usage is measured by real speech time detected, not connection time. If usage significantly exceeds normal patterns for non-personal content, adjustments may apply.',
  );
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
    {title: 'Speech Usage', copy: ''},
    {title: 'Today', copy: '2.4h / 2h'},
    {title: '3-Day Rolling', copy: '8.1h / 8h'},
    {title: 'Weekly Rolling', copy: '11.0h / 10h'},
    {title: 'Fair Use', copy: 'Usage is restricted.'},
    {title: fairUseDailyTranscriptionCopy(), copy: '30m / 30m'},
    {
      title: fairUseDailyTranscriptionCopy(),
      copy: 'Daily transcription limit reached',
    },
    {title: fairUseDailyTranscriptionCopy(), copy: 'Resets 5h'},
    {
      title: fairUseAboutTitleCopy(),
      copy: fairUseAboutBodyCopy(),
    },
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
    {title: 'Speech Usage', copy: ''},
    {title: 'Today', copy: '2.4h / 2h'},
    {title: '3-Day Rolling', copy: '8.1h / 8h'},
    {title: 'Weekly Rolling', copy: '11.0h / 10h'},
    {title: 'Fair Use', copy: 'Usage is restricted.'},
    {title: fairUseDailyTranscriptionCopy(), copy: '30m / 30m'},
    {
      title: fairUseDailyTranscriptionCopy(),
      copy: 'Daily transcription limit reached',
    },
    {
      title: fairUseAboutTitleCopy(),
      copy: fairUseAboutBodyCopy(),
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
    {title: 'Speech Usage', copy: ''},
    {title: 'Today', copy: '0.0h / 2h'},
    {title: '3-Day Rolling', copy: '0.0h / 8h'},
    {title: 'Weekly Rolling', copy: '0.0h / 10h'},
    {title: 'Fair Use', copy: ''},
    {
      title: fairUseAboutTitleCopy(),
      copy: fairUseAboutBodyCopy(),
    },
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

test('names Flutter FairUsePage whitespace GET message instead of omitting the banner', () => {
  const idle = {
    stage: 'none',
    caseRef: '',
    speechHoursToday: 0,
    speechHours3day: 0,
    speechHoursWeekly: 0,
    dailyHours: 2,
    threeDayHours: 8,
    weeklyHours: 10,
    dailyLimitMs: 1_800_000,
    usedMs: 0,
    exhausted: false,
  };
  expect(fairUseCopy({...idle, message: ' \t'})).toEqual([
    {title: 'Speech Usage', copy: ''},
    {title: 'Today', copy: '0.0h / 2h'},
    {title: '3-Day Rolling', copy: '0.0h / 8h'},
    {title: 'Weekly Rolling', copy: '0.0h / 10h'},
    {title: 'Fair Use', copy: ''},
    {
      title: fairUseAboutTitleCopy(),
      copy: fairUseAboutBodyCopy(),
    },
  ]);
  expect(fairUseCopy({...idle, message: '\u0085'})).toEqual([
    {title: 'Speech Usage', copy: ''},
    {title: 'Today', copy: '0.0h / 2h'},
    {title: '3-Day Rolling', copy: '0.0h / 8h'},
    {title: 'Weekly Rolling', copy: '0.0h / 10h'},
    {title: 'Fair Use', copy: ''},
    {
      title: fairUseAboutTitleCopy(),
      copy: fairUseAboutBodyCopy(),
    },
  ]);
  expect(fairUseCopy({...idle, message: ''})).toEqual([
    {title: 'Speech Usage', copy: ''},
    {title: 'Today', copy: '0.0h / 2h'},
    {title: '3-Day Rolling', copy: '0.0h / 8h'},
    {title: 'Weekly Rolling', copy: '0.0h / 10h'},
    {
      title: fairUseAboutTitleCopy(),
      copy: fairUseAboutBodyCopy(),
    },
  ]);
});

test('names Flutter FairUsePage whitespace GET caseRef instead of omitting the slot', () => {
  const restrict = {
    stage: 'restrict',
    message: '',
    speechHoursToday: 0,
    speechHours3day: 0,
    speechHoursWeekly: 0,
    dailyHours: 2,
    threeDayHours: 8,
    weeklyHours: 10,
    dailyLimitMs: 1_800_000,
    usedMs: 0,
    exhausted: false,
  };
  expect(fairUseCopy({...restrict, caseRef: ' \t'})).toEqual([
    {title: 'Fair Use', copy: 'Restricted · '},
    {title: 'Speech Usage', copy: ''},
    {title: 'Today', copy: '0.0h / 2h'},
    {title: '3-Day Rolling', copy: '0.0h / 8h'},
    {title: 'Weekly Rolling', copy: '0.0h / 10h'},
    {title: fairUseDailyTranscriptionCopy(), copy: '0m / 30m'},
    {
      title: fairUseAboutTitleCopy(),
      copy: fairUseAboutBodyCopy(),
    },
  ]);
  expect(fairUseCopy({...restrict, caseRef: '\u0085'})).toEqual([
    {title: 'Fair Use', copy: 'Restricted · '},
    {title: 'Speech Usage', copy: ''},
    {title: 'Today', copy: '0.0h / 2h'},
    {title: '3-Day Rolling', copy: '0.0h / 8h'},
    {title: 'Weekly Rolling', copy: '0.0h / 10h'},
    {title: fairUseDailyTranscriptionCopy(), copy: '0m / 30m'},
    {
      title: fairUseAboutTitleCopy(),
      copy: fairUseAboutBodyCopy(),
    },
  ]);
  expect(fairUseCopy({...restrict, caseRef: ''})).toEqual([
    {title: 'Fair Use', copy: 'Restricted'},
    {title: 'Speech Usage', copy: ''},
    {title: 'Today', copy: '0.0h / 2h'},
    {title: '3-Day Rolling', copy: '0.0h / 8h'},
    {title: 'Weekly Rolling', copy: '0.0h / 10h'},
    {title: fairUseDailyTranscriptionCopy(), copy: '0m / 30m'},
    {
      title: fairUseAboutTitleCopy(),
      copy: fairUseAboutBodyCopy(),
    },
  ]);
});

test('daily summary copy names GET headlines and omits Flutter DailySummaryCard unused stats', () => {
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
          id: 'sum-default',
          date: '',
          headline: dailySummaryDefaultHeadlineCopy(),
        },
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
    {title: 'Daily summary', copy: 'Tue, Sep 8 ·  \t'},
    {
      title: 'Daily summary',
      copy: dailySummaryDefaultHeadlineCopy(),
    },
    {
      title: 'Daily summary',
      copy: 'Today · Shipped the recap',
    },
  ]);
  expect(dailySummaryDurationCopy(45)).toBe('45m');
  expect(dailySummaryDurationCopy(60)).toBe('1h');
  expect(dailySummaryDurationCopy(90)).toBe('1h 30m');
  expect(dailySummaryDurationCopy(0)).toBe('');
});

test('daily summary schedule copy names GET hour without Flutter 10:00 PM default', () => {
  expect(dailySummaryScheduleTitleCopy()).toBe('Daily Summary');
  expect(deliveryTimeTitleCopy()).toBe('Delivery Time');
  expect(dailySummaryDescriptionCopy()).toBe(
    "Get a personalized summary of your day's conversations delivered as a notification.",
  );
  expect(dailySummaryHourCopy(0)).toBe('12:00 AM');
  expect(dailySummaryHourCopy(12)).toBe('12:00 PM');
  expect(dailySummaryHourCopy(22)).toBe('10:00 PM');
  expect(dailySummaryHourCopy(23)).toBe('11:00 PM');
  expect(dailySummaryHourCopy(24)).toBe('12:00 PM');
  expect(dailySummaryHourCopy(-1)).toBe('-1:00 AM');
  expect(dailySummaryScheduleCopy({enabled: true, hour: 22})).toEqual([
    {
      title: dailySummaryScheduleTitleCopy(),
      copy: `Enabled\n${dailySummaryDescriptionCopy()}`,
    },
    {title: deliveryTimeTitleCopy(), copy: '10:00 PM'},
  ]);
  expect(dailySummaryScheduleCopy({enabled: true, hour: 24})).toEqual([
    {
      title: dailySummaryScheduleTitleCopy(),
      copy: `Enabled\n${dailySummaryDescriptionCopy()}`,
    },
    {title: deliveryTimeTitleCopy(), copy: '12:00 PM'},
  ]);
  expect(dailySummaryScheduleCopy({enabled: true, hour: -1})).toEqual([
    {
      title: dailySummaryScheduleTitleCopy(),
      copy: `Enabled\n${dailySummaryDescriptionCopy()}`,
    },
    {title: deliveryTimeTitleCopy(), copy: '-1:00 AM'},
  ]);
  expect(dailySummaryScheduleCopy({enabled: false, hour: 0})).toEqual([
    {
      title: dailySummaryScheduleTitleCopy(),
      copy: `Off\n${dailySummaryDescriptionCopy()}`,
    },
    {title: deliveryTimeTitleCopy(), copy: '12:00 AM'},
  ]);
  expect(dailySummaryScheduleCopy(null)).toEqual([]);
  expect(dailySummaryScheduleCopy(undefined)).toEqual([]);
});

test('mentor notification copy names GET frequency and Flutter descriptions', () => {
  expect(notificationFrequencyTitleCopy()).toBe('Notification Frequency');
  expect(notificationFrequencyDescriptionCopy()).toBe(
    'Control how often Omi sends you proactive notifications and reminders.',
  );
  expect(mentorNotificationFrequencyCopy(0)).toEqual([
    {
      title: notificationFrequencyTitleCopy(),
      copy: `Off · No proactive notifications\n${notificationFrequencyDescriptionCopy()}`,
    },
  ]);
  expect(mentorNotificationFrequencyCopy(1)).toEqual([
    {
      title: notificationFrequencyTitleCopy(),
      copy: `Minimal · Only critical reminders\n${notificationFrequencyDescriptionCopy()}`,
    },
  ]);
  expect(mentorNotificationFrequencyCopy(2)).toEqual([
    {
      title: notificationFrequencyTitleCopy(),
      copy: `Low · Important updates only\n${notificationFrequencyDescriptionCopy()}`,
    },
  ]);
  expect(mentorNotificationFrequencyCopy(3)).toEqual([
    {
      title: notificationFrequencyTitleCopy(),
      copy: `Balanced · Regular helpful nudges\n${notificationFrequencyDescriptionCopy()}`,
    },
  ]);
  expect(mentorNotificationFrequencyCopy(4)).toEqual([
    {
      title: notificationFrequencyTitleCopy(),
      copy: `High · Frequent check-ins\n${notificationFrequencyDescriptionCopy()}`,
    },
  ]);
  expect(mentorNotificationFrequencyCopy(5)).toEqual([
    {
      title: notificationFrequencyTitleCopy(),
      copy: `Maximum · Stay constantly engaged\n${notificationFrequencyDescriptionCopy()}`,
    },
  ]);
  expect(mentorNotificationFrequencyCopy(null)).toEqual([]);
});

test('names GET mentor notification frequency outside 0-5 as Balanced', () => {
  expect(mentorNotificationFrequencyCopy(6)).toEqual([
    {
      title: notificationFrequencyTitleCopy(),
      copy: `Balanced · Regular helpful nudges\n${notificationFrequencyDescriptionCopy()}`,
    },
  ]);
  expect(mentorNotificationFrequencyCopy(-1)).toEqual([
    {
      title: notificationFrequencyTitleCopy(),
      copy: `Balanced · Regular helpful nudges\n${notificationFrequencyDescriptionCopy()}`,
    },
  ]);
});

test('transcription preference copy names GET vocabulary without Flutter false defaults', () => {
  expect(primaryLanguageTitleCopy()).toBe('Primary Language');
  expect(automaticTranslationTitleCopy()).toBe('Automatic Translation');
  expect(detectLanguagesCopy()).toBe('Detect 10+ languages');
  expect(customVocabularyTitleCopy()).toBe('Custom Vocabulary');
  expect(automaticTranslationCopy(true)).toEqual([
    {
      title: automaticTranslationTitleCopy(),
      copy: `Off\n${detectLanguagesCopy()}`,
    },
  ]);
  expect(automaticTranslationCopy(false)).toEqual([
    {
      title: automaticTranslationTitleCopy(),
      copy: `Enabled\n${detectLanguagesCopy()}`,
    },
  ]);
  expect(automaticTranslationCopy(undefined)).toEqual([]);
  expect(automaticTranslationCopy(null)).toEqual([]);
  expect(customVocabularyCopy(['Omi', ' \t', '\u0085', 'Based Hardware'])).toEqual([
    {title: customVocabularyTitleCopy(), copy: 'Omi'},
    {title: customVocabularyTitleCopy(), copy: ' \t'},
    {title: customVocabularyTitleCopy(), copy: '\u0085'},
    {title: customVocabularyTitleCopy(), copy: 'Based Hardware'},
  ]);
  expect(customVocabularyCopy([''])).toEqual([
    {title: customVocabularyTitleCopy(), copy: ''},
  ]);
  expect(customVocabularyCopy([])).toEqual([]);
  expect(customVocabularyCopy(null)).toEqual([]);
});

test('firmware update copy names GET latest without Available on current or draft', () => {
  expect(firmwareLatestVersionCopy()).toBe('Latest Version');
  expect(firmwareWhatsNewCopy()).toBe("What's New");
  expect(firmwareDeviceUpToDateCopy()).toBe('Your device is up to date');
  expect(deviceProductNameCopy()).toBe('Product Name');
  expect(deviceModelNumberCopy()).toBe('Model Number');
  expect(deviceSerialNumberCopy()).toBe('Serial Number');
  expect(deviceUnknownCopy()).toBe('Unknown');
  expect(deviceIdentityChipCopy('omi-test')).toBe('omi-test');
  expect(deviceIdentityChipCopy('123456789012')).toBe('123456789012');
  expect(deviceIdentityChipCopy('1234567890123')).toBe('12345•••0123');
  expect(deviceIdentityChipCopy('AA:BB:CC:DD:EE:FF')).toBe('AA:BB•••E:FF');
  expect(deviceIdentityChipCopy('SERIALNUMBER9911')).toBe('SERIA•••9911');
  expect(deviceIdentityChipCopy('Unknown')).toBe('Unknown');
  expect(deviceFoundShortIdCopy('AA:BB:CC:DD:EE:FF')).toBe('AABBCC');
  expect(deviceFoundShortIdCopy('11:22:33:44:55:66')).toBe('112233');
  expect(deviceFoundShortIdCopy('omi-test')).toBe('omi-te');
  expect(deviceFoundShortIdCopy('abc')).toBe('abc');
  expect(deviceFoundShortIdCopy('123456789012')).toBe('123456');
  expect(deviceFoundShortIdCopy('apple-watch')).toBe('watchOS');
  expect(
    deviceFoundNameCopy('Omi', 'AA:BB:CC:DD:EE:FF', [
      {name: 'Omi'},
      {name: 'Omi'},
    ]),
  ).toBe('Omi (AABBCC)');
  expect(
    deviceFoundNameCopy('Omi', 'AA:BB:CC:DD:EE:FF', [{name: 'Omi'}]),
  ).toBe('Omi');
  expect(
    deviceFoundNameCopy('Pendant', 'omi-unique', [
      {name: 'Omi'},
      {name: 'Pendant'},
    ]),
  ).toBe('Pendant');
  expect(
    deviceFoundNameCopy('', 'AA:BB:CC:DD:EE:FF', [{name: ''}]),
  ).toBe('');
  expect(
    deviceFoundNameCopy(' \t', 'AA:BB:CC:DD:EE:FF', [
      {name: ' \t'},
      {name: ' \t'},
    ]),
  ).toBe(' \t (AABBCC)');
  expect(deviceFoundSavedCopy()).toBe('Saved');
  expect(deviceFoundSavedChipCopy('saved-id', 'saved-id')).toBe('Saved');
  expect(deviceFoundSavedChipCopy('scan-id', 'saved-id')).toBeNull();
  expect(deviceFoundSavedChipCopy('saved-id', null)).toBeNull();
  expect(deviceFoundSavedChipCopy('saved-id', ' \t')).toBeNull();
  expect(deviceFoundConnectedBatteryCopy(87)).toBe('🔋 87%');
  expect(deviceFoundConnectedBatteryCopy(1)).toBe('🔋 1%');
  expect(ledBrightnessCopy()).toBe('LED Brightness');
  expect(micGainCopy()).toBe('Mic Gain');
  expect(micGainLevelCopy(0)).toBe('Mute');
  expect(micGainLevelCopy(1)).toBe('-20dB');
  expect(micGainLevelCopy(2)).toBe('-10dB');
  expect(micGainLevelCopy(3)).toBe('+0dB');
  expect(micGainLevelCopy(4)).toBe('+6dB');
  expect(micGainLevelCopy(5)).toBe('+10dB');
  expect(micGainLevelCopy(6)).toBe('+20dB');
  expect(micGainLevelCopy(7)).toBe('+30dB');
  expect(micGainLevelCopy(8)).toBe('+40dB');
  expect(micGainLevelCopy(-1)).toBe('');
  expect(micGainLevelCopy(9)).toBe('');
  expect(findDeviceCopy()).toBe('Find');
  expect(deviceStorageTitleCopy()).toBe('Device Storage');
  expect(deviceStoragePercentFullCopy(33)).toBe('33% full');
  expect(deviceStorageFormatBytesCopy(0)).toBe('0 B');
  expect(deviceStorageFormatBytesCopy(4096)).toBe('4 KB');
  expect(deviceStorageFormatBytesCopy(8192)).toBe('8 KB');
  expect(deviceStorageFormatBytesCopy(12288)).toBe('12 KB');
  expect(deviceStorageCardCopy({usedBytes: 4096, freeBytes: 8192})).toEqual([
    'Device Storage',
    '33% full',
    '4 KB of 12 KB used  ·  8 KB free',
  ]);
  expect(deviceStorageCardCopy({usedBytes: 95, freeBytes: 5})).toEqual([
    'Device Storage',
    '95% full',
    '95 B of 100 B used  ·  5 B free',
    'Device nearly full — sync to free space.',
  ]);
  expect(chargingCopy()).toBe('Charging');
  expect(batteryLevelCopy()).toBe('Battery Level');
  expect(deviceBatteryPercentCopy(87)).toBe('87%');
  expect(deviceBatteryPercentCopy(87)).not.toContain('battery');
  expect(deviceDisconnectedCopy()).toBe('Disconnected');
  expect(deviceDisconnectedCopy()).not.toContain('Omi');
  expect(
    compactHomeDeviceLabelCopy('Omi not connected', true),
  ).toBe(deviceDisconnectedCopy());
  expect(compactHomeDeviceLabelCopy('Omi not connected', false)).toBe(
    'Omi not connected',
  );
  expect(compactHomeDeviceLabelCopy('Bluetooth off', true)).toBe(
    'Bluetooth off',
  );
  expect(compactHomeDeviceLabelCopy('Connected · Ready', true)).toBe(
    'Connected · Ready',
  );
  expect(
    firmwareUpdateCopy('1.2.3', {
      version: '1.3.0',
      draft: false,
      minVersion: '1.0.0',
    }),
  ).toEqual({latest: '1.3.0', available: true});
  expect(
    firmwareUpdateCopy('1.3.0', {
      version: '1.3.0',
      draft: false,
      minVersion: null,
    }),
  ).toEqual({latest: '1.3.0', available: false, upToDate: true});
  expect(
    firmwareUpdateCopy('1.3.0', {
      version: '1.3.0',
      draft: false,
      minVersion: null,
      changelog: ['Battery improvements'],
    }),
  ).toEqual({
    latest: '1.3.0',
    available: false,
    upToDate: true,
    changelog: ['Battery improvements'],
  });
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
    available: false,
    upToDate: true,
    changelog: ['Fixed BLE reconnect', '  ', 'Battery improvements'],
  });
  expect(
    firmwareUpdateCopy('1.2.3', {
      version: '1.3.0',
      draft: false,
      minVersion: null,
      changelog: [' \t'],
    }),
  ).toEqual({
    latest: '1.3.0',
    available: false,
    upToDate: true,
    changelog: [' \t'],
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

test('firmware update copy names Flutter FirmwareUpdate empty GET min_version as up to date instead of available', () => {
  expect(
    firmwareUpdateCopy('1.2.3', {
      version: '1.3.0',
      draft: false,
      minVersion: null,
    }),
  ).toEqual({latest: '1.3.0', available: false, upToDate: true});
  expect(
    firmwareUpdateCopy('1.2.3', {
      version: '1.3.0',
      draft: false,
      minVersion: '',
    }),
  ).toEqual({latest: '1.3.0', available: false, upToDate: true});
  expect(
    firmwareUpdateCopy('1.2.3', {
      version: '1.3.0',
      draft: false,
      minVersion: ' \t',
    }),
  ).toEqual({latest: '1.3.0', available: false, upToDate: true});
  expect(
    firmwareUpdateCopy('1.2.3', {
      version: '1.3.0',
      draft: false,
      minVersion: 'not-a-version',
    }),
  ).toEqual({latest: '1.3.0', available: false, upToDate: true});
  expect(
    firmwareUpdateCopy('1.2.3', {
      version: '1.3.0',
      draft: false,
      minVersion: '1.0.0',
    }),
  ).toEqual({latest: '1.3.0', available: true});
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
      developerApiTitleCopy(),
    ),
  ).toEqual([
    {title: developerApiTitleCopy(), copy: `Local · omi_sk_ab · ${created}`},
    {title: developerApiTitleCopy(), copy: ` \t \u00b7 omi_sk_cd · ${created}`},
    {title: developerApiTitleCopy(), copy: 'Cursor \u00b7 '},
    {
      title: developerApiTitleCopy(),
      copy: `Scoped · omi_sk_gh · ${created} · Full Access`,
    },
  ]);
  expect(developerKeyRowCopy({name: '', keyPrefix: 'omi_sk_ab'})).toBe(
    ' \u00b7 omi_sk_ab',
  );
  expect(developerKeyRowCopy({name: ' \t', keyPrefix: 'omi_sk_ab'})).toBe(
    ' \t \u00b7 omi_sk_ab',
  );
  expect(developerKeyRowCopy({name: '  Named  ', keyPrefix: 'omi_sk_ab'})).toBe(
    '  Named   \u00b7 omi_sk_ab',
  );
  expect(developerKeyRowCopy({name: '', keyPrefix: ''})).toBe(' \u00b7 ');
  expect(developerKeyRowCopy({name: 'Cursor', keyPrefix: ''})).toBe(
    'Cursor \u00b7 ',
  );
  expect(developerKeyRowCopy({name: 'Cursor', keyPrefix: ' \t'})).toBe(
    'Cursor \u00b7  \t',
  );
  expect(
    developerKeysCopy([{name: 'Cursor', keyPrefix: ''}], mcpTitleCopy()),
  ).toEqual([{title: mcpTitleCopy(), copy: 'Cursor \u00b7 '}]);
  expect(
    developerKeysCopy([{name: '', keyPrefix: 'omi_mcp_cd'}], mcpTitleCopy()),
  ).toEqual([{title: mcpTitleCopy(), copy: ' \u00b7 omi_mcp_cd'}]);
  expect(
    developerKeysCopy([{name: '', keyPrefix: ''}], mcpTitleCopy()),
  ).toEqual([{title: mcpTitleCopy(), copy: ' \u00b7 '}]);
  expect(
    developerKeyRowCopy(
      {name: '', keyPrefix: 'omi_sk_cd'},
      {emptyScopesCopy: 'Read Only', maskPrefix: true},
    ),
  ).toBe(' \u00b7 omi_sk_cd*** \u00b7 Read Only');
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

test('developer key copy names GET empty scopes Read Only without inventing it on MCP keys', () => {
  const createdAtMs = Date.parse('2026-09-09T12:00:00.000Z');
  const created = developerKeyCreatedCopy(createdAtMs);
  expect(
    developerKeysCopy(
      [
        {name: 'Local', keyPrefix: 'omi_sk_ab', createdAtMs, scopes: []},
        {name: 'Omitted', keyPrefix: 'omi_sk_om', createdAtMs},
      ],
      developerApiTitleCopy(),
      {emptyScopesCopy: 'Read Only'},
    ),
  ).toEqual([
    {
      title: developerApiTitleCopy(),
      copy: `Local · omi_sk_ab · ${created} · Read Only`,
    },
    {
      title: developerApiTitleCopy(),
      copy: `Omitted · omi_sk_om · ${created} · Read Only`,
    },
  ]);
  expect(
    developerKeysCopy(
      [{name: 'Cursor', keyPrefix: 'omi_mcp_cd', createdAtMs}],
      mcpTitleCopy(),
    ),
  ).toEqual([{title: mcpTitleCopy(), copy: `Cursor · omi_mcp_cd · ${created}`}]);
  expect(developerKeyScopeCopy([])).toBe('');
  expect(developerKeyScopeCopy(undefined)).toBe('');
  expect(developerKeyScopeCopy([], {emptyCopy: 'Read Only'})).toBe('Read Only');
  expect(developerKeyScopeCopy(undefined, {emptyCopy: 'Read Only'})).toBe(
    'Read Only',
  );
  expect(
    developerKeyScopeCopy(['conversations:write'], {emptyCopy: 'Read Only'}),
  ).toBe('Write');
  expect(developerKeyScopeCopy([''], {emptyCopy: 'Read Only'})).toBe('');
  expect(developerKeyScopeCopy([' \t\n'], {emptyCopy: 'Read Only'})).toBe('');
  expect(
    developerKeysCopy(
      [
        {
          name: 'Local',
          keyPrefix: 'omi_sk_ab',
          createdAtMs,
          scopes: [''],
        },
      ],
      developerApiTitleCopy(),
      {emptyScopesCopy: 'Read Only'},
    ),
  ).toEqual([
    {
      title: developerApiTitleCopy(),
      copy: `Local · omi_sk_ab · ${created}`,
    },
  ]);
});

test('developer key copy names GET prefix Flutter *** mask without inventing it on MCP keys', () => {
  const createdAtMs = Date.parse('2026-09-09T12:00:00.000Z');
  const created = developerKeyCreatedCopy(createdAtMs);
  expect(developerKeyPrefixCopy('omi_sk_ab', {mask: true})).toBe('omi_sk_ab***');
  expect(developerKeyPrefixCopy('omi_sk_ab')).toBe('omi_sk_ab');
  expect(developerKeyPrefixCopy('', {mask: true})).toBe('***');
  expect(developerKeyPrefixCopy('')).toBe('');
  expect(developerKeyPrefixCopy(' \t')).toBe(' \t');
  expect(developerKeyPrefixCopy(' \t', {mask: true})).toBe(' \t***');
  expect(developerKeyPrefixCopy('  pref  ', {mask: true})).toBe('  pref  ***');
  expect(
    developerKeysCopy(
      [
        {name: 'Local', keyPrefix: 'omi_sk_ab', createdAtMs, scopes: []},
        {name: 'Blank', keyPrefix: '', createdAtMs},
      ],
      developerApiTitleCopy(),
      {emptyScopesCopy: 'Read Only', maskPrefix: true},
    ),
  ).toEqual([
    {
      title: developerApiTitleCopy(),
      copy: `Local · omi_sk_ab*** · ${created} · Read Only`,
    },
    {
      title: developerApiTitleCopy(),
      copy: `Blank · *** · ${created} · Read Only`,
    },
  ]);
  expect(
    developerKeysCopy(
      [{name: 'Cursor', keyPrefix: 'omi_mcp_cd', createdAtMs}],
      mcpTitleCopy(),
    ),
  ).toEqual([{title: mcpTitleCopy(), copy: `Cursor · omi_mcp_cd · ${created}`}]);
  expect(
    developerKeyRowCopy(
      {name: 'Local', keyPrefix: 'omi_sk_ab', createdAtMs},
      {maskPrefix: true},
    ),
  ).toBe(`Local · omi_sk_ab*** · ${created}`);
  expect(developerKeyRowCopy({name: 'Local', keyPrefix: 'omi_sk_ab'})).toBe(
    'Local · omi_sk_ab',
  );
});

test('developer key copy names GET empty keys Flutter No API keys yet plus createKeyToGetStarted', () => {
  expect(developerApiTitleCopy()).toBe('Developer API');
  expect(mcpTitleCopy()).toBe('MCP');
  expect(webhooksTitleCopy()).toBe('Webhooks');
  expect(userIdTitleCopy()).toBe('User ID');
  expect(userIdChipCopy('user-1')).toBe('user-1');
  expect(userIdChipCopy('123456')).toBe('123456');
  expect(userIdChipCopy('user-42')).toBe('use•••••-42');
  expect(userIdChipCopy('1234567')).toBe('123•••••567');
  expect(userIdChipCopy('firebase-uid-abcdefghijklmnopqrstuvwxyz')).toBe(
    'fir•••••xyz',
  );
  expect(userIdChipCopy('')).toBe('Account id unavailable');
  expect(userIdChipCopy(' \t')).toBe('Account id unavailable');
  expect(signOutTitleCopy()).toBe('Sign Out');
  expect(privacyPolicyTitleCopy()).toBe('Privacy Policy');
  expect(termsOfServiceTitleCopy()).toBe('Terms of Service');
  expect(permissionsTitleCopy()).toBe('Permissions');
  expect(developerKeysEmptyCopy()).toBe(
    'No API keys yet\nCreate a key to get started',
  );
  expect(developerKeysCopy([], developerApiTitleCopy())).toEqual([
    {title: developerApiTitleCopy(), copy: developerKeysEmptyCopy()},
  ]);
  expect(
    developerKeysCopy([], developerApiTitleCopy(), {
      emptyScopesCopy: 'Read Only',
    }),
  ).toEqual([{title: developerApiTitleCopy(), copy: developerKeysEmptyCopy()}]);
  expect(developerKeysCopy([], mcpTitleCopy())).toEqual([
    {title: mcpTitleCopy(), copy: developerKeysEmptyCopy()},
  ]);
  expect(developerKeysCopy(null, developerApiTitleCopy())).toEqual([]);
  expect(developerKeysCopy(null, mcpTitleCopy())).toEqual([]);
});

test('developer webhook status copy does not say unknown for a missing enablement bit', () => {
  expect(developerWebhookStatusCopy(true)).toBe('Enabled');
  expect(developerWebhookStatusCopy(false)).toBe('Disabled');
  expect(developerWebhookStatusCopy(null)).toBe('Status unavailable');
});

test('developer webhook rows name Flutter webhook descriptions', () => {
  expect(developerWebhookDescriptionCopy('memory_created')).toBe(
    'New conversation created',
  );
  expect(developerWebhookDescriptionCopy('realtime_transcript')).toBe(
    'Transcript received',
  );
  expect(developerWebhookDescriptionCopy('audio_bytes')).toBe(
    'Audio data received',
  );
  expect(developerWebhookDescriptionCopy('day_summary')).toBe(
    'Summary generated',
  );
  expect(developerWebhookDescriptionCopy('button_event')).toBe(null);
  expect(developerWebhookDescriptionCopy('')).toBe(null);
  expect(
    developerWebhookRowCopy({
      type: 'memory_created',
      enabled: true,
      url: 'https://example.test/conversation',
    }),
  ).toBe(
    'Enabled · https://example.test/conversation\nNew conversation created',
  );
  expect(
    developerWebhookRowCopy({
      type: 'realtime_transcript',
      enabled: false,
      url: null,
    }),
  ).toBe('Disabled\nTranscript received');
  expect(
    developerWebhookRowCopy({
      type: 'audio_bytes',
      enabled: true,
      url: 'https://example.test/audio',
      intervalSeconds: '5',
    }),
  ).toBe('Enabled · https://example.test/audio · 5s\nAudio data received');
  expect(
    developerWebhookRowCopy({
      type: 'day_summary',
      enabled: true,
      url: null,
    }),
  ).toBe('Enabled\nSummary generated');
  expect(
    developerWebhookRowCopy({
      type: 'button_event',
      enabled: null,
      url: 'https://example.test/button',
    }),
  ).toBe('Status unavailable · https://example.test/button');
});

test('developer webhook rows name Flutter webhook empty GET URLs', () => {
  expect(
    developerWebhookRowCopy({
      enabled: true,
      url: 'https://example.test/conversation',
    }),
  ).toBe('Enabled · https://example.test/conversation');
  expect(developerWebhookRowCopy({enabled: false, url: null})).toBe('Disabled');
  expect(developerWebhookRowCopy({enabled: true, url: ''})).toBe('Enabled');
  expect(developerWebhookRowCopy({enabled: true, url: ' \t\n'})).toBe(
    'Enabled ·  \t\n',
  );
  expect(developerWebhookRowCopy({enabled: true, url: '\u0085'})).toBe(
    'Enabled · \u0085',
  );
  expect(developerWebhookRowCopy({enabled: null, url: '\u00A0'})).toBe(
    'Status unavailable · \u00A0',
  );
  expect(
    developerWebhookRowCopy({enabled: true, url: '  https://example.test/a  '}),
  ).toBe('Enabled ·   https://example.test/a  ');
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
  expect(accountFieldCopy(null, primaryLanguageNotSetCopy())).toBe(
    primaryLanguageNotSetCopy(),
  );
  expect(accountFieldCopy(' \t\n', primaryLanguageNotSetCopy())).toBe(
    primaryLanguageNotSetCopy(),
  );
  expect(accountFieldCopy('\u00A0', primaryLanguageNotSetCopy())).toBe(
    primaryLanguageNotSetCopy(),
  );
  expect(accountFieldCopy('  Ada  ', primaryLanguageNotSetCopy())).toBe('Ada');
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
  expect(appCategoryCopy('productivity-and-organization')).toBe('Productivity');
  expect(appCategoryCopy('personal-wellness')).toBe('Personal & Lifestyle');
  expect(appCategoryCopy('health-and-wellness')).toBe('Health');
  expect(appCategoryCopy('conversation-analysis')).toBe(
    'Conversation Analysis',
  );
  expect(appCategoryCopy('other')).toBe('Other');
  expect(appCategoryCopy('productivity')).toBe('Productivity');
  expect(appCategoryCopy('health-fitness')).toBe('Health Fitness');
  expect(appCategoryCopy('')).toBe('');
  expect(appCategoryCopy(' \t')).toBe('');
});

test('app section category copy names Flutter CategorySection GET category and omits AppListItem', () => {
  expect(appSectionCategoryCopy('health-and-wellness', true)).toBe('Health');
  expect(
    appSectionCategoryCopy('productivity-and-organization', true),
  ).toBe('Productivity');
  expect(appSectionCategoryCopy('health-and-wellness', false)).toBeNull();
  expect(
    appSectionCategoryCopy('productivity-and-organization', false),
  ).toBeNull();
  expect(appSectionCategoryCopy('', true)).toBeNull();
  expect(appSectionCategoryCopy(' \t', true)).toBeNull();
});

test('app display source names Flutter empty GET details', () => {
  expect(appDisplaySource({author: '', category: '', description: ''})).toBe(
    '',
  );
  expect(
    appDisplaySource({author: ' \t\n', category: ' \t', description: '\u00A0'}),
  ).toBe('');
  expect(
    appDisplaySource({
      author: '\u0085',
      category: '\u0085',
      description: '\u0085',
    }),
  ).toBe('');
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

test('app display name names Flutter empty GET names', () => {
  expect(appDisplayName('')).toBe('');
  expect(appDisplayName(' \t\n')).toBe(' \t\n');
  expect(appDisplayName('\u00A0')).toBe('\u00A0');
  expect(appDisplayName('  Owned app  ')).toBe('  Owned app  ');
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

test('app explore rating copy names Flutter CategorySection GET scores', () => {
  expect(appExploreRatingCopy(4.5, 12)).toBe('4.5 · 12 ratings');
  expect(appExploreRatingCopy(4, 0)).toBe('4.0 · 0 ratings');
  expect(appExploreRatingCopy(4.5, 1)).toBe('4.5 · 1 rating');
  expect(appExploreRatingCopy(4.5, null)).toBe('4.5 · 0 ratings');
  expect(appExploreRatingCopy(null, 12)).toBe(null);
  expect(appExploreRatingCopy(undefined, undefined)).toBe(null);
  expect(appExploreRatingCopy(Number.NaN, 12)).toBe(null);
  expect(appExploreRatingCopy(4.5, -1)).toBe('4.5 · 0 ratings');
});

test('app list private name copy names Flutter AppListItem lock and omits CategorySection Private', () => {
  expect(appListPrivateNameCopy('Owned app', true, true)).toBe('Owned app');
  expect(appListPrivateNameCopy('Owned app', true, false)).toBe('Owned app 🔒');
  expect(appListPrivateNameCopy('Owned app', false, false)).toBe('Owned app');
  expect(appListPrivateNameCopy('Owned app', false, true)).toBe('Owned app');
  expect(appListPrivateNameCopy('  Owned app  ', true, false)).toBe(
    '  Owned app   🔒',
  );
  expect(appListPrivateNameCopy('', true, false)).toBe(' 🔒');
  expect(appListPrivateNameCopy(' \t', true, true)).toBe(' \t');
  expect(appListPrivateNameCopy(' \t', true, false)).toBe(' \t 🔒');
});

test('app list description copy names Flutter AppListItem truncated GET description', () => {
  expect(appListDescriptionCopy('Calendar sync')).toBe('Calendar sync');
  expect(appListDescriptionCopy('A'.repeat(50))).toBe('A'.repeat(50));
  expect(appListDescriptionCopy('A'.repeat(51))).toBe(`${'A'.repeat(50)}...`);
  expect(appListDescriptionCopy('  Calendar sync  ')).toBe('  Calendar sync  ');
  expect(appListDescriptionCopy(` ${'A'.repeat(50)}`)).toBe(
    ` ${'A'.repeat(49)}...`,
  );
  expect(appListDescriptionCopy(' \t')).toBe(' \t');
  expect(appListDescriptionCopy('')).toBe('');
  expect(appListDescriptionCopy('\u0085')).toBe('\u0085');
  expect(appListDescriptionCopy(undefined)).toBeNull();
  expect(appListDescriptionCopy(null)).toBeNull();
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

test('device display name names Flutter empty GET names', () => {
  expect(deviceDisplayName('')).toBe('');
  expect(deviceDisplayName(' \t\n')).toBe(' \t\n');
  expect(deviceDisplayName('\u00A0')).toBe('\u00A0');
  expect(deviceDisplayName('  Omi  ')).toBe('  Omi  ');
});

test('device information copy names Flutter empty GET chips', () => {
  expect(deviceInformationCopy('')).toBe('');
  expect(deviceInformationCopy(' \t\n')).toBe(' \t\n');
  expect(deviceInformationCopy('\u00A0')).toBe('\u00A0');
  expect(deviceInformationCopy('\u0085')).toBe('\u0085');
  expect(deviceInformationCopy('  Omi Dev Kit  ')).toBe('  Omi Dev Kit  ');
  expect(deviceInformationCopy(null)).toBe(deviceUnknownCopy());
  expect(deviceInformationCopy(undefined)).toBe(deviceUnknownCopy());
});

test('chat message display text names Flutter empty GET text', () => {
  expect(
    chatMessageDisplayText({
      text: '',
      generationOutcome: null,
    }),
  ).toBe('');
  expect(
    chatMessageDisplayText({
      text: ' \t\n',
      generationOutcome: 'completed',
    }),
  ).toBe('');
  expect(
    chatMessageDisplayText({
      text: '\u00A0',
      generationOutcome: null,
    }),
  ).toBe('');
  expect(
    chatMessageDisplayText({
      text: '\u0085',
      generationOutcome: 'completed',
    }),
  ).toBe('');
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

test('chat message body slot names Flutter HumanMessage empty GET text and AI whitespace', () => {
  expect(
    chatMessageShowsBodySlot(
      {text: '', sender: 'human'},
      chatMessageDisplayText({text: '', generationOutcome: null}),
    ),
  ).toBe(true);
  expect(
    chatMessageShowsBodySlot(
      {text: ' \t\n', sender: 'human'},
      chatMessageDisplayText({text: ' \t\n', generationOutcome: null}),
    ),
  ).toBe(true);
  expect(
    chatMessageShowsBodySlot(
      {text: ' \t\n', sender: 'ai'},
      chatMessageDisplayText({
        text: ' \t\n',
        generationOutcome: 'completed',
      }),
    ),
  ).toBe(true);
  expect(
    chatMessageShowsBodySlot(
      {text: '', sender: 'ai'},
      chatMessageDisplayText({
        text: '',
        generationOutcome: 'completed',
      }),
    ),
  ).toBe(false);
  expect(
    chatMessageShowsBodySlot(
      {text: '', sender: 'ai'},
      chatMessageDisplayText({
        text: '',
        generationOutcome: 'cancelled',
      }),
    ),
  ).toBe(true);
  expect(
    chatMessageShowsBodySlot(
      {text: '', sender: 'ai'},
      chatMessageDisplayText({
        text: '',
        generationOutcome: 'completed',
        contentBlocks: [{eyebrow: 'Discovery', title: 'Quiet mornings'}],
      }),
    ),
  ).toBe(false);
});

test('chat human quoted context copy names Flutter HumanMessage Context chrome', () => {
  expect(
    chatHumanQuotedContextCopy(
      'Context: "Meeting notes from standup about the launch"\n\nWhat should I do next?',
    ),
  ).toEqual({
    context: 'Meeting notes from standup about the launch',
    remainder: 'What should I do next?',
  });
  expect(
    chatHumanQuotedContextCopy(
      'Context: "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ"\n\nAsk this',
    ),
  ).toEqual({
    context: 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWX...',
    remainder: 'Ask this',
  });
  expect(chatHumanQuotedContextCopy('What should I do next?')).toEqual({
    context: null,
    remainder: 'What should I do next?',
  });
  expect(
    chatHumanQuotedContextCopy('Context: "no blank line"\nWhat next?'),
  ).toEqual({
    context: null,
    remainder: 'Context: "no blank line"\nWhat next?',
  });
  expect(
    chatMessageDisplayText({
      text: 'Context: "Meeting notes from standup about the launch"\n\nWhat should I do next?',
      generationOutcome: null,
    }),
  ).toBe(
    'Context: "Meeting notes from standup about the launch"\n\nWhat should I do next?',
  );
});

test('chat message copy names GET chart points and omits empty charts', () => {
  expect(
    chatChartCopy({
      title: 'Talk time',
      points: [
        {label: 'Mon', value: 12},
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
      points: [],
    }),
  ).toBeNull();
});

test('names Flutter ChartMessageWidget empty GET title instead of omitting the heading', () => {
  expect(
    chatChartCopy({
      title: '',
      points: [
        {label: 'Mon', value: 12},
        {label: 'Tue', value: 15},
      ],
    }),
  ).toBe('\nMon · 12\nTue · 15');
  expect(
    chatChartCopy({
      title: ' \t',
      points: [{label: 'Mon', value: 12}],
    }),
  ).toBe('\nMon · 12');
  expect(
    chatMessageDisplayText({
      text: 'Here is the trend.',
      generationOutcome: null,
      chart: {
        title: '',
        points: [{label: 'Mon', value: 12}],
      },
    }),
  ).toBe('Here is the trend.\n\nMon · 12');
});

test('names Flutter ChartMessageWidget empty GET point labels instead of omitting the chart', () => {
  expect(
    chatChartCopy({
      title: 'Talk time',
      points: [
        {label: 'Mon', value: 12},
        {label: ' \t', value: 1},
        {label: 'Tue', value: 15},
      ],
    }),
  ).toBe('Talk time\nMon · 12\n · 1\nTue · 15');
  expect(
    chatChartCopy({
      title: 'Talk time',
      points: [{label: '', value: 12}],
    }),
  ).toBe('Talk time\n · 12');
  expect(
    chatChartCopy({
      title: '',
      points: [{label: ' \t', value: 12}],
    }),
  ).toBe('\n · 12');
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
  ).toEqual({eyebrow: 'Task', title: chatBlockUnavailableCopy()});
  expect(
    paintedChatContentBlock({eyebrow: 'Task', taskId: 'missing'}),
  ).toEqual({eyebrow: 'Task', title: chatBlockLoadingCopy()});
  expect(chatBlockLoadingCopy()).toBe('Loading...');
  expect(
    paintedChatContentBlock({eyebrow: 'Task', taskId: 'missing'}, []),
  ).toEqual({eyebrow: 'Task', title: chatBlockUnavailableCopy()});
  expect(
    paintedChatContentBlock(
      {eyebrow: 'Task', taskId: 'task-join'},
      [{id: 'task-join', title: ' \t'}],
    ),
  ).toEqual({eyebrow: 'Task', title: ''});
  expect(
    JSON.stringify(
      paintedChatContentBlock({eyebrow: 'Task', taskId: 'task-join'}, tasks),
    ),
  ).not.toContain('task-join');
  expect(
    JSON.stringify(
      paintedChatContentBlock({eyebrow: 'Task', taskId: 'missing'}, tasks),
    ),
  ).not.toContain('missing');
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

test('names Flutter TaskCardBlock empty GET descriptions instead of omitting the title', () => {
  expect(
    taskCardDescription('task-join', [{id: 'task-join', title: ''}]),
  ).toBe('');
  expect(
    taskCardDescription('task-join', [{id: 'task-join', title: ' \t'}]),
  ).toBe('');
  expect(
    taskCardDescription('task-alias', [
      {id: 'other', taskId: 'task-alias', title: ''},
    ]),
  ).toBe('');
  expect(
    paintedChatContentBlock(
      {eyebrow: 'Task', taskId: 'task-join'},
      [{id: 'task-join', title: ''}],
    ),
  ).toEqual({eyebrow: 'Task', title: ''});
  expect(
    paintedChatContentBlock(
      {eyebrow: 'Task', taskId: 'task-join'},
      [{id: 'task-join', title: ' \t'}],
    ),
  ).toEqual({eyebrow: 'Task', title: ''});
  expect(
    paintedChatContentBlock(
      {eyebrow: 'Task', taskId: 'task-alias'},
      [{id: 'other', taskId: 'task-alias', title: ''}],
    ),
  ).toEqual({eyebrow: 'Task', title: ''});
  expect(
    paintedChatContentBlock({eyebrow: 'Task', taskId: 'missing'}, [
      {id: 'task-join', title: ''},
    ]),
  ).toEqual({eyebrow: 'Task', title: chatBlockUnavailableCopy()});
});

test('goal link chrome names loaded GET miss No longer available without leaking ids', () => {
  const goals = [{id: 'goal-join'}];
  expect(
    paintedChatContentBlock(
      {eyebrow: 'Goal', title: 'Ship the recap', goalId: 'goal-join'},
      undefined,
      false,
      goals,
    ),
  ).toEqual({eyebrow: 'Goal', title: 'Ship the recap'});
  expect(
    paintedChatContentBlock(
      {eyebrow: 'Goal', title: 'Ship the recap', goalId: 'missing'},
      undefined,
      false,
      goals,
    ),
  ).toEqual({eyebrow: 'Goal', title: chatBlockUnavailableCopy()});
  expect(
    paintedChatContentBlock({
      eyebrow: 'Goal',
      title: 'Ship the recap',
      goalId: 'missing',
    }),
  ).toEqual({eyebrow: 'Goal', title: 'Ship the recap'});
  expect(
    paintedChatContentBlock(
      {eyebrow: 'Goal', title: 'Ship the recap', goalId: 'missing'},
      undefined,
      false,
      [],
    ),
  ).toEqual({eyebrow: 'Goal', title: chatBlockUnavailableCopy()});
  expect(
    JSON.stringify(
      paintedChatContentBlock(
        {eyebrow: 'Goal', title: 'Ship the recap', goalId: 'missing'},
        undefined,
        false,
        goals,
      ),
    ),
  ).not.toContain('missing');
  expect(
    paintedChatContentBlock(
      {eyebrow: 'Goal', title: 'Ship the recap', goalId: 'goal-join'},
      undefined,
      false,
      goals,
    ),
  ).not.toHaveProperty('goalId');
  expect(
    paintedChatContentBlock(
      {eyebrow: 'Memory', title: 'Prefers concise notes', goalId: 'missing'},
      undefined,
      false,
      goals,
    ),
  ).toEqual({eyebrow: 'Memory', title: 'Prefers concise notes'});
});

test('memory link chrome names loaded GET miss No longer available without leaking ids', () => {
  const memories = [{id: 'mem-join'}];
  expect(
    paintedChatContentBlock(
      {eyebrow: 'Memory', title: 'Prefers concise notes', memoryId: 'mem-join'},
      undefined,
      false,
      undefined,
      memories,
    ),
  ).toEqual({eyebrow: 'Memory', title: 'Prefers concise notes'});
  expect(
    paintedChatContentBlock(
      {eyebrow: 'Memory', title: 'Prefers concise notes', memoryId: 'missing'},
      undefined,
      false,
      undefined,
      memories,
    ),
  ).toEqual({eyebrow: 'Memory', title: chatBlockUnavailableCopy()});
  expect(
    paintedChatContentBlock({
      eyebrow: 'Memory',
      title: 'Prefers concise notes',
      memoryId: 'missing',
    }),
  ).toEqual({eyebrow: 'Memory', title: 'Prefers concise notes'});
  expect(
    paintedChatContentBlock(
      {eyebrow: 'Memory', title: 'Prefers concise notes', memoryId: 'missing'},
      undefined,
      false,
      undefined,
      [],
    ),
  ).toEqual({eyebrow: 'Memory', title: chatBlockUnavailableCopy()});
  expect(
    JSON.stringify(
      paintedChatContentBlock(
        {eyebrow: 'Memory', title: 'Prefers concise notes', memoryId: 'missing'},
        undefined,
        false,
        undefined,
        memories,
      ),
    ),
  ).not.toContain('missing');
  expect(
    paintedChatContentBlock(
      {eyebrow: 'Memory', title: 'Prefers concise notes', memoryId: 'mem-join'},
      undefined,
      false,
      undefined,
      memories,
    ),
  ).not.toHaveProperty('memoryId');
  expect(
    paintedChatContentBlock(
      {eyebrow: 'Goal', title: 'Ship the recap', memoryId: 'missing'},
      undefined,
      false,
      undefined,
      memories,
    ),
  ).toEqual({eyebrow: 'Goal', title: 'Ship the recap'});
});

test('discovery chrome names GET fullText Show more without leaking the wire key', () => {
  const block = {
    eyebrow: 'Discovery',
    title: 'Quiet mornings',
    detail: 'You like a slow start.',
    more: 'Longer body stays collapsed.',
  };
  expect(paintedChatContentBlock(block)).toEqual({
    eyebrow: 'Discovery',
    title: 'Quiet mornings',
    detail: 'You like a slow start.',
  });
  expect(paintedChatContentBlock(block, undefined, true)).toEqual({
    eyebrow: 'Discovery',
    title: 'Quiet mornings',
    detail: 'Longer body stays collapsed.',
  });
  expect(JSON.stringify(paintedChatContentBlock(block))).not.toContain(
    'full_text',
  );
  expect(JSON.stringify(paintedChatContentBlock(block))).not.toContain(
    chatDiscoveryShowMoreCopy(),
  );
  expect(chatDiscoveryShowMoreCopy()).toBe('Show more');
  expect(chatDiscoveryShowLessCopy()).toBe('Show less');
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

test('chat attachment display name names Flutter empty GET names', () => {
  expect(chatAttachmentDisplayName('')).toBe('');
  expect(chatAttachmentDisplayName(' \t\n')).toBe('');
  expect(chatAttachmentDisplayName('\u00A0')).toBe('');
  expect(chatAttachmentDisplayName('\u0085')).toBe('');
  expect(chatAttachmentDisplayName('  notes.txt  ')).toBe('notes.txt');
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
  ).toBe('');
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
    chatAttachmentCopy({
      displayName: 'meeting-notes.pdf',
      mediaType: 'application/pdf',
      sizeBytes: 2048,
    }),
  ).toBe('meeting-notes.pdf');
  expect(
    chatAttachmentCopy({
      displayName: 'notes.txt',
      mediaType: 'text/plain',
      sizeBytes: 12,
    }),
  ).toBe('notes.txt');
  expect(
    chatAttachmentCopy({
      displayName: 'notes.txt',
      mediaType: 'text/plain',
      sizeBytes: 12,
    }),
  ).not.toContain('Text');
  expect(
    chatAttachmentCopy({
      displayName: 'meeting-notes.pdf',
      mediaType: 'application/pdf',
      sizeBytes: 2048,
    }),
  ).not.toContain('PDF');
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
  ).toBe('notes.txt');
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
  ).toBe('Here is the note.\nnotes.txt');
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
  ).toBe('Hello\nmeeting-notes.pdf');
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
  ).toBe('');
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
  ).not.toContain('Size unavailable');
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
  ).not.toContain('Attachment name unavailable');
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

test('chat memory citation copy names Flutter empty GET titles', () => {
  expect(
    chatMemoryCitationCopy({title: 'Morning standup', emoji: '🚀'}),
  ).toBe('🚀 Morning standup');
  expect(chatMemoryCitationCopy({title: '', emoji: '🧠'})).toBe('🧠 ');
  expect(chatMemoryCitationCopy({title: '  ', emoji: '✨'})).toBe('✨ ');
  expect(chatMemoryCitationCopy({title: '\u0085', emoji: '🧠'})).toBe('🧠 ');
  expect(chatMemoryCitationCopy({title: ''})).toBe(' ');
  expect(chatMemoryCitationCopy({title: ' \t'})).toBe(' ');
});

test('names Flutter MemoriesMessageWidget empty GET emoji instead of omitting the prefix', () => {
  expect(chatMemoryCitationCopy({title: 'Notes'})).toBe(' Notes');
  expect(chatMemoryCitationCopy({title: 'Notes', emoji: ''})).toBe(' Notes');
  expect(chatMemoryCitationCopy({title: 'Notes', emoji: ' \t'})).toBe(' Notes');
  expect(chatMemoryCitationCopy({title: '', emoji: ' \t'})).toBe(' ');
});

test('memory display text names Flutter empty GET content', () => {
  expect(memoryDisplayTitle({title: '', summary: ''})).toBe('');
  expect(memoryDisplayBody({title: '', summary: ''})).toBe('');
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
  expect(memoryDisplayTitle({title: ' \t', summary: ''})).toBe('');
  expect(memoryDisplayBody({title: '', summary: ' \t\n'})).toBe('');
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
  expect(memoryBaselineCopy({isBaseline: true})).toBe('⚑');
  expect(memoryHistoryCopy({})).toBeNull();
  expect(memoryHistoryCopy({history: false})).toBeNull();
  expect(memoryHistoryCopy({history: true})).toBe('⟳');
  expect(memoryHistoryPartialCopy()).toBe(
    'Some memory history is unavailable. Showing the history received so far.',
  );
  expect(memoryCaptureDeviceCopy(null)).toBeNull();
  expect(memoryCaptureDeviceCopy(' \t')).toBeNull();
  expect(memoryCaptureDeviceCopy('windows_ab12cd34')).toBeNull();
  expect(memoryCaptureDeviceCopy('macos_ab12cd34')).toBe('Mac');
  expect(memoryCaptureDeviceCopy('ios_ab12cd34')).toBe('iPhone');
  expect(memoryCaptureDeviceCopy('android_ab12cd34')).toBe('Android');
});

test('task display summary omits Flutter ActionItemsPage row due dates', () => {
  const secondScaleDue = 1786000000;
  expect(taskDisplaySummary({completed: false, dueAt: secondScaleDue})).toBe(
    null,
  );
  expect(taskDisplaySummary({completed: false, dueAt: null})).toBe(null);
  expect(taskDisplaySummary({completed: true, dueAt: secondScaleDue})).toBe(
    null,
  );
  expect(taskDisplaySummary({completed: true, dueAt: null})).toBe(null);
  expect(taskDisplaySummary({completed: false, dueAt: 0})).toBe(null);
  expect(
    taskDisplaySummary({completed: false, dueAt: 8_640_000_000_000_001}),
  ).toBe(null);
  expect(taskGroup(0, Date.now())).toBe('Later');
});

test('task display title names Flutter empty GET titles', () => {
  expect(taskDisplayTitle({title: ''})).toBe('');
  expect(taskDisplayTitle({title: ' \t\n'})).toBe('');
  expect(taskDisplayTitle({title: '\u0085'})).toBe('');
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

test('conversation display summary names Flutter empty GET overviews', () => {
  expect(
    conversationDisplaySummary({
      summary: '',
      status: 'processing',
    }),
  ).toBe('');
  expect(
    conversationDisplaySummary({
      summary: '',
      status: 'completed',
    }),
  ).toBe('');
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
  ).toBe('');
  expect(
    conversationDisplaySummary({
      summary: ' \t\n',
      status: 'completed',
    }),
  ).toBe('');
  expect(
    conversationDisplaySummary({
      summary: '\u0085',
      status: 'completed',
    }),
  ).toBe('');
  expect(
    conversationDisplaySummary({
      summary: '  Walked to the market.  ',
      status: 'completed',
    }),
  ).toBe('Walked to the market.');
});

test('conversation detail names Flutter noSummaryForConversation when GET has no summarized app', () => {
  expect(conversationNoSummaryCopy()).toBe(
    'No summary available\nfor this conversation.',
  );
  expect(processingConversationNoContentCopy()).toBe('No content to display');
  expect(processingConversationNoSummaryCopy()).toBe('No summary');
  expect(processingConversationStatusCopy()).toBe('Processing');
  expect(
    conversationDetailSummaryForStatusCopy('completed', true, {
      summary: '',
      sections: [],
    }),
  ).toBe(conversationNoSummaryCopy());
  expect(
    conversationDetailSummaryForStatusCopy('processing', true, {
      summary: '',
      sections: [],
    }),
  ).toBe(processingConversationNoSummaryCopy());
  expect(
    conversationDetailSummaryForStatusCopy('merging', false, {
      summary: '',
      sections: [],
    }),
  ).toBe(processingConversationStatusCopy());
  expect(
    conversationDetailSummaryForStatusCopy('processing', true, {
      summary: 'Still writing',
      sections: [],
    }),
  ).toBe('Still writing');
  expect(
    conversationDetailSummaryCopy({
      summary: '',
      sections: [],
    }),
  ).toBe(conversationNoSummaryCopy());
  expect(conversationNoSummaryForAppCopy()).toBe(
    'No summary available for this app. Try another app for better results.',
  );
  expect(
    conversationDetailSummaryCopy({
      summary: ' \t\n',
      sections: [],
      appSummary: '',
    }),
  ).toBe(conversationNoSummaryForAppCopy());
  expect(
    conversationDetailSummaryCopy({
      summary: '\u0085',
      sections: [],
    }),
  ).toBe(conversationNoSummaryForAppCopy());
  expect(
    conversationDetailSummaryCopy({
      summary: '',
      sections: [{heading: ' \t\n', bodyMarkdown: ' \t'}],
    }),
  ).toBe(conversationNoSummaryForAppCopy());
  expect(
    conversationDetailSummaryForStatusCopy('processing', true, {
      summary: ' \t\n',
      sections: [],
    }),
  ).toBe(processingConversationNoSummaryCopy());
  expect(
    conversationDetailSummaryForStatusCopy('completed', true, {
      summary: ' \t\n',
      sections: [],
    }),
  ).toBe(conversationNoSummaryForAppCopy());
  expect(
    conversationDetailSummaryCopy({
      summary: 'Day recap notes',
      sections: [],
    }),
  ).toBe('Day recap notes');
  expect(
    conversationDetailSummaryCopy({
      summary: '',
      sections: [{heading: 'Notes', bodyMarkdown: 'Full notes'}],
    }),
  ).toBeNull();
  expect(
    conversationDetailSummaryCopy({
      summary: '',
      sections: [],
      appSummary: 'App wrote this recap',
    }),
  ).toBeNull();
});

test('starred conversation filter names Flutter noStarredConversations', () => {
  expect(conversationsStarredEmptyCopy()).toBe(
    'No starred conversations\nTo star a conversation, open it and tap the star icon in the header.',
  );
});

test('conversation empty copy names Flutter noConversationsYet', () => {
  expect(conversationsEmptyHeadingCopy()).toBe('No conversations yet');
  expect(conversationsEmptyCopy()).toBe(
    'No conversations yet\nConversations you record show up here. Tap a tile on the home tab to start your first one.',
  );
});

test('memory empty copy names Flutter noMemoriesYet and noMemoriesFound', () => {
  expect(memoriesEmptyCopy()).toBe('🧠 No memories yet');
  expect(memoriesSearchEmptyCopy()).toBe('🔍 No memories found');
});

test('memory load error copy names Flutter couldNotLoadMemories', () => {
  expect(memoriesLoadErrorCopy()).toBe("Couldn't load memories");
});

test('task empty copy names Flutter noTasksYet', () => {
  expect(tasksEmptyCopy()).toBe(
    'No Tasks Yet\nTasks from your conversations will appear here.\nTap + to create one manually.',
  );
  expect(compactHomeTodayTasksTitleCopy()).toBe('Today');
  expect(compactHomeTodayTasksHidesEmpty(undefined)).toBe(true);
  expect(compactHomeTodayTasksHidesEmpty('')).toBe(true);
  expect(compactHomeTodayTasksHidesEmpty("Nothing's waiting on you.")).toBe(
    true,
  );
  expect(compactHomeTodayTasksHidesEmpty(tasksEmptyCopy())).toBe(true);
  expect(compactHomeTodayTasksHidesEmpty('Tasks are incomplete.')).toBe(false);
  expect(compactHomeConversationsEmptyCopy()).toBe('No recaps yet');
  expect(compactHomeConversationsHidesEmpty(undefined)).toBe(true);
  expect(compactHomeConversationsHidesEmpty('')).toBe(true);
  expect(
    compactHomeConversationsHidesEmpty(compactHomeConversationsEmptyCopy()),
  ).toBe(true);
  expect(compactHomeConversationsHidesEmpty('Recaps are incomplete.')).toBe(
    false,
  );
});

test('task search empty copy names Flutter noResultsFound', () => {
  expect(tasksSearchEmptyCopy()).toBe('No results found');
});

test('apps empty copy names Flutter noAppsFound', () => {
  expect(appsEmptyCopy()).toBe('No apps found');
});

test('apps created-by-me copy names Flutter myApps', () => {
  expect(appsCreatedByMeCopy()).toBe('Created by me');
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

test('names Flutter MediaViewerPage whitespace GET photo descriptions instead of omitting the caption', () => {
  expect(
    conversationPhotoChrome({discarded: false, description: ' \t'}),
  ).toBe(' \t');
  expect(
    conversationPhotoChrome({discarded: false, description: '\u0085'}),
  ).toBe('\u0085');
  expect(
    conversationPhotoChrome({discarded: false, description: ''}),
  ).toBeUndefined();
  expect(
    conversationPhotoChrome({discarded: false, description: 'Whiteboard notes'}),
  ).toBe('Whiteboard notes');
  expect(
    conversationPhotoChrome({
      discarded: false,
      description: '  Whiteboard notes  ',
    }),
  ).toBe('  Whiteboard notes  ');
  expect(conversationPhotoChrome({discarded: false})).toBe(
    conversationPhotoAnalyzingCopy(),
  );
  expect(
    conversationPhotoChrome({discarded: true, description: ' \t'}),
  ).toBe(conversationPhotoDiscardedCopy());
});

test('conversation discarded photo copy names Flutter ConversationListItem discarded photos only', () => {
  expect(
    conversationDiscardedPhotoCopy({discarded: true, photoCount: 3}),
  ).toBe('3 photos');
  expect(
    conversationDiscardedPhotoCopy({discarded: true, photoCount: 1}),
  ).toBe('1 photos');
  expect(
    conversationDiscardedPhotoCopy({discarded: false, photoCount: 3}),
  ).toBeNull();
  expect(
    conversationDiscardedPhotoCopy({discarded: true, photoCount: 0}),
  ).toBeNull();
  expect(conversationDiscardedPhotoCopy({discarded: true})).toBeNull();
});

test('conversation list category names GET wire values and Flutter ConversationListItem empty GET tags', () => {
  expect(conversationListCategory({discarded: false, category: 'work'})).toBe(
    'Work',
  );
  expect(conversationListCategory({discarded: false, category: 'other'})).toBe(
    'Other',
  );
  expect(conversationListCategory({discarded: false, category: ' \t\n'})).toBe(
    '',
  );
  expect(conversationListCategory({discarded: false, category: ''})).toBeNull();
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
  expect(
    conversationListTag({
      discarded: false,
      source: 'screenpipe',
    }),
  ).toBeNull();
  expect(
    conversationListTag({
      discarded: false,
      category: '',
      source: 'openglass',
    }),
  ).toBeNull();
  expect(
    conversationListTag({
      discarded: false,
      category: ' \t',
      source: 'sdcard',
    }),
  ).toBe('SD Card');
  expect(
    conversationListTag({
      discarded: false,
      category: ' \t',
      source: 'omi',
    }),
  ).toBe('');
  expect(
    conversationListTag({
      discarded: true,
      source: 'rayban_meta',
    }),
  ).toBeNull();
});

test('conversation visibility copy names GET private, shared, and public as Flutter chips', () => {
  expect(conversationVisibilityCopy('shared')).toBe('Shared');
  expect(conversationVisibilityCopy('public')).toBe('Shared');
  expect(conversationVisibilityCopy('private')).toBe('Private');
  expect(conversationVisibilityCopy(' \t\n')).toBeNull();
  expect(conversationVisibilityCopy(undefined)).toBeNull();
  expect(conversationVisibilityCopy('secret')).toBeNull();
});

test('conversation calendar attendee chip names Flutter GetSummaryWidgets first names', () => {
  expect(conversationCalendarAttendeesChipCopy(undefined)).toBeNull();
  expect(conversationCalendarAttendeesChipCopy([])).toBeNull();
  expect(conversationCalendarAttendeesChipCopy(['Alex Chen'])).toBe('Alex');
  expect(
    conversationCalendarAttendeesChipCopy(['Alex Chen', 'sam@example.com']),
  ).toBe('Alex, Sam');
  expect(
    conversationCalendarAttendeesChipCopy([
      'Alex Chen',
      'sam@example.com',
      'Priya Shah',
    ]),
  ).toBe('Alex, Sam +1');
  expect(conversationCalendarAttendeesChipCopy([' \t\n'])).toBe('');
  expect(
    conversationCalendarAttendeesChipCopy([
      'Alex Chen',
      ' \t\n',
      'sam@example.com',
    ]),
  ).toBe('Alex,  +1');
});

test('calendar event display title names Flutter empty GET titles', () => {
  expect(calendarEventDisplayTitle('')).toBe('');
  expect(calendarEventDisplayTitle(' \t\n')).toBe(' \t\n');
  expect(calendarEventDisplayTitle('\u00A0')).toBe('\u00A0');
  expect(calendarEventDisplayTitle('\u0085')).toBe('\u0085');
  expect(calendarEventDisplayTitle(undefined)).toBe('');
  expect(calendarEventDisplayTitle('  Standup  ')).toBe('  Standup  ');
});

test('conversation unknown-app copy names Flutter catalog-miss attribution', () => {
  expect(conversationUnknownAppCopy()).toBe('Unknown App');
});

test('conversation location address copy names Flutter GetGeolocationWidgets short address', () => {
  expect(conversationUnknownLocationCopy()).toBe('Unknown location');
  expect(
    conversationLocationAddressCopy(
      '123 Market St, Mission District, San Francisco, CA 94103',
    ),
  ).toBe('Mission District, San Francisco');
  expect(
    conversationLocationAddressCopy('123 Market St, San Francisco, CA'),
  ).toBe('123 Market St, San Francisco');
  expect(
    conversationLocationAddressCopy('123 Market St, San Francisco'),
  ).toBe('123 Market St, San Francisco');
  expect(conversationLocationAddressCopy('San Francisco')).toBe(
    'San Francisco',
  );
  expect(conversationLocationAddressCopy('  San Francisco  ')).toBe(
    '  San Francisco  ',
  );
  expect(conversationLocationAddressCopy('')).toBe(
    conversationUnknownLocationCopy(),
  );
  expect(conversationLocationAddressCopy(' \t\u0085 ')).toBe(' \t\u0085 ');
  expect(conversationLocationAddressCopy('\u0085')).toBe('\u0085');
  expect(conversationLocationAddressCopy(undefined)).toBe(
    conversationUnknownLocationCopy(),
  );
  expect(conversationLocationAddressCopy(null)).toBe(
    conversationUnknownLocationCopy(),
  );
});

test('names Flutter GetGeolocationWidgets whitespace GET address instead of Unknown location', () => {
  expect(conversationLocationAddressCopy(' \t')).toBe(' \t');
  expect(conversationLocationAddressCopy('\n')).toBe('\n');
  expect(conversationLocationAddressCopy('')).toBe(
    conversationUnknownLocationCopy(),
  );
});

test('conversation No Folder copy names Flutter l10n.noFolder', () => {
  expect(conversationNoFolderCopy()).toBe('No Folder');
});

test('transcript STT copy names Flutter getDisplayName empty as Unknown', () => {
  expect(transcriptSttUnknownCopy()).toBe('Unknown');
  expect(transcriptSttOmiFallbackCopy()).toBe('Omi');
  expect(transcriptSttProviderCopy('')).toBe(transcriptSttUnknownCopy());
  expect(transcriptSttProviderCopy('deepgram')).toBe('Deepgram');
  expect(transcriptSttProviderCopy('omi')).toBe(transcriptSttOmiFallbackCopy());
  expect(transcriptSttProviderCopy('whisper-cloudflare')).toBe(
    transcriptSttOmiFallbackCopy(),
  );
  expect(transcriptSttProviderCopy('Deepgram')).toBe(
    transcriptSttOmiFallbackCopy(),
  );
  expect(transcriptSttProviderCopy(' \t\u0085 ')).toBe(
    transcriptSttOmiFallbackCopy(),
  );
  expect(transcriptSttProviderCopy(undefined)).toBeUndefined();
  expect(transcriptSttProviderCopy(null)).toBeUndefined();
});

test('conversation structured emoji copy names Flutter omitted GET emoji as 🧠', () => {
  expect(conversationStructuredEmojiDefaultCopy()).toBe('🧠');
  expect(conversationStructuredEmojiCopy(undefined)).toBe(
    conversationStructuredEmojiDefaultCopy(),
  );
  expect(conversationStructuredEmojiCopy(null)).toBe(
    conversationStructuredEmojiDefaultCopy(),
  );
  expect(conversationStructuredEmojiCopy('🚀')).toBe('🚀');
  expect(conversationStructuredEmojiCopy('')).toBe('');
  expect(conversationStructuredEmojiCopy(' \t\u0085 ')).toBe('');
});

test('conversation list emoji names Flutter ConversationListItem empty GET emoji', () => {
  expect(conversationListEmoji({discarded: false, emoji: '🚀'})).toBe('🚀');
  expect(conversationListEmoji({discarded: false, emoji: ''})).toBe('');
  expect(conversationListEmoji({discarded: false, emoji: ' \t\u0085 '})).toBe(
    '',
  );
  expect(conversationListEmoji({discarded: false})).toBeNull();
  expect(
    conversationListEmoji({discarded: true, emoji: '🧠'}),
  ).toBeNull();
});

test('conversation structured category copy names Flutter omitted GET category as other', () => {
  expect(conversationStructuredCategoryDefaultCopy()).toBe('other');
  expect(conversationStructuredCategoryCopy(undefined)).toBe(
    conversationStructuredCategoryDefaultCopy(),
  );
  expect(conversationStructuredCategoryCopy(null)).toBe(
    conversationStructuredCategoryDefaultCopy(),
  );
  expect(conversationStructuredCategoryCopy('work')).toBe('work');
  expect(conversationStructuredCategoryCopy('')).toBeUndefined();
  expect(conversationStructuredCategoryCopy(' \t\u0085 ')).toBe('');
});

test('conversation first-party summary copy names Flutter appId-null attribution', () => {
  expect(conversationFirstPartySummaryCopy()).toBe('Summary');
});

test('conversation action-item copy names Flutter ActionItemsTab To-Do chrome', () => {
  expect(conversationActionItemsTodoCopy()).toBe('To-Do');
  expect(conversationActionItemsNoPendingCopy()).toBe(
    'No pending action items',
  );
  expect(conversationActionItemsCompletedCopy()).toBe('Completed');
  expect(conversationActionItemsNoCompletedCopy()).toBe(
    'No completed items yet',
  );
  expect(conversationActionItemsEmptyCopy()).toBe('No Action Items');
  expect(conversationActionItemsEmptyDescriptionCopy()).toBe(
    'Tasks and to-dos from this conversation will appear here once they are created.',
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

test('conversation list group copy names Flutter DateListItem and omits Today', () => {
  const now = new Date(2026, 7, 14, 12, 0).getTime();
  expect(
    conversationListGroupCopy(
      new Date(2026, 7, 14, 1, 0).toISOString(),
      now,
    ),
  ).toBeNull();
  expect(
    conversationListGroupCopy(
      new Date(2026, 7, 13, 23, 0).toISOString(),
      now,
    ),
  ).toBe('Yesterday');
  expect(
    conversationListGroupCopy(new Date(2026, 7, 10, 12, 0).toISOString(), now),
  ).toBe(
    new Date(2026, 7, 10, 12, 0).toLocaleDateString(undefined, {
      month: 'short',
      day: '2-digit',
    }),
  );
  expect(
    conversationListGroupCopy(new Date(2025, 7, 10, 12, 0).toISOString(), now),
  ).toBe(
    new Date(2025, 7, 10, 12, 0).toLocaleDateString(undefined, {
      month: 'short',
      day: '2-digit',
    }),
  );
  expect(
    conversationListGroupCopy(new Date(0).toISOString(), now),
  ).toBe('Date unavailable');
});

test('conversation list time copy names Flutter ConversationListItem h:mm a', () => {
  const older = new Date(2025, 7, 10, 12, 0);
  expect(conversationListTimeCopy(older.toISOString())).toBe(
    older.toLocaleTimeString(undefined, {
      hour: 'numeric',
      minute: '2-digit',
    }),
  );
  expect(conversationListTimeCopy(null)).toBe('Time unavailable');
  expect(conversationListTimeCopy(new Date(0).toISOString())).toBe(
    'Time unavailable',
  );
});

test('conversation detail date chip names Flutter GetSummaryWidgets date and time', () => {
  const now = new Date(2026, 7, 14, 12, 0).getTime();
  const time = (value: Date) =>
    value.toLocaleTimeString(undefined, {
      hour: 'numeric',
      minute: '2-digit',
    });
  const today = new Date(2026, 7, 14, 15, 4);
  expect(
    conversationDetailDateChipCopy(today.toISOString(), now),
  ).toBe(`Today, ${time(today)}`);
  const yesterday = new Date(2026, 7, 13, 15, 4);
  expect(
    conversationDetailDateChipCopy(yesterday.toISOString(), now),
  ).toBe(`Yesterday, ${time(yesterday)}`);
  const sameYear = new Date(2026, 7, 10, 12, 0);
  expect(
    conversationDetailDateChipCopy(sameYear.toISOString(), now),
  ).toBe(
    `${sameYear.toLocaleDateString(undefined, {
      month: 'short',
      day: 'numeric',
    })}, ${time(sameYear)}`,
  );
  const otherYear = new Date(2025, 7, 10, 12, 0);
  expect(
    conversationDetailDateChipCopy(otherYear.toISOString(), now),
  ).toBe(
    `${otherYear.toLocaleDateString(undefined, {
      month: 'short',
      day: 'numeric',
      year: 'numeric',
    })}, ${time(otherYear)}`,
  );
  expect(conversationDetailDateChipCopy(null, now)).toBe('Time unavailable');
  expect(
    conversationDetailDateChipCopy(new Date(0).toISOString(), now),
  ).toBe('Time unavailable');
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
      searchableText: '',
    }),
    expect.objectContaining({
      id: 'task2_abc',
      title: ' \t\n',
      searchableText: '',
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
              intent_backed: true,
              user_review: false,
              superseded_by: 'newer-fact',
              invalid_at: '2026-09-06T00:00:00Z',
              deleted: true,
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
  expect(result.items[0]).not.toHaveProperty('history');
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

test('canonical conversations name GET transcriptEndSeconds as list duration span', async () => {
  const result = await loadConversations(
    backendFor(() => ({
      status: 200,
      body: JSON.stringify(
        conversationPage([{...conversation, transcriptEndSeconds: 201}]),
      ),
    })),
  );
  expect(result.items[0]).toMatchObject({transcriptEndSeconds: 201});
  expect(result.items[0]).not.toHaveProperty('transcriptSegments');
  const omitted = await loadConversations(
    backendFor(() => ({
      status: 200,
      body: JSON.stringify(conversationPage([conversation])),
    })),
  );
  expect(omitted.items[0]).not.toHaveProperty('transcriptEndSeconds');
  await expect(
    loadConversations(
      backendFor(() => ({
        status: 200,
        body: JSON.stringify(
          conversationPage([{...conversation, transcriptEndSeconds: 0}]),
        ),
      })),
    ),
  ).rejects.toThrow('transcriptEndSeconds');
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
      ratingCount: 0,
      installs: 0,
      image: '',
    }),
  );
  expect(
    parseCloudApp(
      {
        id: 'catalog-app-rated-omitted-count',
        name: 'Rated without count',
        rating_avg: 4.5,
      },
      'App omitted count',
    ),
  ).toEqual(
    expect.objectContaining({
      ratingAvg: 4.5,
      ratingCount: 0,
    }),
  );
  expect(
    parseCloudApp(
      {
        id: 'catalog-app-rated-strings',
        name: 'String-rated app',
        rating_avg: '4.5',
        rating_count: '12',
        installs: '3',
      },
      'App strings',
    ),
  ).toEqual(
    expect.objectContaining({
      ratingAvg: 4.5,
      ratingCount: 12,
      installs: 3,
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

test('names Flutter AppListItem empty GET ids instead of failing the Apps page', () => {
  expect(
    parseCloudApps(
      [
        {id: '', name: 'Blank id'},
        {id: ' \t', name: 'Whitespace id'},
        {id: '\u0085', name: 'Next line id'},
        {id: '  padded  ', name: 'Padded id'},
        {id: 'catalog-app-1', name: 'Owned app'},
      ],
      'Apps response',
    ),
  ).toEqual([
    expect.objectContaining({id: '', name: 'Blank id'}),
    expect.objectContaining({id: ' \t', name: 'Whitespace id'}),
    expect.objectContaining({id: '\u0085', name: 'Next line id'}),
    expect.objectContaining({id: '  padded  ', name: 'Padded id'}),
    expect.objectContaining({id: 'catalog-app-1', name: 'Owned app'}),
  ]);
  expect(() => parseCloudApp({name: 'Omitted id'}, 'App 0')).toThrow(
    'App 0 is malformed',
  );
  expect(() => parseCloudApp({id: null, name: 'Null id'}, 'App 0')).toThrow(
    'App 0 is malformed',
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
  expect(parseCloudApp({id: 'catalog-app-1'}, 'App 0')).toEqual(
    expect.objectContaining({id: 'catalog-app-1', name: ''}),
  );
  expect(
    parseCloudApps(
      [{id: 'catalog-omitted'}, {id: 'catalog-named', name: 'Owned app'}],
      'Apps response',
    ),
  ).toEqual([
    expect.objectContaining({id: 'catalog-omitted', name: ''}),
    expect.objectContaining({id: 'catalog-named', name: 'Owned app'}),
  ]);
  expect(() =>
    parseCloudApp({id: 'catalog-app-1', name: 1}, 'App 0'),
  ).toThrow('App 0 is malformed');
  expect(() =>
    parseCloudApp({id: 'catalog-app-1', name: null}, 'App 0'),
  ).toThrow('App 0 is malformed');
});

test('names JSON-null GET connected_accounts as omitted instead of hiding neighbors', () => {
  expect(
    parseCloudApps(
      [
        {id: 'catalog-null-accounts', connected_accounts: null},
        {
          id: 'catalog-named',
          name: 'Owned app',
          connected_accounts: ['calendar'],
        },
      ],
      'Apps response',
    ),
  ).toEqual([
    expect.objectContaining({
      id: 'catalog-null-accounts',
      connectedAccounts: [],
    }),
    expect.objectContaining({
      id: 'catalog-named',
      name: 'Owned app',
      connectedAccounts: ['calendar'],
    }),
  ]);
  expect(parseCloudApp({id: 'catalog-app-1'}, 'App 0')).toEqual(
    expect.objectContaining({id: 'catalog-app-1', connectedAccounts: []}),
  );
  expect(() =>
    parseCloudApp(
      {id: 'catalog-app-1', connected_accounts: {calendar: true}},
      'App 0',
    ),
  ).toThrow('App 0 connected_accounts are malformed');
  expect(() =>
    parseCloudApp({id: 'catalog-app-1', connected_accounts: [1]}, 'App 0'),
  ).toThrow('App 0 connected_accounts are malformed');
});

test('names Flutter UsagePage fromJson invalid GET subscription extras', () => {
  const valid = {
    insights_gained_limit: 0,
    insights_gained_used: 0,
    transcription_seconds_limit: 0,
    transcription_seconds_used: 0,
    words_transcribed_limit: 0,
    words_transcribed_used: 0,
    subscription: {plan: 'basic', status: 'active'},
  };
  expect(parseCloudSubscription(valid, 'Subscription response')).toEqual(
    expect.objectContaining({
      plan: 'basic',
      status: 'active',
      transcriptionSecondsUsed: 0,
      transcriptionSecondsLimit: 0,
      wordsTranscribedUsed: 0,
      wordsTranscribedLimit: 0,
      insightsGainedUsed: 0,
      insightsGainedLimit: 0,
    }),
  );
  expect(
    parseCloudSubscription(
      {
        ...valid,
        available_plans: [],
        phone_call_quota: null,
        transcription_allowance: null,
        chat_quota_allowed: true,
        show_subscription_ui: false,
      },
      'Subscription response',
    ),
  ).toEqual(expect.objectContaining({plan: 'basic', status: 'active'}));
  expect(
    parseCloudSubscription(
      {
        ...valid,
        available_plans: [{id: 'plus', title: 'Plus'}],
        phone_call_quota: {has_access: false, is_paid: false},
        transcription_allowance: {mode: 'allowed'},
        subscription: {
          plan: 'basic',
          status: 'active',
          features: [],
          limits: {},
        },
      },
      'Subscription response',
    ),
  ).toEqual(expect.objectContaining({plan: 'basic'}));
  expect(() =>
    parseCloudSubscription(
      {plan: 'basic', status: 'active'},
      'Subscription response',
    ),
  ).toThrow('Subscription response insights_gained_limit is malformed');
  expect(() =>
    parseCloudSubscription(
      {subscription: {plan: 'basic', status: 'active'}},
      'Subscription response',
    ),
  ).toThrow('Subscription response insights_gained_limit is malformed');
  expect(() =>
    parseCloudSubscription(
      {...valid, transcription_seconds_used: 'bad'},
      'Subscription response',
    ),
  ).toThrow('Subscription response transcription_seconds_used is malformed');
  expect(() =>
    parseCloudSubscription(
      {...valid, available_plans: 'bad'},
      'Subscription response',
    ),
  ).toThrow('Subscription response available_plans is malformed');
  expect(() =>
    parseCloudSubscription(
      {...valid, available_plans: [{title: 'Plus'}]},
      'Subscription response',
    ),
  ).toThrow('Subscription response available_plans[0] is malformed');
  expect(() =>
    parseCloudSubscription(
      {...valid, phone_call_quota: {has_access: true}},
      'Subscription response',
    ),
  ).toThrow('Subscription response phone_call_quota is malformed');
  expect(() =>
    parseCloudSubscription(
      {...valid, transcription_allowance: {}},
      'Subscription response',
    ),
  ).toThrow('Subscription response transcription_allowance is malformed');
  expect(() =>
    parseCloudSubscription(
      {...valid, chat_quota_allowed: 'yes'},
      'Subscription response',
    ),
  ).toThrow('Subscription response chat_quota_allowed is malformed');
  expect(() =>
    parseCloudSubscription(
      {...valid, show_subscription_ui: 'yes'},
      'Subscription response',
    ),
  ).toThrow('Subscription response show_subscription_ui is malformed');
  expect(() =>
    parseCloudSubscription(
      {...valid, chat_quota_unit: 1},
      'Subscription response',
    ),
  ).toThrow('Subscription response chat_quota_unit is malformed');
  expect(() =>
    parseCloudSubscription(
      {
        ...valid,
        subscription: {plan: 'basic', status: 'active', features: [1]},
      },
      'Subscription response',
    ),
  ).toThrow('Subscription response subscription features is malformed');
  expect(() =>
    parseCloudSubscription(
      {
        ...valid,
        subscription: {plan: 'basic', status: 'active', limits: 'bad'},
      },
      'Subscription response',
    ),
  ).toThrow('Subscription response subscription limits is malformed');
  expect(() =>
    parseCloudSubscription(
      {
        ...valid,
        subscription: {
          plan: 'basic',
          status: 'active',
          cancel_at_period_end: 'yes',
        },
      },
      'Subscription response',
    ),
  ).toThrow(
    'Subscription response subscription cancel_at_period_end is malformed',
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
  const quota = {
    insights_gained_limit: 0,
    insights_gained_used: 0,
    transcription_seconds_limit: 0,
    transcription_seconds_used: 0,
    words_transcribed_limit: 0,
    words_transcribed_used: 0,
  };
  expect(
    parseCloudSubscription(
      {...quota, subscription: {plan: '', status: ''}},
      'Subscription response',
    ),
  ).toEqual(
    expect.objectContaining({
      plan: '',
      status: '',
      transcriptionSecondsUsed: 0,
      transcriptionSecondsLimit: 0,
      wordsTranscribedUsed: 0,
      wordsTranscribedLimit: 0,
      insightsGainedUsed: 0,
      insightsGainedLimit: 0,
      chatQuotaUsed: 0,
      chatQuotaUnit: null,
    }),
  );
  expect(
    parseCloudSubscription(
      {...quota, subscription: {plan: 'plus', status: 'active'}},
      'Subscription response',
    ),
  ).toEqual(expect.objectContaining({plan: 'plus', status: 'active'}));
  expect(
    parseCloudSubscription(
      {...quota, subscription: {status: 'active'}},
      'Subscription response',
    ),
  ).toEqual(expect.objectContaining({plan: 'basic', status: 'active'}));
  expect(
    parseCloudSubscription(
      {...quota, subscription: {plan: 'plus'}},
      'Subscription response',
    ),
  ).toEqual(expect.objectContaining({plan: 'plus', status: 'active'}));
  expect(
    parseCloudSubscription(
      {
        ...quota,
        transcription_seconds_used: 90,
        transcription_seconds_limit: 1800,
        subscription: {status: 'active'},
      },
      'Subscription response',
    ),
  ).toEqual(
    expect.objectContaining({
      plan: 'basic',
      status: 'active',
      transcriptionSecondsUsed: 90,
      transcriptionSecondsLimit: 1800,
    }),
  );
  expect(() =>
    parseCloudSubscription({plan: 1, status: 'active'}, 'Subscription response'),
  ).toThrow('Subscription response insights_gained_limit is malformed');
  expect(() =>
    parseCloudSubscription(
      {plan: null, status: 'active'},
      'Subscription response',
    ),
  ).toThrow('Subscription response insights_gained_limit is malformed');
  expect(() =>
    parseCloudSubscription(
      {...quota, subscription: {plan: 1, status: 'active'}},
      'Subscription response',
    ),
  ).toThrow('Subscription response is malformed');
});

test('names omitted GET subscription chat_quota_used as zero instead of hiding Chat this month', () => {
  const quota = {
    insights_gained_limit: 0,
    insights_gained_used: 0,
    transcription_seconds_limit: 0,
    transcription_seconds_used: 0,
    words_transcribed_limit: 0,
    words_transcribed_used: 0,
  };
  expect(
    parseCloudSubscription(
      {
        ...quota,
        chat_quota_unit: 'messages',
        subscription: {
          plan: 'plus',
          status: 'active',
          limits: {chat_questions_per_month: 100},
        },
      },
      'Subscription response',
    ),
  ).toEqual(
    expect.objectContaining({
      chatQuotaUsed: 0,
      chatQuotaUnit: 'messages',
      chatQuestionsPerMonth: 100,
    }),
  );
  expect(
    subscriptionPeriodCopy(
      parseCloudSubscription(
        {
          ...quota,
          chat_quota_unit: 'messages',
          subscription: {
            plan: 'plus',
            status: 'active',
            limits: {chat_questions_per_month: 100},
          },
        },
        'Subscription response',
      ),
    ),
  ).toEqual([
    {
      title: 'Chat this month',
      copy: `0 Chat\n${chatQuotaSubtitleCopy()}\n0 of 100 messages used this month`,
    },
  ]);
  expect(
    subscriptionPeriodCopy(
      parseCloudSubscription(
        {
          ...quota,
          chat_quota_unit: 'cost_usd',
          subscription: {plan: 'plus', status: 'active'},
        },
        'Subscription response',
      ),
    ),
  ).toEqual([
    {
      title: 'Chat this month',
      copy: `$0.00\n${chatQuotaSubtitleCopy()}\n$0.00 used this month`,
    },
  ]);
  expect(
    subscriptionPeriodCopy(
      parseCloudSubscription(
        {
          ...quota,
          subscription: {plan: 'plus', status: 'active'},
        },
        'Subscription response',
      ),
    ),
  ).toBeNull();
  expect(() =>
    parseCloudSubscription(
      {
        ...quota,
        chat_quota_used: null,
        subscription: {plan: 'plus', status: 'active'},
      },
      'Subscription response',
    ),
  ).toThrow('Subscription response chat_quota_used is malformed');
  expect(() =>
    parseCloudSubscription(
      {
        ...quota,
        chat_quota_used: 'nope',
        subscription: {plan: 'plus', status: 'active'},
      },
      'Subscription response',
    ),
  ).toThrow('Subscription response chat_quota_used is malformed');
});

test('subscription period copy names GET words insights and chat quotas without Upgrade', () => {
  expect(chatQuotaSubtitleCopy()).toBe(
    'AI chat messages used with Omi this month.',
  );
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
      copy: '12 of 10,000 words used this month',
    },
    {
      title: 'Insights this month',
      copy: '3 of 500 insights gained this month',
    },
    {
      title: 'Chat this month',
      copy: `5 Chat\n${chatQuotaSubtitleCopy()}\n5 of 100 messages used this month`,
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
    {
      title: 'Chat this month',
      copy: `$1.20\n${chatQuotaSubtitleCopy()}\n$1.20 of $20 used this month`,
    },
  ]);
  expect(
    parseCloudSubscription(
      {
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

test('names Flutter UsagePage empty GET chatQuotaUnit instead of omitting Chat this month', () => {
  const chat = {
    wordsTranscribedUsed: null,
    wordsTranscribedLimit: null,
    insightsGainedUsed: null,
    insightsGainedLimit: null,
    chatQuotaUsed: 5,
    chatQuestionsPerMonth: 100,
    chatCostUsdPerMonth: null,
  };
  expect(subscriptionPeriodCopy({...chat, chatQuotaUnit: ''})).toEqual([
    {
      title: 'Chat this month',
      copy: `5 Chat\n${chatQuotaSubtitleCopy()}\n5 of 100 messages used this month`,
    },
  ]);
  expect(subscriptionPeriodCopy({...chat, chatQuotaUnit: ' \t'})).toEqual([
    {
      title: 'Chat this month',
      copy: `5 Chat\n${chatQuotaSubtitleCopy()}\n5 of 100 messages used this month`,
    },
  ]);
  expect(subscriptionPeriodCopy({...chat, chatQuotaUnit: '\u0085'})).toEqual([
    {
      title: 'Chat this month',
      copy: `5 Chat\n${chatQuotaSubtitleCopy()}\n5 of 100 messages used this month`,
    },
  ]);
  expect(subscriptionPeriodCopy({...chat, chatQuotaUnit: null})).toBeNull();
  expect(
    subscriptionPeriodCopy(
      parseCloudSubscription(
        {
          insights_gained_limit: 0,
          insights_gained_used: 0,
          transcription_seconds_limit: 0,
          transcription_seconds_used: 0,
          words_transcribed_limit: 0,
          words_transcribed_used: 0,
          chat_quota_used: 5,
          chat_quota_unit: ' \t',
          subscription: {
            plan: 'plus',
            status: 'active',
            limits: {chat_questions_per_month: 100},
          },
        },
        'Subscription response',
      ),
    ),
  ).toEqual([
    {
      title: 'Chat this month',
      copy: `5 Chat\n${chatQuotaSubtitleCopy()}\n5 of 100 messages used this month`,
    },
  ]);
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
        body: JSON.stringify({
          insights_gained_limit: 0,
          insights_gained_used: 0,
          transcription_seconds_limit: 0,
          transcription_seconds_used: 0,
          words_transcribed_limit: 0,
          words_transcribed_used: 0,
          subscription: {plan: 'plus', status: 'active'},
        }),
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
  expect(snapshot.subscriptionError).toBeNull();
  expect(snapshot.storeRecordingPermission).toBe(true);
  expect(snapshot.trainingOptedIn).toBe(false);
  expect(snapshot.privateCloudSync).toBe(false);
  expect(snapshot.webhooks).toBeNull();
  expect(snapshot.usage).toBeNull();
  expect(snapshot.usageError).toBe(usageLoadErrorCopy());
});

test('loadAccountSettings names malformed GET subscription Flutter load-error', async () => {
  const backend = backendFor(request => {
    if (request.path === '/v1/users/profile') {
      return {
        status: 200,
        body: JSON.stringify({uid: 'user-1', email: 'ada@example.test'}),
      };
    }
    if (request.path === '/v1/users/me/subscription') {
      return {status: 200, body: '{'};
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
    return {status: 404, body: null};
  });
  const snapshot = await loadAccountSettings(backend);
  expect(snapshot.subscription).toBeNull();
  expect(snapshot.subscriptionError).toBe(subscriptionLoadErrorCopy());
  expect(snapshot.profile).toEqual(
    expect.objectContaining({uid: 'user-1', email: 'ada@example.test'}),
  );
});

test('loadAccountSettings names Flutter UsagePage fromJson invalid GET available_plans', async () => {
  const backend = backendFor(request => {
    if (request.path === '/v1/users/profile') {
      return {
        status: 200,
        body: JSON.stringify({uid: 'user-1', email: 'ada@example.test'}),
      };
    }
    if (request.path === '/v1/users/me/subscription') {
      return {
        status: 200,
        body: JSON.stringify({
          insights_gained_limit: 0,
          insights_gained_used: 0,
          transcription_seconds_limit: 0,
          transcription_seconds_used: 0,
          words_transcribed_limit: 0,
          words_transcribed_used: 0,
          available_plans: [{title: 'Plus'}],
          subscription: {plan: 'basic', status: 'active'},
        }),
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
    return {status: 404, body: null};
  });
  const snapshot = await loadAccountSettings(backend);
  expect(snapshot.subscription).toBeNull();
  expect(snapshot.subscriptionError).toBe(subscriptionLoadErrorCopy());
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
        body: JSON.stringify({
          insights_gained_limit: 0,
          insights_gained_used: 0,
          transcription_seconds_limit: 0,
          transcription_seconds_used: 0,
          words_transcribed_limit: 0,
          words_transcribed_used: 0,
          subscription: {plan: 'plus', status: 'active'},
        }),
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
  expect(() =>
    parseCloudUsage(
      {
        today: {
          transcription_seconds: 90,
          speech_seconds: 'bad',
        },
      },
      'Usage',
    ),
  ).toThrow('Usage speech_seconds is malformed');
  expect(() =>
    parseCloudUsage(
      {
        today: {transcription_seconds: 90},
        monthly: {transcription_seconds: '12.5'},
      },
      'Usage',
    ),
  ).toThrow('Usage monthly transcription_seconds is malformed');
  expect(() =>
    parseCloudUsage(
      {
        today: {transcription_seconds: 90},
        history: [{date: 1}],
      },
      'Usage',
    ),
  ).toThrow('Usage history[0] date is malformed');
  expect(
    parseCloudUsage(
      {
        today: {
          transcription_seconds: 90,
          speech_seconds: 99,
        },
        monthly: {
          transcription_seconds: 180,
          speech_seconds: 0,
        },
        history: [{date: '', speech_seconds: '0'}],
      },
      'Usage',
    ),
  ).toEqual({
    transcriptionSeconds: 90,
    wordsTranscribed: 0,
    insightsGained: 0,
    memoriesCreated: 0,
  });
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
        body: JSON.stringify({
          insights_gained_limit: 0,
          insights_gained_used: 0,
          transcription_seconds_limit: 0,
          transcription_seconds_used: 0,
          words_transcribed_limit: 0,
          words_transcribed_used: 0,
          subscription: {plan: 'plus', status: 'active'},
        }),
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

test('names Flutter LanguageSettingsPage empty GET available-language names instead of omitting them', () => {
  expect(
    parseCloudLanguageNames(
      {
        languages: [
          {code: 'fr', name: ''},
          {code: 'de', name: ' \t'},
          {code: 'it', name: '\u0085'},
          {code: 'en', name: 'English'},
        ],
      },
      'Languages',
    ),
  ).toEqual([
    {code: 'fr', name: ''},
    {code: 'de', name: ' \t'},
    {code: 'it', name: '\u0085'},
    {code: 'en', name: 'English'},
  ]);
  expect(() =>
    parseCloudLanguageNames(
      {languages: [{code: 'en', name: 1}]},
      'Languages',
    ),
  ).toThrow('Languages languages[0] is malformed');
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
