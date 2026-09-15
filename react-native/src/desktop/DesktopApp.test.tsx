import {readFileSync} from 'node:fs';
import {resolve} from 'node:path';
import React from 'react';
import ReactTestRenderer, {act} from 'react-test-renderer';
import {ScrollView, Text, TextInput} from 'react-native';
import {DesktopApp} from './DesktopApp';
import {TaskPagination} from '../ui/TaskPagination';
import {
  chatDaySummaryCopy,
  chatBlockUnavailableCopy,
  chatDiscoveryShowMoreCopy,
  chatDiscoveryShowLessCopy,
  dailySummaryDefaultHeadlineCopy,
  dailySummaryDescriptionCopy,
  desktopAccountSettingUnavailableCopy,
  desktopAppsUnavailableCopy,
  desktopBackendConfigurationCopy,
  desktopBackendServiceCopy,
  desktopBackendUnavailableCopy,
  developerKeyCreatedCopy,
  desktopReadErrorCopy,
  appsEmptyCopy,
  tasksEmptyCopy,
  signOutTitleCopy,
  fairUseLoadErrorCopy,
  usageLoadErrorCopy,
  subscriptionLoadErrorCopy,
  primaryLanguageNotSetCopy,
  taskIntegrationsFooterCopy,
  integrationsFooterCopy,
} from '../desktopReadClient';
import {appChangelogsLoadErrorCopy} from '../legacyOmiAppChangelogs';

jest.mock('../app/useReduceMotion', () => ({
  useReduceMotion: () => true,
}));

jest.mock('../omiNative', () => ({
  omiBackend: {request: jest.fn()},
}));

jest.mock('./ShippingPressable', () => {
  const ReactModule = require('react');
  const {FocusPressable} = require('../ui/Pressable');
  return {
    ShippingPressable: ({
      children,
      ...props
    }: React.ComponentProps<typeof FocusPressable>) =>
      ReactModule.createElement(FocusPressable, props, children),
  };
});

jest.mock('./ShippingStage', () => {
  const ReactModule = require('react');
  const {View} = require('react-native');
  return {
    ShippingGlassMount: ({
      children,
      style,
    }: {
      children?: React.ReactNode;
      style?: object;
    }) => ReactModule.createElement(View, {style}, children),
    ShippingListInsert: ({children}: {children?: React.ReactNode}) =>
      ReactModule.createElement(View, null, children),
    ShippingSearchFocus: ({
      children,
      style,
    }: {
      children?: React.ReactNode;
      style?: object;
    }) => ReactModule.createElement(View, {style}, children),
    ShippingStage: ({
      children,
      style,
    }: {
      children?: React.ReactNode;
      style?: object;
    }) => ReactModule.createElement(View, {style}, children),
  };
});

jest.mock('../desktopSettingsClient', () => {
  const actual = jest.requireActual(
    '../desktopSettingsClient',
  ) as typeof import('../desktopSettingsClient');
  const prefs = {
    audioMode: 'off',
    floatingBar: true,
    fontScale: 100,
    interfaceSounds: true,
    meetingNoteScreenshots: true,
    notificationsEnabled: false,
    openOmiShortcut: true,
    pushToTalk: true,
    rewindRetentionDays: 14,
    screenCapture: false,
    softwarePlane: 'old',
    stampedV5Origin: null,
    transcriptionAutoDetect: true,
    vadGate: true,
  };
  return {
    ...actual,
    defaultDesktopPreferences: () => prefs,
    loadDesktopPreferences: jest.fn(async () => prefs),
    loadPermissionStatus: jest.fn(async () => ({
      microphone: 'unknown',
      notifications: 'unknown',
      screen: 'unknown',
    })),
    requestDesktopPermission: jest.fn(async () => 'unknown'),
    setDesktopPreference: jest.fn(async () => prefs),
  };
});

jest.mock('../desktopCloudClient', () => ({
  cloudErrorCanRetry: (error: unknown) =>
    !(
      error instanceof Error &&
      'retryable' in error &&
      (error as {retryable?: unknown}).retryable === false
    ),
  loadAccountSettings: jest.fn(async () => {
    throw new Error('unused');
  }),
  loadConnectors: jest.fn(async () => ({
    apps: [],
    enabledError: null,
    enabledIds: [],
    ownerUid: null,
    ownerError: null,
  })),
  enableCloudApp: jest.fn(async () => undefined),
  disableCloudApp: jest.fn(async () => undefined),
  optInTrainingData: jest.fn(),
  setPrivateCloudSync: jest.fn(),
  setStoreRecordingPermission: jest.fn(),
}));

const outcomes = {
  conversations: {
    status: 'success' as const,
    value: {
      items: [
        {
          kind: 'conversation' as const,
          id: 'conversation-1',
          title: 'Product review',
          summary: 'Reviewed the current desktop direction.',
          searchableText: 'product review current desktop direction',
          createdAt: '2026-08-30T10:00:00.000Z',
          updatedAt: '2026-08-30T10:10:00.000Z',
          startedAt: '2026-08-30T10:00:00.000Z',
          finishedAt: '2026-08-30T10:10:00.000Z',
          starred: false,
          status: 'completed',
          source: 'desktop',
          visibility: 'private' as const,
          folderId: null,
          locked: false,
          discarded: false,
        },
      ],
      page: {
        windowStatus: 'complete' as const,
        complete: true,
        hasMore: false,
        nextCursor: null,
        completenessStatus: 'complete' as const,
        reasons: [],
      },
    },
  },
  memories: {
    status: 'success' as const,
    value: {
      items: [],
      page: {
        windowStatus: 'complete' as const,
        complete: true,
        hasMore: false,
        nextCursor: null,
        completenessStatus: 'complete' as const,
        reasons: [],
      },
    },
  },
  tasks: {
    status: 'success' as const,
    value: {
      accountEpoch: null,
      items: [
        {
          kind: 'task' as const,
          id: 'task-1',
          title: 'Ship the desktop chrome',
          summary: 'Finish the Home stage.',
          searchableText: 'ship the desktop chrome finish the home stage',
          completed: false,
          completedAt: null,
          dueAt: null,
          owner: null,
          source: 'desktop',
          provenance: [],
          sortOrder: 0,
          indentLevel: 0,
          createdAt: 1756540800,
          updatedAt: 1756540800,
          revision: null,
        },
      ],
      page: {
        windowStatus: 'complete' as const,
        complete: true,
        hasMore: false,
        nextCursor: null,
        completenessStatus: 'complete' as const,
        reasons: [],
      },
    },
  },
};

function renderedText(renderer: ReactTestRenderer.ReactTestRenderer): string {
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

function visibleButtonCopy(
  renderer: ReactTestRenderer.ReactTestRenderer,
  accessibilityLabel: string,
): string[] {
  return renderer.root
    .find(node => node.props.accessibilityLabel === accessibilityLabel)
    .findAllByType(Text)
    .flatMap(node =>
      Array.isArray(node.props.children)
        ? node.props.children
        : [node.props.children],
    )
    .filter((value): value is string => typeof value === 'string');
}

function pressText(
  renderer: ReactTestRenderer.ReactTestRenderer,
  label: string,
) {
  let node: ReactTestRenderer.ReactTestInstance | null = renderer.root.find(
    candidate => candidate.type === Text && candidate.props.children === label,
  );
  while (node !== null && typeof node.props.onPress !== 'function') {
    node = node.parent;
  }
  if (node === null) {
    throw new Error(`No pressable contains ${label}`);
  }
  node.props.onPress();
}

const renderers: ReactTestRenderer.ReactTestRenderer[] = [];

afterEach(() => {
  act(() => {
    renderers.splice(0).forEach(renderer => renderer.unmount());
  });
  const {omiBackend} = jest.requireMock('../omiNative') as {
    omiBackend: {request: jest.Mock};
  };
  omiBackend.request.mockReset();
});

function renderDesktop(
  overrides: Partial<React.ComponentProps<typeof DesktopApp>> = {},
) {
  let renderer: ReactTestRenderer.ReactTestRenderer;
  act(() => {
    renderer = ReactTestRenderer.create(
      <DesktopApp
        activeGenerationId={null}
        authError={null}
        chatBusy={false}
        chatError={null}
        draft=""
        hasOlderChat={false}
        loadingOlderChat={false}
        messages={[]}
        onDraftChange={jest.fn()}
        onLoadOlderChat={jest.fn()}
        onRefresh={jest.fn()}
        onSend={jest.fn()}
        onSignIn={jest.fn()}
        onSignOut={jest.fn()}
        onStop={jest.fn()}
        outcomes={outcomes}
        reads={[
          ...outcomes.conversations.value.items,
          ...outcomes.tasks.value.items,
        ]}
        readsPhase="ready"
        session="ready"
        signingIn={false}
        {...overrides}
      />,
    );
  });
  renderers.push(renderer!);
  return renderer!;
}

test('renders the shipping search-first desktop hierarchy', () => {
  const renderer = renderDesktop();
  const tree = renderedText(renderer);
  const placeholders = renderer.root
    .findAllByType(TextInput)
    .map(node => node.props.placeholder);
  expect(placeholders).toContain("Search what you've seen and heard…");
  expect(placeholders).not.toContain('Ask a follow-up…');
  expect(tree).toContain('Home');
  expect(tree).toContain('Conversations');
  expect(tree).toContain('Tasks');
  expect(tree).toContain('Apps');
  expect(tree).toContain('Product review');
  expect(tree).toContain('Ship the desktop chrome');
  expect(tree).not.toContain("I'm ready.");
  expect(tree).not.toContain('Saved data unavailable');
  expect(tree).not.toContain('Omi disconnected');
  expect(tree).not.toContain('Devices');
  expect(tree).not.toContain('Your day is clear');
  expect(renderer.root.findAllByType(ScrollView).length).toBeGreaterThan(0);
});

test('desktop Tasks names GET exported platforms and Home previews omit them', () => {
  const exportedTask = {
    ...outcomes.tasks.value.items[0],
    id: 'task-exported',
    title: 'Call Sam',
    searchableText: 'Call Sam',
    exportCopy: 'Exported to Todoist',
  };
  const plainTask = {
    ...outcomes.tasks.value.items[0],
    id: 'task-plain',
    title: 'Write recap',
    searchableText: 'Write recap',
  };
  const renderer = renderDesktop({
    outcomes: {
      ...outcomes,
      tasks: {
        ...outcomes.tasks,
        value: {
          ...outcomes.tasks.value,
          items: [exportedTask, plainTask],
        },
      },
    },
    reads: [...outcomes.conversations.value.items, exportedTask, plainTask],
  });
  const home = renderedText(renderer);
  expect(home).toContain('Call Sam');
  expect(home).toContain('Write recap');
  expect(home).not.toContain('Exported to Todoist');
  act(() => {
    renderer.root
      .find(node => node.props.accessibilityLabel === 'Tasks')
      .props.onPress();
  });
  const tasks = renderedText(renderer);
  expect(tasks).toContain('Exported to Todoist');
  expect(tasks).toContain('Call Sam');
  expect(tasks).toContain('Write recap');
});

test('Home conversation rows name starred conversations without an empty star toggle', () => {
  const renderer = renderDesktop({
    outcomes: {
      ...outcomes,
      conversations: {
        ...outcomes.conversations,
        value: {
          ...outcomes.conversations.value,
          items: outcomes.conversations.value.items.map(item => ({
            ...item,
            starred: true,
          })),
        },
      },
    },
    reads: outcomes.conversations.value.items.map(item => ({
      ...item,
      starred: true,
    })),
  });
  const tree = renderedText(renderer);
  expect(tree).toContain('★');
  expect(tree).not.toContain('Starred');
  expect(tree).not.toContain('☆');
  expect(
    renderer.root.findAll(
      node => node.props.accessibilityLabel === 'Not starred',
    ),
  ).toHaveLength(0);
});

test('Home conversation rows open shared Conversations details', () => {
  const renderer = renderDesktop();
  act(() => {
    renderer.root
      .find(
        node =>
          node.props.accessibilityLabel === 'Open conversation Product review',
      )
      .props.onPress();
  });
  expect(
    renderer.root.find(
      node => node.props.accessibilityLabel === 'Selected conversation details',
    ),
  ).toBeDefined();
  expect(renderedText(renderer)).toContain('Product review');
  act(() => {
    renderer.root
      .find(node => node.props.accessibilityLabel === 'Back to conversations')
      .props.onPress();
  });
  expect(
    renderer.root.find(
      node =>
        node.props.accessibilityLabel === 'Open conversation Product review',
    ),
  ).toBeDefined();
});

test('Home task rows complete through shared mutation callbacks', () => {
  const onTaskToggle = jest.fn();
  const renderer = renderDesktop({
    writesAvailable: true,
    onTaskToggle,
    outcomes: {
      ...outcomes,
      tasks: {
        ...outcomes.tasks,
        value: {
          ...outcomes.tasks.value,
          apiContract: 'omi' as const,
        },
      },
    },
  });
  const toggle = renderer.root.find(
    node =>
      node.props.accessibilityLabel ===
      'Complete task: Ship the desktop chrome',
  );
  expect(toggle.props.accessibilityRole).toBe('checkbox');
  expect(toggle.props.disabled).toBe(false);
  act(() => {
    toggle.props.onPress();
  });
  expect(onTaskToggle).toHaveBeenCalledWith('task-1');
  expect(
    renderer.root.findAll(
      node =>
        node.props.accessibilityLabel === 'Edit task: Ship the desktop chrome',
    ),
  ).toHaveLength(0);
});

test('Home canonical tasks without revisions stay disabled', () => {
  const renderer = renderDesktop({
    writesAvailable: true,
    onTaskToggle: jest.fn(),
  });
  expect(
    renderer.root.find(
      node =>
        node.props.accessibilityLabel ===
        'Complete task: Ship the desktop chrome',
    ).props.disabled,
  ).toBe(true);
});

test('Home canonical tasks with revisions complete through shared mutation callbacks', () => {
  const onTaskToggle = jest.fn();
  const renderer = renderDesktop({
    writesAvailable: true,
    onTaskToggle,
    outcomes: {
      ...outcomes,
      tasks: {
        ...outcomes.tasks,
        value: {
          ...outcomes.tasks.value,
          items: outcomes.tasks.value.items.map(item => ({
            ...item,
            revision: 'a'.repeat(64),
          })),
        },
      },
    },
  });
  const toggle = renderer.root.find(
    node =>
      node.props.accessibilityLabel ===
      'Complete task: Ship the desktop chrome',
  );
  expect(toggle.props.disabled).toBe(false);
  act(() => {
    toggle.props.onPress();
  });
  expect(onTaskToggle).toHaveBeenCalledWith('task-1');
});

test('Home reports a closed write door without labeling tasks Complete', () => {
  const renderer = renderDesktop({writesAvailable: false});
  expect(renderedText(renderer)).toContain(
    'Task editing is unavailable for this connection.',
  );
  expect(
    renderer.root.find(
      node => node.props.accessibilityLabel === 'Task: Ship the desktop chrome',
    ).props.disabled,
  ).toBe(true);
  expect(
    renderer.root.findAll(
      node =>
        node.props.accessibilityLabel ===
        'Complete task: Ship the desktop chrome',
    ),
  ).toHaveLength(0);
});

test('Home memory rows stay display-only', () => {
  const memory = {
    kind: 'memory' as const,
    id: 'memory-1',
    title: 'A remembered fact',
    summary: 'A remembered fact',
    searchableText: 'a remembered fact',
    citations: [],
    timestamp: 1756540800,
    provenance: {
      label: null,
      synthesisVersion: null,
      inputDigest: null,
      outputDigest: null,
    },
  };
  const renderer = renderDesktop({
    outcomes: {
      ...outcomes,
      memories: {
        status: 'success',
        value: {
          items: [memory],
          page: outcomes.memories.value.page,
        },
      },
    },
    reads: [...outcomes.conversations.value.items, memory],
  });
  expect(
    renderer.root.find(
      node =>
        node.props.accessibilityLabel === 'Open conversation Product review',
    ),
  ).toBeDefined();
  expect(
    renderer.root.findAll(node =>
      `${node.props.accessibilityLabel ?? ''}`.startsWith('Open memory'),
    ),
  ).toHaveLength(0);
  expect(renderedText(renderer)).toContain('A remembered fact');
});

test('omnibar send uses the existing chat send path', () => {
  const onSend = jest.fn();
  const onDraftChange = jest.fn();
  const renderer = renderDesktop({
    draft: 'What did we decide?',
    onDraftChange,
    onSend,
  });
  const omnibar = renderer.root
    .findAllByType(TextInput)
    .find(
      node => node.props.placeholder === "Search what you've seen and heard…",
    );
  expect(omnibar).toBeDefined();
  expect(omnibar!.props.value).toBe('What did we decide?');
  act(() => {
    omnibar!.props.onChangeText('Follow up');
  });
  expect(onDraftChange).toHaveBeenCalledWith('Follow up');
  act(() => {
    omnibar!.props.onSubmitEditing();
  });
  expect(onSend).toHaveBeenCalled();
  act(() => {
    renderer.root
      .find(node => node.props.accessibilityLabel === 'Send')
      .props.onPress();
  });
  expect(onSend).toHaveBeenCalledTimes(2);
});

test('sending from another page returns to Home and an active response can stop', async () => {
  const onSend = jest.fn();
  const onStop = jest.fn();
  const renderer = renderDesktop({
    draft: 'What did we decide?',
    onSend,
    onStop,
  });
  act(() => {
    renderer.root
      .find(node => node.props.accessibilityLabel === 'Tasks')
      .props.onPress();
  });
  expect(renderedText(renderer)).not.toContain('Screen history');
  act(() => {
    renderer.root
      .find(node => node.props.accessibilityLabel === 'Send')
      .props.onPress();
  });
  expect(onSend).toHaveBeenCalledTimes(1);
  expect(renderedText(renderer)).toContain('Screen history');

  await act(async () => {
    renderer.update(
      <DesktopApp
        activeGenerationId="generation-1"
        authError={null}
        chatBusy
        chatError={null}
        draft=""
        hasOlderChat={false}
        loadingOlderChat={false}
        messages={[]}
        onDraftChange={jest.fn()}
        onLoadOlderChat={jest.fn()}
        onRefresh={jest.fn()}
        onSend={onSend}
        onSignIn={jest.fn()}
        onSignOut={jest.fn()}
        onStop={onStop}
        outcomes={outcomes}
        reads={[]}
        readsPhase="ready"
        session="ready"
        signingIn={false}
      />,
    );
  });
  act(() => {
    renderer.root
      .find(node => node.props.accessibilityLabel === 'Stop')
      .props.onPress();
  });
  expect(onStop).toHaveBeenCalledTimes(1);
  expect(onSend).toHaveBeenCalledTimes(1);
});

test('desktop chat renders a truthful failed terminal state', () => {
  const renderer = renderDesktop({
    messages: [
      {
        id: 'failed-1',
        text: '',
        sender: 'ai',
        createdAt: Date.parse('2026-09-07T12:00:00.000Z'),
        generationOutcome: 'failed',
        generationRetryable: true,
      },
    ],
  });
  expect(renderedText(renderer)).toContain('Response failed. Try again.');
  expect(
    renderer.root.findAll(
      node => node.props.accessibilityLabel === 'Failed response',
    ),
  ).not.toHaveLength(0);
});

test('desktop chat treats a cancelled whitespace-only reply as Response stopped', () => {
  const renderer = renderDesktop({
    messages: [
      {
        id: 'cancelled-whitespace',
        text: ' \t\n',
        sender: 'ai',
        createdAt: Date.parse('2026-09-07T12:00:00.000Z'),
        generationOutcome: 'cancelled',
      },
    ],
  });
  const copy = renderedText(renderer);
  expect(copy).toContain('Response stopped.');
  expect(copy).not.toContain(' \t\n');
});

test('desktop chat keeps Response stopped when a cancelled reply already has text', () => {
  const renderer = renderDesktop({
    messages: [
      {
        id: 'cancelled-partial',
        text: 'Partial answer',
        sender: 'ai',
        createdAt: Date.parse('2026-09-07T12:00:00.000Z'),
        generationOutcome: 'cancelled',
      },
    ],
  });
  const copy = renderedText(renderer);
  expect(copy).toContain('Partial answer');
  expect(copy).toContain('Response stopped');
});

test('desktop chat names GET day_summary instead of a normal Omi turn', () => {
  const renderer = renderDesktop({
    messages: [
      {
        id: 'summary-1',
        text: 'Yesterday you captured two meetings.',
        sender: 'ai',
        type: 'day_summary',
        createdAt: Date.parse('2026-09-07T12:00:00.000Z'),
        generationOutcome: 'completed',
      },
    ],
  });
  const copy = renderedText(renderer);
  expect(copy).toContain(
    chatDaySummaryCopy(
      'day_summary',
      Date.parse('2026-09-07T12:00:00.000Z'),
    ),
  );
  expect(copy).not.toContain('📅');
  expect(copy).toContain('1. Yesterday you captured two meetings');
  expect(copy).not.toContain('Yesterday you captured two meetings.');
  expect(copy).not.toContain('day_summary');
});

test('desktop chat names Flutter ChartMessageWidget empty GET title without omitting the chart', () => {
  const renderer = renderDesktop({
    messages: [
      {
        id: 'empty-chart-title',
        text: 'Here is the trend.',
        sender: 'ai',
        createdAt: Date.parse('2026-09-07T12:00:00.000Z'),
        generationOutcome: 'completed',
        chart: {
          title: '',
          points: [
            {label: 'Mon', value: 12},
            {label: ' \t', value: 1},
          ],
        },
      },
    ],
  });
  const copy = renderedText(renderer);
  expect(copy).toContain('Here is the trend.');
  expect(copy).toContain('\nMon · 12\n · 1');
  expect(copy).not.toContain('Here is the trend.\nMon · 12');
});

test('desktop chat names GET memory citations with empty titles', () => {
  const renderer = renderDesktop({
    messages: [
      {
        id: 'empty-cited-1',
        text: 'I found that meeting.',
        sender: 'ai',
        createdAt: Date.parse('2026-09-07T12:00:00.000Z'),
        generationOutcome: 'completed',
        memories: [
          {title: '', emoji: '🧠'},
          {title: '  '},
          {title: '\u0085', emoji: '🚀'},
        ],
      },
    ],
  });
  const copy = renderedText(renderer);
  expect(copy).toContain('I found that meeting.');
  expect(copy).toContain('🧠 ');
  expect(copy).toContain('🚀 ');
  expect(copy).not.toContain('\u0085');
});

test('desktop chat names Flutter TaskCardBlock empty GET descriptions', () => {
  const emptyTask = {
    ...outcomes.tasks.value.items[0],
    id: 'task-join',
    title: '',
    searchableText: '',
  };
  const renderer = renderDesktop({
    outcomes: {
      ...outcomes,
      tasks: {
        ...outcomes.tasks,
        value: {
          ...outcomes.tasks.value,
          items: [emptyTask],
        },
      },
    },
    reads: [...outcomes.conversations.value.items, emptyTask],
    messages: [
      {
        id: 'empty-task-desc',
        text: 'Here is what I found.',
        sender: 'ai',
        createdAt: Date.parse('2026-09-07T12:00:00.000Z'),
        generationOutcome: 'completed',
        contentBlocks: [{eyebrow: 'Task', taskId: 'task-join'}],
      },
    ],
  });
  expect(
    renderer.root.findAll(
      node =>
        node.props.accessibilityLabel === 'Task: ' &&
        node.findAll(
          child =>
            String(child.type) === 'Text' && child.props.children === 'Task',
        ).length > 0 &&
        node.findAll(
          child =>
            String(child.type) === 'Text' && child.props.children === '',
        ).length > 0,
    ).length,
  ).toBeGreaterThan(0);
  const copy = renderedText(renderer);
  expect(copy).toContain('Task');
  expect(copy).not.toContain(chatBlockUnavailableCopy());
  expect(copy).not.toContain('Loading');
  expect(copy).not.toContain('task-join');
});

test('desktop chat names GET content_blocks without inventing write actions', () => {
  const renderer = renderDesktop({
    messages: [
      {
        id: 'blocks-1',
        text: 'Here is what I found.',
        sender: 'ai',
        createdAt: Date.parse('2026-09-07T12:00:00.000Z'),
        generationOutcome: 'completed',
        appName: 'Notes',
        appImage: 'https://cdn.example.test/notes.png',
        memories: [{title: 'Morning standup', emoji: '🚀'}],
        evidence: [{title: 'Calendar', detail: 'Tuesday agenda'}],
        contentBlocks: [
          {
            eyebrow: 'Discovery',
            title: 'Quiet mornings',
            detail: 'You like a slow start.',
          },
          {eyebrow: 'Memory', title: 'Prefers concise notes'},
          {eyebrow: 'Task', taskId: 'task-join'},
        ],
      },
    ],
  });
  const copy = renderedText(renderer);
  expect(copy).toContain('Here is what I found.');
  expect(copy).toContain('Notes');
  expect(copy).toContain('🚀 Morning standup');
  expect(copy).toContain('Calendar');
  expect(copy).toContain('Tuesday agenda');
  expect(copy).toContain('Discovery');
  expect(copy).toContain('Quiet mornings');
  expect(copy).toContain('You like a slow start.');
  expect(copy).toContain('Prefers concise notes');
  expect(copy).toContain('Task');
  expect(copy).toContain(chatBlockUnavailableCopy());
  expect(copy).not.toContain('task-join');
  expect(copy).not.toContain('Loading');
  expect(copy).not.toContain('Open in Memories');
  expect(copy).not.toContain('Open conversation');
  expect(copy).not.toContain('Open in Goals');
  expect(copy).not.toContain('Show more');
  expect(
    renderer.root.findAll(
      node => node.props.source?.uri === 'https://cdn.example.test/notes.png',
    ).length,
  ).toBeGreaterThan(0);
  const humanOnly = renderDesktop({
    messages: [
      {
        id: 'human-only',
        text: 'Save this.',
        sender: 'human',
        createdAt: Date.parse('2026-09-07T12:01:00.000Z'),
        generationOutcome: null,
        appName: 'Notes',
        appImage: 'https://cdn.example.test/notes.png',
        contentBlocks: [{eyebrow: 'Discovery', title: 'Quiet mornings'}],
      },
    ],
  });
  const humanCopy = renderedText(humanOnly);
  expect(humanCopy).toContain('Save this.');
  expect(humanCopy).not.toContain('Notes');
  expect(humanCopy).not.toContain('Discovery');
  expect(humanCopy).not.toContain('Quiet mornings');
  expect(
    humanOnly.root.findAll(
      node => node.props.source?.uri === 'https://cdn.example.test/notes.png',
    ),
  ).toHaveLength(0);
});

test('desktop chat names GET goal_link loaded-list miss No longer available', () => {
  const renderer = renderDesktop({
    goals: [{id: 'other'}],
    messages: [
      {
        id: 'goal-miss',
        text: 'Here is what I found.',
        sender: 'ai',
        createdAt: Date.parse('2026-09-07T12:00:00.000Z'),
        generationOutcome: 'completed',
        contentBlocks: [
          {eyebrow: 'Goal', title: 'Ship the recap', goalId: 'goal-join'},
        ],
      },
    ],
  });
  const copy = renderedText(renderer);
  expect(copy).toContain('Goal');
  expect(copy).toContain(chatBlockUnavailableCopy());
  expect(copy).not.toContain('Ship the recap');
  expect(copy).not.toContain('goal-join');
  expect(copy).not.toContain('Loading');
  expect(copy).not.toContain('Open in Goals');
  const hit = renderDesktop({
    goals: [{id: 'goal-join'}],
    messages: [
      {
        id: 'goal-hit',
        text: 'Here is what I found.',
        sender: 'ai',
        createdAt: Date.parse('2026-09-07T12:00:00.000Z'),
        generationOutcome: 'completed',
        contentBlocks: [
          {eyebrow: 'Goal', title: 'Ship the recap', goalId: 'goal-join'},
        ],
      },
    ],
  });
  const hitCopy = renderedText(hit);
  expect(hitCopy).toContain('Goal');
  expect(hitCopy).toContain('Ship the recap');
  expect(hitCopy).not.toContain(chatBlockUnavailableCopy());
  expect(hitCopy).not.toContain('goal-join');
  expect(hitCopy).not.toContain('Open in Goals');
});

test('desktop chat names GET memory_link loaded-list miss No longer available', () => {
  const renderer = renderDesktop({
    messages: [
      {
        id: 'memory-miss',
        text: 'Here is what I found.',
        sender: 'ai',
        createdAt: Date.parse('2026-09-07T12:00:00.000Z'),
        generationOutcome: 'completed',
        contentBlocks: [
          {
            eyebrow: 'Memory',
            title: 'Prefers concise notes',
            memoryId: 'mem-join',
          },
        ],
      },
    ],
  });
  const copy = renderedText(renderer);
  expect(copy).toContain('Memory');
  expect(copy).toContain(chatBlockUnavailableCopy());
  expect(copy).not.toContain('Prefers concise notes');
  expect(copy).not.toContain('mem-join');
  expect(copy).not.toContain('Loading');
  expect(copy).not.toContain('Open in Memories');
  const hit = renderDesktop({
    outcomes: {
      ...outcomes,
      memories: {
        status: 'success',
        value: {
          items: [
            {
              kind: 'memory',
              id: 'mem-join',
              title: 'Prefers concise notes',
              summary: 'Prefers concise notes',
              searchableText: 'prefers concise notes',
              citations: [],
              timestamp: null,
              provenance: {
                label: null,
                synthesisVersion: null,
                inputDigest: null,
                outputDigest: null,
              },
            },
          ],
          page: outcomes.memories.value.page,
        },
      },
    },
    messages: [
      {
        id: 'memory-hit',
        text: 'Here is what I found.',
        sender: 'ai',
        createdAt: Date.parse('2026-09-07T12:00:00.000Z'),
        generationOutcome: 'completed',
        contentBlocks: [
          {
            eyebrow: 'Memory',
            title: 'Prefers concise notes',
            memoryId: 'mem-join',
          },
        ],
      },
    ],
  });
  const hitCopy = renderedText(hit);
  expect(hitCopy).toContain('Memory');
  expect(hitCopy).toContain('Prefers concise notes');
  expect(hitCopy).not.toContain(chatBlockUnavailableCopy());
  expect(hitCopy).not.toContain('mem-join');
  expect(hitCopy).not.toContain('Open in Memories');
});

test('desktop chat names GET discovery fullText Show more without a write', () => {
  const renderer = renderDesktop({
    messages: [
      {
        id: 'discovery-more',
        text: 'Here is what I found.',
        sender: 'ai',
        createdAt: Date.parse('2026-09-07T12:00:00.000Z'),
        generationOutcome: 'completed',
        contentBlocks: [
          {
            eyebrow: 'Discovery',
            title: 'Quiet mornings',
            detail: 'You like a slow start.',
            more: 'Longer body stays collapsed.',
          },
        ],
      },
    ],
  });
  const copy = renderedText(renderer);
  expect(copy).toContain('Discovery');
  expect(copy).toContain('You like a slow start.');
  expect(copy).toContain(chatDiscoveryShowMoreCopy());
  expect(copy).not.toContain('Longer body stays collapsed.');
  expect(copy).not.toContain(chatDiscoveryShowLessCopy());
  const more = renderer.root.find(
    node =>
      node.props.accessibilityLabel === chatDiscoveryShowMoreCopy() &&
      typeof node.props.onPress === 'function',
  );
  act(() => {
    more.props.onPress();
  });
  const expanded = renderedText(renderer);
  expect(expanded).toContain('Longer body stays collapsed.');
  expect(expanded).toContain(chatDiscoveryShowLessCopy());
  expect(expanded).not.toContain(chatDiscoveryShowMoreCopy());
  expect(expanded).not.toContain('You like a slow start.');
});

test('desktop chat names Flutter empty GET chat text', () => {
  const renderer = renderDesktop({
    messages: [
      {
        id: 'human-whitespace',
        text: ' \t\n',
        sender: 'human',
        createdAt: Date.parse('2026-09-07T12:00:00.000Z'),
        generationOutcome: null,
      },
      {
        id: 'completed-whitespace',
        text: ' \t\n',
        sender: 'ai',
        createdAt: Date.parse('2026-09-07T12:00:00.000Z'),
        generationOutcome: 'completed',
      },
    ],
  });
  const copy = renderedText(renderer);
  expect(copy).not.toContain('Message text unavailable');
  expect(copy).toContain('You');
  expect(copy).toContain('Omi');
  expect(copy).not.toContain('Response stopped.');
  expect(copy).not.toContain(' \t\n');
  const emptyBodies = renderer.root.findAll(node => {
    if (String(node.type) !== 'Text') {
      return false;
    }
    const children = node.props.children;
    return (
      children === '' ||
      (Array.isArray(children) && children.some(child => child === ''))
    );
  });
  expect(emptyBodies.length).toBeGreaterThan(0);
});

test('desktop chat names Flutter FilesHandlerWidget empty GET names', () => {
  const renderer = renderDesktop({
    messages: [
      {
        id: 'human-empty-attachment',
        text: '',
        sender: 'human',
        createdAt: Date.parse('2026-09-07T12:00:00.000Z'),
        generationOutcome: 'completed',
        attachments: [
          {
            id: 'att-empty',
            displayName: ' \t\n',
            mediaType: 'text/plain',
            sizeBytes: 0,
          },
        ],
      },
    ],
  });
  const copy = renderedText(renderer);
  expect(copy).toContain('You');
  expect(copy).not.toContain('Attachment name unavailable');
  expect(copy).not.toContain('Size unavailable');
  expect(copy).not.toContain('Message text unavailable');
});

test('a zero macOS Home chat timestamp says Time unavailable instead of omitting the clock', () => {
  const renderer = renderDesktop({
    messages: [
      {
        id: 'undated-1',
        text: 'undated prompt',
        sender: 'human',
        createdAt: 0,
        generationOutcome: null,
      },
    ],
  });
  const copy = renderedText(renderer);
  expect(copy).toContain('undated prompt');
  expect(copy).toContain('Time unavailable');
  expect(copy).not.toContain('1970');
});

test('desktop chat can load earlier messages', () => {
  const onLoadOlderChat = jest.fn();
  const renderer = renderDesktop({hasOlderChat: true, onLoadOlderChat});
  expect(renderedText(renderer)).not.toContain("I'm ready.");
  act(() => {
    renderer.root
      .find(node => node.props.accessibilityLabel === 'Load earlier messages')
      .props.onPress();
  });
  expect(onLoadOlderChat).toHaveBeenCalledTimes(1);
});

test('desktop chat omits Load earlier when the older cursor is empty', () => {
  const onLoadOlderChat = jest.fn();
  const renderer = renderDesktop({
    hasOlderChat: true,
    olderChatAvailable: false,
    onLoadOlderChat,
    messages: [
      {
        id: 'human-1',
        text: 'saved prompt',
        sender: 'human',
        createdAt: Date.parse('2026-09-07T12:00:00.000Z'),
        generationOutcome: null,
      },
    ],
  });
  const copy = renderedText(renderer);
  expect(copy).toContain('saved prompt');
  expect(copy).not.toContain("I'm ready.");
  expect(
    renderer.root.findAll(
      node => node.props.accessibilityLabel === 'Load earlier messages',
    ),
  ).toHaveLength(0);
});

test('signed-out Mac sees only the Welcome, never product chrome', () => {
  const onSignIn = jest.fn();
  const renderer = renderDesktop({
    onSignIn,
    outcomes: null,
    reads: [],
    readsPhase: 'unavailable',
    session: 'signed-out',
  });
  const tree = renderedText(renderer);
  expect(tree).toContain('Welcome to Omi');
  expect(tree).toContain('Sign in');
  expect(tree).toContain('Sign in to access your conversations and memories.');
  // No nav pills, no omnibar, no Home currents, no Settings.
  expect(
    renderer.root.findAllByType(TextInput).map(node => node.props.placeholder),
  ).not.toContain("Search what you've seen and heard…");
  for (const nav of ['Home', 'Conversations', 'Tasks', 'Apps']) {
    expect(
      renderer.root.findAll(node => node.props.accessibilityLabel === nav),
    ).toHaveLength(0);
  }
  expect(
    renderer.root.findAll(node => node.props.accessibilityLabel === 'Settings'),
  ).toHaveLength(0);
  expect(tree).not.toContain('No tasks yet');
  expect(tree).not.toContain('Conversations will show here');
  expect(tree).not.toContain('Screen history');
  expect(tree).not.toContain('Sign in to load conversations and memories.');
  expect(tree).not.toContain('Restoring your session…');
  expect(tree).not.toContain('Saved data unavailable');
  expect(tree).not.toContain('Omi disconnected');
  expect(tree).not.toContain('Devices');
  act(() => {
    renderer.root
      .find(node => node.props.accessibilityLabel === 'Sign in')
      .props.onPress();
  });
  expect(onSignIn).toHaveBeenCalled();
});

test('signed-out Mac shows a safe sign-in failure', () => {
  const renderer = renderDesktop({
    authError: 'Sign in was not completed. Try again.',
    session: 'signed-out',
  });
  expect(renderedText(renderer)).toContain(
    'Sign in was not completed. Try again.',
  );
});

test('the session probe holds an empty window with no product copy', () => {
  const renderer = renderDesktop({
    outcomes: null,
    reads: [],
    readsPhase: 'initial-loading',
    session: 'probing',
  });
  const tree = renderedText(renderer);
  expect(
    renderer.root.findAllByType(TextInput).map(node => node.props.placeholder),
  ).not.toContain("Search what you've seen and heard…");
  for (const nav of ['Home', 'Conversations', 'Tasks', 'Apps', 'Settings']) {
    expect(
      renderer.root.findAll(node => node.props.accessibilityLabel === nav),
    ).toHaveLength(0);
  }
  expect(
    renderer.root.findAll(
      node => node.props.accessibilityLabel === 'Home currents',
    ),
  ).toHaveLength(0);
  expect(
    renderer.root.findAll(
      node => node.props.accessibilityLabel === 'Home tasks',
    ),
  ).toHaveLength(0);
  expect(
    renderer.root.findAll(
      node => node.props.accessibilityLabel === 'First-run onboarding',
    ),
  ).toHaveLength(0);
  expect(tree).not.toContain('Restoring your session…');
  expect(tree).not.toContain('Welcome to Omi');
  expect(tree).not.toContain('Sign in');
  expect(tree).not.toContain('Saved data unavailable');
  expect(renderer.root.findAllByType(Text)).toHaveLength(0);
});

test('keeps an unavailable read as an inline shell state', () => {
  const renderer = renderDesktop({
    outcomes: null,
    reads: [],
    readsPhase: 'unavailable',
  });
  const tree = renderedText(renderer);
  expect(tree).toContain("Some of your history isn't loaded yet.");
  expect(tree).toContain('Try again');
  expect(
    renderer.root.findAllByType(TextInput).map(node => node.props.placeholder),
  ).toContain("Search what you've seen and heard…");
  expect(tree).not.toContain('Saved data unavailable');
  expect(tree).not.toContain('Sign in to Omi cloud');
  expect(tree).not.toContain('Offline · showing what is available on this Mac');
});

test('nested non-retryable library 503s do not offer Try again', () => {
  const unavailable = {
    status: 'error' as const,
    error: desktopBackendUnavailableCopy,
  };
  const renderer = renderDesktop({
    outcomes: {
      conversations: unavailable,
      memories: unavailable,
      tasks: unavailable,
    },
    reads: [],
    readsPhase: 'unavailable',
  });
  const tree = renderedText(renderer);
  expect(tree).toContain(desktopBackendUnavailableCopy);
  expect(tree).not.toContain("Some of your history isn't loaded yet.");
  expect(tree).not.toContain('Try again');
  expect(
    renderer.root.findAll(
      node => node.props.accessibilityLabel === 'Try again',
    ),
  ).toHaveLength(0);
});

test('keeps degraded read state visible away from Home', () => {
  const renderer = renderDesktop({readsPhase: 'saved-but-refresh-failed'});
  act(() => {
    renderer.root
      .find(node => node.props.accessibilityLabel === 'Tasks')
      .props.onPress();
  });
  expect(renderedText(renderer)).toContain(
    "Some of your history isn't loaded yet.",
  );
});

test('reports when a desktop read page is only the first window', () => {
  const renderer = renderDesktop({
    outcomes: {
      ...outcomes,
      conversations: {
        ...outcomes.conversations,
        value: {
          ...outcomes.conversations.value,
          page: {
            ...outcomes.conversations.value.page,
            windowStatus: 'unknown',
            complete: false,
            hasMore: true,
            completenessStatus: 'unknown',
            reasons: ['limit_reached'],
          },
        },
      },
    },
  });
  act(() => {
    renderer.root
      .find(node => node.props.accessibilityLabel === 'Conversations')
      .props.onPress();
  });
  expect(renderedText(renderer)).toContain(
    'Showing the first 50 conversations. More may be available.',
  );
});

test('signed-out first paint shows no chat transport error and no shell', () => {
  const renderer = renderDesktop({
    chatError: 'Chat is temporarily unavailable.',
    outcomes: null,
    reads: [],
    readsPhase: 'unavailable',
    session: 'signed-out',
  });
  const tree = renderedText(renderer);
  expect(tree).toContain('Welcome to Omi');
  expect(tree).not.toContain('Chat is temporarily unavailable.');
  expect(
    renderer.root
      .findAllByType(Text)
      .filter(
        node => node.props.accessibilityLabel === 'Chat transport notice',
      ),
  ).toHaveLength(0);
});

test('ready chat transport error stays in the chrome and off the Home stage', () => {
  const renderer = renderDesktop({
    chatError: 'Chat is temporarily unavailable.',
    session: 'ready',
  });
  const notices = renderer.root
    .findAllByType(Text)
    .filter(node => node.props.accessibilityLabel === 'Chat transport notice');
  expect(notices).toHaveLength(1);
  expect(String(notices[0].props.children)).toBe(
    'Chat is temporarily unavailable.',
  );
  expect(notices[0].props.numberOfLines).toBe(1);
  expect(renderedText(renderer)).toContain('Tasks');
  expect(renderedText(renderer)).toContain('Product review');
  for (const scroll of renderer.root.findAllByType(ScrollView)) {
    expect(
      scroll
        .findAllByType(Text)
        .filter(
          node => node.props.accessibilityLabel === 'Chat transport notice',
        ),
    ).toHaveLength(0);
  }
});

test('an unavailable write door disables Ask instead of leaving it sendable', () => {
  const onSend = jest.fn();
  const renderer = renderDesktop({
    chatError: 'Sending messages is not available on this backend yet.',
    chatSendUnavailable: true,
    onSend,
  });
  const send = renderer.root.find(
    node => node.props.accessibilityLabel === 'Send unavailable',
  );
  expect(send.props.disabled).toBe(true);
  const sendStyle =
    typeof send.props.style === 'function'
      ? send.props.style({pressed: false})
      : send.props.style;
  expect([sendStyle].flat(Infinity)).toEqual(
    expect.arrayContaining([expect.objectContaining({opacity: 0.35})]),
  );
  send.props.onPress();
  expect(onSend).not.toHaveBeenCalled();
  const omnibar = renderer.root
    .findAllByType(TextInput)
    .find(
      node => node.props.placeholder === "Search what you've seen and heard…",
    )!;
  expect(omnibar.props.onSubmitEditing).toBeUndefined();
  const live = renderDesktop({draft: 'What did we decide?'});
  const liveSend = live.root.find(
    node => node.props.accessibilityLabel === 'Send',
  );
  expect(liveSend.props.disabled).toBe(false);
  const liveStyle =
    typeof liveSend.props.style === 'function'
      ? liveSend.props.style({pressed: false})
      : liveSend.props.style;
  expect(JSON.stringify([liveStyle].flat(Infinity))).not.toContain(
    '"opacity":0.35',
  );
});

test('desktop empty Ask is disabled without omitting Search', () => {
  const onSend = jest.fn();
  const renderer = renderDesktop({draft: '   ', onSend});
  const send = renderer.root.find(
    node => node.props.accessibilityLabel === 'Send',
  );
  expect(send.props.disabled).toBe(true);
  expect(renderedText(renderer)).toContain('Ask');
  const sendStyle =
    typeof send.props.style === 'function'
      ? send.props.style({pressed: false})
      : send.props.style;
  expect([sendStyle].flat(Infinity)).toEqual(
    expect.arrayContaining([expect.objectContaining({opacity: 0.35})]),
  );
  send.props.onPress();
  expect(onSend).not.toHaveBeenCalled();
  const omnibar = renderer.root
    .findAllByType(TextInput)
    .find(
      node => node.props.placeholder === "Search what you've seen and heard…",
    )!;
  expect(omnibar.props.editable).not.toBe(false);
  expect(omnibar.props.onSubmitEditing).toBeUndefined();
});

test('desktop NEXT LINE-only Ask is disabled without omitting Search', () => {
  const onSend = jest.fn();
  const renderer = renderDesktop({draft: '\u0085', onSend});
  const send = renderer.root.find(
    node => node.props.accessibilityLabel === 'Send',
  );
  expect(send.props.disabled).toBe(true);
  expect(renderedText(renderer)).toContain('Ask');
  const sendStyle =
    typeof send.props.style === 'function'
      ? send.props.style({pressed: false})
      : send.props.style;
  expect([sendStyle].flat(Infinity)).toEqual(
    expect.arrayContaining([expect.objectContaining({opacity: 0.35})]),
  );
  send.props.onPress();
  expect(onSend).not.toHaveBeenCalled();
  const omnibar = renderer.root
    .findAllByType(TextInput)
    .find(
      node => node.props.placeholder === "Search what you've seen and heard…",
    )!;
  expect(omnibar.props.editable).not.toBe(false);
  expect(omnibar.props.onSubmitEditing).toBeUndefined();
});

test('Settings opens the shipping multi-pane IA including Advanced', async () => {
  const renderer = renderDesktop();
  await act(async () => {
    renderer.root
      .find(node => node.props.accessibilityLabel === 'Settings')
      .props.onPress();
    await Promise.resolve();
  });
  const tree = renderedText(renderer);
  expect(tree).toContain('General');
  expect(tree).toContain('Account & Plan');
  expect(tree).not.toContain('Permissions');
  expect(tree).not.toContain('Floating Bar');
  expect(tree).not.toContain('Shortcuts');
  expect(tree).not.toContain('Font Size');
  expect(tree).not.toContain('Interface Sounds');
  expect(tree).toContain('AI & Automation');
  expect(tree).toContain('Old backend');
  expect(tree).toContain('New backend');
  expect(tree).toContain('Screen Capture');
  expect(tree).toContain('Audio Recording');
  expect(tree).toContain('Off');
  expect(tree).toContain('Always');
  expect(tree).toContain('Meetings');
  expect(tree).toContain('Notifications');
  await act(async () => {
    renderer.root
      .find(node => node.props.accessibilityLabel === 'AI & Automation')
      .props.onPress();
    await Promise.resolve();
  });
  const advanced = renderedText(renderer);
  expect(advanced).toContain('AI & Automation');
  expect(advanced).toContain('Backend');
  expect(advanced).toContain('Old backend');
  expect(advanced).toContain('New backend');
  expect(advanced).not.toContain('workers.dev');
});

test('searches real projections instead of a fake timeline', () => {
  const renderer = renderDesktop({
    draft: 'product',
  });
  const tree = renderedText(renderer);
  expect(tree).toContain('Product review');
  expect(tree).not.toContain('Ship the desktop chrome');
  expect(tree).toContain('No tasks match this search.');
  expect(tree).not.toContain('No tasks yet');
  expect(tree).not.toContain('0 screen moments');
  expect(tree).not.toContain('💬');
  expect(tree).not.toContain('🧠');
});

test('a NEXT LINE-only Home search does not claim a search miss', () => {
  const renderer = renderDesktop({draft: '\u0085'});
  const tree = renderedText(renderer);
  expect(tree).toContain('Product review');
  expect(tree).toContain('Ship the desktop chrome');
  expect(tree).not.toContain('Nothing captured matches this search.');
  expect(tree).not.toContain('No tasks match this search.');
  expect(tree).not.toContain('\u0085');
});

test('Home renders real memories alongside conversations', () => {
  const memory = {
    kind: 'memory' as const,
    id: 'memory-1',
    title: 'Prefers concise release notes',
    summary: 'Release notes should lead with the outcome.',
    searchableText:
      'prefers concise release notes release notes should lead with the outcome',
    citations: [],
    timestamp: 1788492408,
    provenance: {
      label: null,
      synthesisVersion: 'v1',
      inputDigest: 'input',
      outputDigest: 'output',
    },
  };
  const renderer = renderDesktop({
    outcomes: {
      ...outcomes,
      memories: {
        status: 'success',
        value: {...outcomes.memories.value, items: [memory]},
      },
    },
    reads: [...outcomes.conversations.value.items, memory],
  });
  const tree = renderedText(renderer);
  expect(tree).toContain('Conversations & memories');
  expect(tree).toContain('Prefers concise release notes');
  expect(tree).not.toContain('0 citations');
  expect(tree).not.toContain('Synthesized memory');
  expect(tree).not.toMatch(/(^| )Memory( |$)/);
});

test('Home opens the real Rewind destination', async () => {
  const renderer = renderDesktop();
  expect(renderedText(renderer)).toContain('Browse screen history');
  await act(async () => {
    renderer.root
      .find(node => node.props.accessibilityLabel === 'Open Rewind')
      .props.onPress();
    await Promise.resolve();
  });
  expect(
    renderer.root.findAll(
      node => node.props.accessibilityLabel === 'Search screen history',
    ).length,
  ).toBeGreaterThan(0);
  expect(renderedText(renderer)).not.toContain(
    'Screen history is ready when capture is on',
  );
});

const kitFiles = [
  'DesktopApp.tsx',
  'DesktopTopChrome.tsx',
  'DesktopHome.tsx',
  'DesktopPages.tsx',
  'DesktopRows.tsx',
  'DesktopSettings.tsx',
] as const;

const kitSources = Object.fromEntries(
  kitFiles.map(fileName => [
    fileName,
    readFileSync(resolve(__dirname, fileName), 'utf8'),
  ]),
) as Record<(typeof kitFiles)[number], string>;

const allKitSource = kitFiles.map(fileName => kitSources[fileName]).join('\n');

test('desktop lists never use FlatList and the stage stays copy-driven', () => {
  expect(allKitSource).not.toMatch(/\bFlatList\b/);
  expect(allKitSource).toContain('ScrollView');
  expect(allKitSource).not.toContain('function GlassSurface');
  expect(allKitSource).not.toContain("I'm ready.");
  expect(allKitSource).not.toContain('Ask a follow-up');
  expect(allKitSource).toContain('accessibilityLabel="Home currents"');
  expect(allKitSource).toContain('accessibilityLabel="Home tasks"');
  expect(allKitSource).toContain('visibleChatError');
  expect(allKitSource).not.toContain('omnibarError');
});

test('chrome keeps a sliding nav pill, structured home cards, and a field omnibar', () => {
  const chrome = kitSources['DesktopTopChrome.tsx'];
  const app = kitSources['DesktopApp.tsx'];
  const home = kitSources['DesktopHome.tsx'];
  const settings = kitSources['DesktopSettings.tsx'];
  expect(app).toMatch(/root:\s*\{[^}]*padding:\s*desktopWindowInset/);
  expect(chrome).toContain('height: desktopNavBarHeight');
  expect(chrome).toContain('width: desktopTrafficLightRowWidth');
  expect(chrome).toContain('styles.navPill');
  expect(chrome).toContain("active={route === 'Settings'}");
  expect(chrome).toMatch(
    /omnibarInput:\s*\{[^}]*textAlignVertical:\s*'center'/,
  );
  expect(chrome).toMatch(/omnibarInput:\s*\{[^}]*paddingVertical:\s*10/);
  expect(chrome).not.toMatch(/navItem:\s*\{[^}]*borderRadius/);
  expect(chrome).toMatch(/omnibar:\s*\{[^}]*minWidth:\s*220/);
  expect(home).toMatch(/section:\s*\{[^}]*borderRadius:\s*16/);
  expect(home).not.toMatch(/filterRow:\s*\{/);
  expect(home).toContain('chatScrollRef.current?.scrollToEnd');
  expect(settings).toContain('const PANE_ITEM_GAP = 12');
  expect(settings).toMatch(/paneItem:\s*\{[^}]*alignItems:\s*'flex-start'/);
  expect(settings).toMatch(/paneText:\s*\{[^}]*textAlign:\s*'left'/);
  expect(settings).toMatch(/row:\s*\{[^}]*marginBottom:\s*14/);
  expect(chrome).toMatch(/navItem:\s*\{[^}]*paddingHorizontal:\s*16/);
  expect(chrome).toContain('placed.current');
  expect(chrome).toContain('navFrameMoved');
  expect(chrome).toContain('animating.current');
  expect(chrome).not.toMatch(/navTextActive:\s*\{[^}]*fontWeight/);
  expect(chrome).toMatch(/navText:\s*\{[^}]*fontWeight:\s*'500'/);
  expect(allKitSource).not.toMatch(/composer:\s*\{/);
});

test('failed reads on Library and Tasks never claim an empty product', () => {
  const errorOutcomes = {
    conversations: {
      status: 'error' as const,
      error:
        'The selected Omi service is unavailable. Check the connection, then retry.',
    },
    memories: {
      status: 'error' as const,
      error:
        'The selected Omi service is unavailable. Check the connection, then retry.',
    },
    tasks: {
      status: 'error' as const,
      error: 'Omi cloud needs a signed-in session.',
    },
  };
  const renderer = renderDesktop({
    outcomes: errorOutcomes,
    reads: [],
    readsPhase: 'unavailable',
  });
  let tree = renderedText(renderer);
  expect(tree).toContain('Omi cloud needs a signed-in session.');
  expect(tree).not.toContain('No tasks yet');
  expect(tree).not.toContain('Nothing captured yet.');
  act(() => {
    renderer.root
      .find(node => node.props.accessibilityLabel === 'Conversations')
      .props.onPress();
  });
  tree = renderedText(renderer);
  expect(tree).toContain(
    'The selected Omi service is unavailable. Check the connection, then retry.',
  );
  expect(tree).not.toContain('Nothing captured in this window yet.');
  act(() => {
    renderer.root
      .find(node => node.props.accessibilityLabel === 'Tasks')
      .props.onPress();
  });
  tree = renderedText(renderer);
  expect(tree).toContain('Omi cloud needs a signed-in session.');
  expect(tree).not.toContain('No tasks yet');
  expect(tree).not.toContain(tasksEmptyCopy());
});

test('a successful empty read is the only path to the empty claims', async () => {
  const emptyOutcomes = {
    conversations: {
      status: 'success' as const,
      value: {
        items: [],
        page: {
          windowStatus: 'complete' as const,
          complete: true,
          hasMore: false,
          nextCursor: null,
          completenessStatus: 'complete' as const,
          reasons: [],
        },
      },
    },
    memories: {
      status: 'success' as const,
      value: {
        items: [],
        page: {
          windowStatus: 'complete' as const,
          complete: true,
          hasMore: false,
          nextCursor: null,
          completenessStatus: 'complete' as const,
          reasons: [],
        },
      },
    },
    tasks: {
      status: 'success' as const,
      value: {
        accountEpoch: null,
        items: [],
        page: {
          windowStatus: 'complete' as const,
          complete: true,
          hasMore: false,
          nextCursor: null,
          completenessStatus: 'complete' as const,
          reasons: [],
        },
      },
    },
  };
  const renderer = renderDesktop({
    outcomes: emptyOutcomes,
    reads: [],
    readsPhase: 'ready',
  });
  let tree = renderedText(renderer);
  expect(tree).toContain('Nothing captured yet.');
  expect(tree).toContain('No tasks yet');
  expect(tree).not.toContain(
    'Conversations will show here when your day is loaded.',
  );
  act(() => {
    renderer.root
      .find(node => node.props.accessibilityLabel === 'Tasks')
      .props.onPress();
  });
  tree = renderedText(renderer);
  expect(tree).toContain(tasksEmptyCopy());
  expect(tree).not.toContain('No tasks yet.');
});

test('an incomplete empty read does not claim a complete library', async () => {
  const incompletePage = {
    windowStatus: 'incomplete' as const,
    complete: false,
    hasMore: false,
    nextCursor: null,
    completenessStatus: 'incomplete' as const,
    reasons: ['accepted_work_pending'],
  };
  const incompleteOutcomes = {
    conversations: {
      status: 'success' as const,
      value: {items: [], page: incompletePage},
    },
    memories: {
      status: 'success' as const,
      value: {items: [], page: incompletePage},
    },
    tasks: {
      status: 'success' as const,
      value: {accountEpoch: null, items: [], page: incompletePage},
    },
  };
  const renderer = renderDesktop({
    outcomes: incompleteOutcomes,
    reads: [],
    readsPhase: 'ready',
  });
  let tree = renderedText(renderer);
  expect(tree).toContain('Conversations are incomplete.');
  expect(tree).toContain('Tasks are incomplete.');
  expect(tree).not.toContain('Nothing captured yet.');
  expect(tree).not.toContain('No tasks yet');
  act(() => {
    renderer.root
      .find(node => node.props.accessibilityLabel === 'Conversations')
      .props.onPress();
  });
  tree = renderedText(renderer);
  expect(tree).toContain('Conversations are incomplete.');
  expect(tree).not.toContain('Nothing captured in this window yet.');
  act(() => {
    renderer.root
      .find(node => node.props.accessibilityLabel === 'Tasks')
      .props.onPress();
  });
  tree = renderedText(renderer);
  expect(tree).toContain('Tasks are incomplete.');
  expect(tree).not.toContain('No tasks yet');
  expect(tree).not.toContain(tasksEmptyCopy());
});

test('an incomplete empty search does not claim a complete miss', async () => {
  const incompletePage = {
    windowStatus: 'incomplete' as const,
    complete: false,
    hasMore: false,
    nextCursor: null,
    completenessStatus: 'incomplete' as const,
    reasons: ['accepted_work_pending'],
  };
  const incompleteOutcomes = {
    conversations: {
      status: 'success' as const,
      value: {items: [], page: incompletePage},
    },
    memories: {
      status: 'success' as const,
      value: {items: [], page: incompletePage},
    },
    tasks: {
      status: 'success' as const,
      value: {accountEpoch: null, items: [], page: incompletePage},
    },
  };
  const renderer = renderDesktop({
    draft: 'product',
    outcomes: incompleteOutcomes,
    reads: [],
    readsPhase: 'ready',
  });
  const tree = renderedText(renderer);
  expect(tree).toContain('Conversations are incomplete.');
  expect(tree).toContain('Tasks are incomplete.');
  expect(tree).not.toContain('Nothing captured matches this search.');
  expect(tree).not.toContain('No tasks match this search.');
  expect(tree).not.toContain('Nothing captured yet.');
  expect(tree).not.toContain('No tasks yet');
});

test('a complete empty search may claim a search miss', async () => {
  const completePage = {
    windowStatus: 'complete' as const,
    complete: true,
    hasMore: false,
    nextCursor: null,
    completenessStatus: 'complete' as const,
    reasons: [],
  };
  const emptyOutcomes = {
    conversations: {
      status: 'success' as const,
      value: {items: [], page: completePage},
    },
    memories: {
      status: 'success' as const,
      value: {items: [], page: completePage},
    },
    tasks: {
      status: 'success' as const,
      value: {accountEpoch: null, items: [], page: completePage},
    },
  };
  const renderer = renderDesktop({
    draft: 'product',
    outcomes: emptyOutcomes,
    reads: [],
    readsPhase: 'ready',
  });
  const tree = renderedText(renderer);
  expect(tree).toContain('Nothing captured matches this search.');
  expect(tree).toContain('No tasks match this search.');
  expect(tree).not.toContain('Conversations are incomplete.');
  expect(tree).not.toContain('Tasks are incomplete.');
  expect(tree).not.toContain('Nothing captured yet.');
  expect(tree).not.toContain('No tasks yet');
});

test('unavailable memory coverage does not claim a complete empty home', async () => {
  const completePage = {
    windowStatus: 'complete' as const,
    complete: true,
    hasMore: false,
    nextCursor: null,
    completenessStatus: 'complete' as const,
    reasons: [],
  };
  const renderer = renderDesktop({
    outcomes: {
      conversations: {
        status: 'success' as const,
        value: {items: [], page: completePage},
      },
      memories: {
        status: 'success' as const,
        value: {
          items: [],
          page: {
            windowStatus: 'incomplete' as const,
            complete: false,
            hasMore: false,
            nextCursor: null,
            completenessStatus: 'degraded' as const,
            reasons: ['projection_unavailable'],
          },
        },
      },
      tasks: {
        status: 'success' as const,
        value: {accountEpoch: null, items: [], page: completePage},
      },
    },
    reads: [],
    readsPhase: 'ready',
  });
  const tree = renderedText(renderer);
  expect(tree).toContain('Memories may be temporarily incomplete.');
  expect(tree).toContain('No tasks yet');
  expect(tree).not.toContain('Nothing captured yet.');
});

test('Apps is a wrapped gallery that does not invent catalog entries', async () => {
  const pages = kitSources['DesktopPages.tsx'];
  expect(pages).toMatch(/appGrid:\s*\{[^}]*flexWrap:\s*'wrap'/);
  expect(pages).toMatch(/appSlot:\s*\{[^}]*width:\s*'50%'/);
  expect(pages).not.toMatch(/appCard:\s*\{[^}]*flex:\s*1/);
  expect(pages).toContain('loadConnectors');
  expect(pages).toContain('Not connected');
  const renderer = renderDesktop();
  await act(async () => {
    renderer.root
      .find(node => node.props.accessibilityLabel === 'Apps')
      .props.onPress();
    await Promise.resolve();
  });
  const tree = renderedText(renderer);
  expect(tree).toContain(appsEmptyCopy());
  expect(tree).not.toContain('No apps are available.');
  expect(tree).not.toContain('Calendar');
  expect(tree).not.toContain('ChatGPT');
});

test('Apps reports a catalog failure instead of showing invented data', async () => {
  const {loadConnectors} = jest.requireMock('../desktopCloudClient') as {
    loadConnectors: jest.Mock;
  };
  loadConnectors.mockRejectedValueOnce(new Error('offline'));
  const renderer = renderDesktop();
  await act(async () => {
    renderer.root
      .find(node => node.props.accessibilityLabel === 'Apps')
      .props.onPress();
    await Promise.resolve();
    await Promise.resolve();
  });
  expect(renderedText(renderer)).toContain('Apps could not be loaded.');
  expect(renderedText(renderer)).not.toContain('Google Calendar');
});

test('nested non-retryable Apps catalogue failures do not claim a load blip', async () => {
  const {loadConnectors} = jest.requireMock('../desktopCloudClient') as {
    loadConnectors: jest.Mock;
  };
  loadConnectors.mockRejectedValueOnce(
    Object.assign(new Error(desktopAppsUnavailableCopy), {retryable: false}),
  );
  const renderer = renderDesktop();
  await act(async () => {
    renderer.root
      .find(node => node.props.accessibilityLabel === 'Apps')
      .props.onPress();
    await Promise.resolve();
    await Promise.resolve();
  });
  expect(renderedText(renderer)).toContain(desktopAppsUnavailableCopy);
  expect(renderedText(renderer)).not.toContain('Apps could not be loaded.');
  expect(renderedText(renderer)).not.toContain('Google Calendar');
});

test('nested non-retryable Apps enabled failures do not claim an empty catalogue', async () => {
  const {loadConnectors} = jest.requireMock('../desktopCloudClient') as {
    loadConnectors: jest.Mock;
  };
  loadConnectors.mockResolvedValueOnce({
    apps: [],
    enabledError: desktopAppsUnavailableCopy,
    enabledIds: null,
    ownerUid: null,
    ownerError: null,
  });
  const renderer = renderDesktop();
  await act(async () => {
    renderer.root
      .find(node => node.props.accessibilityLabel === 'Apps')
      .props.onPress();
    await Promise.resolve();
    await Promise.resolve();
  });
  expect(renderedText(renderer)).toContain(desktopAppsUnavailableCopy);
  expect(renderedText(renderer)).not.toContain('No apps are available.');
  expect(renderedText(renderer)).not.toContain(appsEmptyCopy());
});

test('nested non-retryable Apps enabled failures keep catalogue tiles without claiming install status', async () => {
  const {loadConnectors} = jest.requireMock('../desktopCloudClient') as {
    loadConnectors: jest.Mock;
  };
  loadConnectors.mockResolvedValueOnce({
    apps: [
      {
        id: 'catalog-app-1',
        name: 'Owned app',
        description: '',
        category: '',
        author: '',
        enabled: false,
        uid: null,
        private: false,
        official: false,
        installs: 0,
        hasExternalIntegration: false,
        connectedAccounts: [],
      },
    ],
    enabledError: desktopAppsUnavailableCopy,
    enabledIds: null,
    ownerUid: null,
    ownerError: null,
  });
  const renderer = renderDesktop();
  await act(async () => {
    renderer.root
      .find(node => node.props.accessibilityLabel === 'Apps')
      .props.onPress();
    await Promise.resolve();
    await Promise.resolve();
  });
  const tree = renderedText(renderer);
  expect(tree).toContain(desktopAppsUnavailableCopy);
  expect(tree).toContain('Owned app');
  expect(tree).not.toContain('App details unavailable');
  expect(tree).not.toContain('Not connected');
  expect(tree).not.toContain('Installed');
  expect(
    renderer.root.findAll(
      node => node.props.accessibilityLabel === 'Install Owned app',
    ),
  ).toHaveLength(0);
});

test('Apps gallery names Flutter AppListItem empty GET descriptions', async () => {
  const {loadConnectors} = jest.requireMock('../desktopCloudClient') as {
    loadConnectors: jest.Mock;
  };
  loadConnectors.mockResolvedValueOnce({
    apps: [
      {
        id: 'catalog-app-1',
        name: 'Owned app',
        description: '',
        category: '',
        author: '',
        enabled: false,
        uid: null,
        private: false,
        official: false,
        installs: 0,
        hasExternalIntegration: false,
        connectedAccounts: [],
      },
      {
        id: 'catalog-app-2',
        name: 'Whitespace app',
        description: ' \t',
        category: '',
        author: '',
        enabled: false,
        uid: null,
        private: false,
        official: false,
        installs: 0,
        hasExternalIntegration: false,
        connectedAccounts: [],
      },
    ],
    enabledError: null,
    enabledIds: [],
    ownerUid: null,
    ownerError: null,
  });
  const renderer = renderDesktop();
  await act(async () => {
    renderer.root
      .find(node => node.props.accessibilityLabel === 'Apps')
      .props.onPress();
    await Promise.resolve();
    await Promise.resolve();
  });
  const tree = renderedText(renderer);
  expect(tree).toContain('Owned app');
  expect(tree).toContain('Whitespace app');
  expect(tree).not.toContain('App details unavailable');
  const descriptions = renderer.root.findAll(
    node =>
      String(node.type) === 'Text' && node.props.numberOfLines === 2,
  );
  expect(descriptions.map(node => node.props.children)).toEqual(['', '']);
});

test('successful empty Apps enabled reads still report catalogue tiles as not connected', async () => {
  const {loadConnectors} = jest.requireMock('../desktopCloudClient') as {
    loadConnectors: jest.Mock;
  };
  loadConnectors.mockResolvedValueOnce({
    apps: [
      {
        id: 'catalog-app-1',
        name: 'Owned app',
        description: '',
        category: '',
        author: '',
        enabled: false,
        uid: null,
        private: false,
        official: false,
        installs: 0,
        hasExternalIntegration: false,
        connectedAccounts: [],
      },
    ],
    enabledError: null,
    enabledIds: [],
    ownerUid: null,
    ownerError: null,
  });
  const renderer = renderDesktop();
  await act(async () => {
    renderer.root
      .find(node => node.props.accessibilityLabel === 'Apps')
      .props.onPress();
    await Promise.resolve();
    await Promise.resolve();
  });
  const tree = renderedText(renderer);
  expect(tree).toContain('Owned app');
  expect(tree).toContain('Not connected');
  expect(tree).not.toContain('App details unavailable');
  expect(tree).not.toContain(desktopAppsUnavailableCopy);
  expect(
    renderer.root.find(
      node => node.props.accessibilityLabel === 'Install Owned app',
    ),
  ).toBeDefined();
});

test('actual desktop Apps Install uses the existing enable producer', async () => {
  const catalog = {
    apps: [
      {
        id: 'catalog-app-1',
        name: 'Owned app',
        description: '',
        category: '',
        author: '',
        enabled: false,
        uid: null,
        private: false,
        official: false,
        installs: 0,
        hasExternalIntegration: false,
        connectedAccounts: [],
      },
    ],
    enabledError: null,
    enabledIds: [] as string[],
    ownerUid: null,
    ownerError: null,
  };
  const {loadConnectors, enableCloudApp} = jest.requireMock(
    '../desktopCloudClient',
  ) as {
    loadConnectors: jest.Mock;
    enableCloudApp: jest.Mock;
  };
  loadConnectors.mockResolvedValueOnce(catalog).mockResolvedValueOnce({
    ...catalog,
    apps: [{...catalog.apps[0], enabled: true}],
    enabledIds: ['catalog-app-1'],
  });
  const renderer = renderDesktop();
  await act(async () => {
    renderer.root
      .find(node => node.props.accessibilityLabel === 'Apps')
      .props.onPress();
    await Promise.resolve();
    await Promise.resolve();
  });
  await act(async () => {
    renderer.root
      .find(node => node.props.accessibilityLabel === 'Install Owned app')
      .props.onPress();
    await Promise.resolve();
    await Promise.resolve();
  });
  expect(enableCloudApp).toHaveBeenCalledWith(
    expect.objectContaining({request: expect.any(Function)}),
    'catalog-app-1',
  );
  expect(
    renderer.root.find(
      node => node.props.accessibilityLabel === 'Remove Owned app',
    ),
  ).toBeDefined();
  expect(renderedText(renderer)).toContain('Installed');
});

test('nested non-retryable Apps enable writes omit Install', async () => {
  const {loadConnectors, enableCloudApp} = jest.requireMock(
    '../desktopCloudClient',
  ) as {
    loadConnectors: jest.Mock;
    enableCloudApp: jest.Mock;
  };
  loadConnectors.mockResolvedValueOnce({
    apps: [
      {
        id: 'catalog-app-1',
        name: 'Owned app',
        description: '',
        category: '',
        author: '',
        enabled: false,
        uid: null,
        private: false,
        official: false,
        installs: 0,
        hasExternalIntegration: false,
        connectedAccounts: [],
      },
    ],
    enabledError: null,
    enabledIds: [],
    ownerUid: null,
    ownerError: null,
  });
  enableCloudApp.mockRejectedValueOnce(
    Object.assign(new Error(desktopAppsUnavailableCopy), {retryable: false}),
  );
  const renderer = renderDesktop();
  await act(async () => {
    renderer.root
      .find(node => node.props.accessibilityLabel === 'Apps')
      .props.onPress();
    await Promise.resolve();
    await Promise.resolve();
  });
  await act(async () => {
    renderer.root
      .find(node => node.props.accessibilityLabel === 'Install Owned app')
      .props.onPress();
    await Promise.resolve();
    await Promise.resolve();
  });
  const tree = renderedText(renderer);
  expect(tree).toContain(desktopAppsUnavailableCopy);
  expect(tree).toContain('Owned app');
  expect(tree).toContain('Not connected');
  expect(
    renderer.root.findAll(
      node => node.props.accessibilityLabel === 'Install Owned app',
    ),
  ).toHaveLength(0);
});

test('Apps gallery names Flutter empty GET app names', async () => {
  const {loadConnectors} = jest.requireMock('../desktopCloudClient') as {
    loadConnectors: jest.Mock;
  };
  loadConnectors.mockResolvedValueOnce({
    apps: [
      {
        id: 'catalog-app-1',
        name: ' \t\n',
        description: '',
        category: '',
        author: '',
        enabled: false,
        uid: null,
        private: false,
        official: false,
        installs: 0,
        hasExternalIntegration: false,
        connectedAccounts: [],
      },
    ],
    enabledError: null,
    enabledIds: [],
    ownerUid: null,
    ownerError: null,
  });
  const renderer = renderDesktop();
  await act(async () => {
    renderer.root
      .find(node => node.props.accessibilityLabel === 'Apps')
      .props.onPress();
    await Promise.resolve();
    await Promise.resolve();
  });
  const tree = renderedText(renderer);
  expect(tree).not.toContain('App name unavailable');
  expect(tree).not.toContain('App details unavailable');
  expect(tree).toContain('Not connected');
  expect(tree).not.toContain(desktopAppsUnavailableCopy);
});

test('Apps gallery category labels are not raw wire tokens', async () => {
  const {loadConnectors} = jest.requireMock('../desktopCloudClient') as {
    loadConnectors: jest.Mock;
  };
  loadConnectors.mockResolvedValueOnce({
    apps: [
      {
        id: 'catalog-app-1',
        name: 'Catalog fixture app',
        description: '',
        category: 'productivity-and-organization',
        author: '',
        enabled: false,
        uid: null,
        private: false,
        official: false,
        installs: 0,
        hasExternalIntegration: false,
        connectedAccounts: [],
      },
    ],
    enabledError: null,
    enabledIds: [],
    ownerUid: null,
    ownerError: null,
  });
  const renderer = renderDesktop();
  await act(async () => {
    renderer.root
      .find(node => node.props.accessibilityLabel === 'Apps')
      .props.onPress();
    await Promise.resolve();
    await Promise.resolve();
  });
  const tree = renderedText(renderer);
  expect(tree).toContain('Catalog fixture app');
  expect(tree).toContain('Productivity');
  expect(tree).not.toContain('productivity-and-organization');
  expect(tree).not.toContain('Productivity and organization');
});

test('Apps gallery keeps GET description when an author is present', async () => {
  const {loadConnectors} = jest.requireMock('../desktopCloudClient') as {
    loadConnectors: jest.Mock;
  };
  loadConnectors.mockResolvedValueOnce({
    apps: [
      {
        id: 'catalog-app-1',
        name: 'Catalog fixture app',
        description: 'Calendar sync for the workday.',
        category: 'productivity',
        author: 'Omi',
        enabled: false,
        uid: null,
        private: false,
        official: false,
        installs: 0,
        hasExternalIntegration: false,
        connectedAccounts: [],
      },
    ],
    enabledError: null,
    enabledIds: [],
    ownerUid: null,
    ownerError: null,
  });
  const renderer = renderDesktop();
  await act(async () => {
    renderer.root
      .find(node => node.props.accessibilityLabel === 'Apps')
      .props.onPress();
    await Promise.resolve();
    await Promise.resolve();
  });
  const tree = renderedText(renderer);
  expect(tree).toContain('Catalog fixture app');
  expect(tree).toContain('Calendar sync for the workday.');
  expect(tree).toContain('Omi');
  expect(
    renderer.root.findAll(
      node =>
        node.props.numberOfLines === 2 &&
        node.props.children === 'Calendar sync for the workday.',
    ).length,
  ).toBeGreaterThan(0);
  expect(
    renderer.root.findAll(
      node =>
        node.props.numberOfLines === 1 &&
        typeof node.props.children === 'string' &&
        node.props.children.includes('Calendar sync for the workday.'),
    ).length,
  ).toBe(0);
});

test('Apps gallery keeps GET category when an author is present', async () => {
  const {loadConnectors} = jest.requireMock('../desktopCloudClient') as {
    loadConnectors: jest.Mock;
  };
  loadConnectors.mockResolvedValueOnce({
    apps: [
      {
        id: 'catalog-app-1',
        name: 'Catalog fixture app',
        description: 'Calendar sync for the workday.',
        category: 'productivity',
        author: 'Omi',
        enabled: false,
        uid: null,
        private: false,
        official: false,
        installs: 0,
        hasExternalIntegration: false,
        connectedAccounts: [],
      },
    ],
    enabledError: null,
    enabledIds: [],
    ownerUid: null,
    ownerError: null,
  });
  const renderer = renderDesktop();
  await act(async () => {
    renderer.root
      .find(node => node.props.accessibilityLabel === 'Apps')
      .props.onPress();
    await Promise.resolve();
    await Promise.resolve();
  });
  const tree = renderedText(renderer);
  expect(tree).toContain('Productivity · Omi');
  expect(tree).toContain('Calendar sync for the workday.');
  expect(tree).not.toContain('productivity');
});

test('Apps gallery keeps GET private instead of a public-looking catalogue', async () => {
  const {loadConnectors} = jest.requireMock('../desktopCloudClient') as {
    loadConnectors: jest.Mock;
  };
  loadConnectors.mockResolvedValueOnce({
    apps: [
      {
        id: 'catalog-app-private',
        name: 'Owned app',
        description: '',
        category: '',
        author: '',
        enabled: false,
        uid: null,
        private: true,
        official: false,
        installs: 0,
        hasExternalIntegration: false,
        connectedAccounts: [],
      },
      {
        id: 'catalog-app-public',
        name: 'Catalog fixture app',
        description: '',
        category: '',
        author: '',
        enabled: false,
        uid: null,
        private: false,
        official: false,
        installs: 0,
        hasExternalIntegration: false,
        connectedAccounts: [],
      },
    ],
    enabledError: null,
    enabledIds: [],
    ownerUid: null,
    ownerError: null,
  });
  const renderer = renderDesktop();
  await act(async () => {
    renderer.root
      .find(node => node.props.accessibilityLabel === 'Apps')
      .props.onPress();
    await Promise.resolve();
    await Promise.resolve();
  });
  const tree = renderedText(renderer);
  expect(tree).toContain('Owned app');
  expect(
    renderer.root.findAll(node => node.props.children === 'Private').length,
  ).toBeGreaterThan(0);
  expect(tree).toContain('Catalog fixture app');
  expect(tree).not.toContain('Official');
});

test('Apps gallery keeps GET ratings instead of a scoreless catalogue', async () => {
  const {loadConnectors} = jest.requireMock('../desktopCloudClient') as {
    loadConnectors: jest.Mock;
  };
  loadConnectors.mockResolvedValueOnce({
    apps: [
      {
        id: 'catalog-app-rated',
        name: 'Owned app',
        description: '',
        category: '',
        author: '',
        enabled: false,
        uid: null,
        private: false,
        official: false,
        installs: 0,
        ratingAvg: 4.5,
        ratingCount: 12,
        hasExternalIntegration: false,
        connectedAccounts: [],
      },
      {
        id: 'catalog-app-unrated',
        name: 'Catalog fixture app',
        description: '',
        category: '',
        author: '',
        enabled: false,
        uid: null,
        private: false,
        official: false,
        installs: 0,
        ratingAvg: null,
        ratingCount: null,
        hasExternalIntegration: false,
        connectedAccounts: [],
      },
    ],
    enabledError: null,
    enabledIds: [],
    ownerUid: null,
    ownerError: null,
  });
  const renderer = renderDesktop();
  await act(async () => {
    renderer.root
      .find(node => node.props.accessibilityLabel === 'Apps')
      .props.onPress();
    await Promise.resolve();
    await Promise.resolve();
  });
  const tree = renderedText(renderer);
  expect(tree).toContain('Owned app');
  expect(
    renderer.root.findAll(node => node.props.children === '4.5 · 12 ratings')
      .length,
  ).toBeGreaterThan(0);
  expect(tree).not.toContain('4.5 (12)');
  expect(tree).toContain('Catalog fixture app');
  expect(tree).not.toContain('0.0');
  expect(tree).not.toContain('Official');
});

test('Apps gallery keeps GET http images instead of a logo-less catalogue', async () => {
  const {loadConnectors} = jest.requireMock('../desktopCloudClient') as {
    loadConnectors: jest.Mock;
  };
  loadConnectors.mockResolvedValueOnce({
    apps: [
      {
        id: 'catalog-app-imaged',
        name: 'Owned app',
        description: '',
        category: '',
        author: '',
        enabled: false,
        uid: null,
        private: false,
        official: false,
        installs: 0,
        image: 'https://cdn.example.test/app.png',
        hasExternalIntegration: false,
        connectedAccounts: [],
      },
      {
        id: 'catalog-app-relative',
        name: 'Catalog fixture app',
        description: '',
        category: '',
        author: '',
        enabled: false,
        uid: null,
        private: false,
        official: false,
        installs: 0,
        image: '/assets/apps/foo.png',
        hasExternalIntegration: false,
        connectedAccounts: [],
      },
    ],
    enabledError: null,
    enabledIds: [],
    ownerUid: null,
    ownerError: null,
  });
  const renderer = renderDesktop();
  await act(async () => {
    renderer.root
      .find(node => node.props.accessibilityLabel === 'Apps')
      .props.onPress();
    await Promise.resolve();
    await Promise.resolve();
  });
  const tree = renderedText(renderer);
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

test('Settings persists a plane switch before reloading the workspace', async () => {
  const onWorkspaceReload = jest.fn();
  const {setDesktopPreference} = jest.requireMock(
    '../desktopSettingsClient',
  ) as {setDesktopPreference: jest.Mock};
  setDesktopPreference.mockClear();
  const renderer = renderDesktop({onWorkspaceReload});
  await act(async () => {
    renderer.root
      .find(node => node.props.accessibilityLabel === 'Settings')
      .props.onPress();
    await Promise.resolve();
  });
  act(() => {
    renderer.root
      .find(node => node.props.accessibilityLabel === 'AI & Automation')
      .props.onPress();
  });
  await act(async () => {
    pressText(renderer, 'New backend');
    await Promise.resolve();
    await Promise.resolve();
    await Promise.resolve();
  });
  expect(setDesktopPreference).toHaveBeenCalledWith('softwarePlane', 'new');
  expect(onWorkspaceReload).toHaveBeenCalledTimes(1);
});

test('re-selecting the current backend segment does not wipe the workspace', async () => {
  const onWorkspaceReload = jest.fn();
  const {setDesktopPreference} = jest.requireMock(
    '../desktopSettingsClient',
  ) as {setDesktopPreference: jest.Mock};
  setDesktopPreference.mockClear();
  const renderer = renderDesktop({onWorkspaceReload});
  await act(async () => {
    renderer.root
      .find(node => node.props.accessibilityLabel === 'Settings')
      .props.onPress();
    await Promise.resolve();
  });
  act(() => {
    renderer.root
      .find(node => node.props.accessibilityLabel === 'AI & Automation')
      .props.onPress();
  });
  await act(async () => {
    pressText(renderer, 'Old backend');
    await Promise.resolve();
    await Promise.resolve();
    await Promise.resolve();
  });
  expect(setDesktopPreference).not.toHaveBeenCalled();
  expect(onWorkspaceReload).not.toHaveBeenCalled();
});

test('Settings disables backend switching while admission is pending', async () => {
  const renderer = renderDesktop({chatBusy: true});
  await act(async () => {
    renderer.root
      .find(node => node.props.accessibilityLabel === 'Settings')
      .props.onPress();
    await Promise.resolve();
  });
  act(() => {
    renderer.root
      .find(node => node.props.accessibilityLabel === 'AI & Automation')
      .props.onPress();
  });
  expect(renderedText(renderer)).toContain(
    'Stop the active response before switching backends.',
  );
  for (const option of ['New backend', 'Old backend']) {
    expect(
      renderer.root.find(
        node =>
          node.props.accessibilityRole === 'button' &&
          node.props.accessibilityState?.disabled === true &&
          node.findAllByType(Text).some(text => text.props.children === option),
      ),
    ).toBeDefined();
  }
});

test('Settings surfaces a failed mutation and does not reload the workspace', async () => {
  const onWorkspaceReload = jest.fn();
  const {setDesktopPreference} = jest.requireMock(
    '../desktopSettingsClient',
  ) as {setDesktopPreference: jest.Mock};
  setDesktopPreference.mockRejectedValueOnce(new Error('write failed'));
  const renderer = renderDesktop({onWorkspaceReload});
  await act(async () => {
    renderer.root
      .find(node => node.props.accessibilityLabel === 'Settings')
      .props.onPress();
    await Promise.resolve();
  });
  act(() => {
    renderer.root
      .find(node => node.props.accessibilityLabel === 'AI & Automation')
      .props.onPress();
  });
  await act(async () => {
    pressText(renderer, 'New backend');
    await Promise.resolve();
    await Promise.resolve();
  });
  expect(renderedText(renderer)).toContain(
    'Settings change could not be saved. Try again.',
  );
  expect(onWorkspaceReload).not.toHaveBeenCalled();
});

test('Settings does not persist audio capture when microphone access is denied', async () => {
  const settings = jest.requireMock('../desktopSettingsClient') as {
    requestDesktopPermission: jest.Mock;
    setDesktopPreference: jest.Mock;
  };
  settings.requestDesktopPermission.mockResolvedValueOnce('denied');
  settings.setDesktopPreference.mockClear();
  const renderer = renderDesktop();
  await act(async () => {
    renderer.root
      .find(node => node.props.accessibilityLabel === 'Settings')
      .props.onPress();
    await Promise.resolve();
  });
  await act(async () => {
    pressText(renderer, 'Always');
    await Promise.resolve();
    await Promise.resolve();
  });
  expect(settings.requestDesktopPermission).toHaveBeenCalledWith('microphone');
  expect(settings.setDesktopPreference).not.toHaveBeenCalledWith(
    'audioMode',
    'always',
  );
  expect(renderedText(renderer)).toContain(
    'Microphone access is denied in System Settings.',
  );
});

test('Settings names denied notification access instead of asking macOS again', async () => {
  const settings = jest.requireMock('../desktopSettingsClient') as {
    loadPermissionStatus: jest.Mock;
  };
  settings.loadPermissionStatus.mockResolvedValueOnce({
    microphone: 'unknown',
    notifications: 'denied',
    screen: 'unknown',
  });
  const renderer = renderDesktop();
  await act(async () => {
    renderer.root
      .find(node => node.props.accessibilityLabel === 'Settings')
      .props.onPress();
    await Promise.resolve();
    await Promise.resolve();
  });
  const tree = renderedText(renderer);
  expect(tree).toContain('Notification access is denied in System Settings.');
  expect(tree).not.toContain('Ask macOS for notification permission.');
});

test('Settings names denied Screen Recording access in System Settings', async () => {
  const settings = jest.requireMock('../desktopSettingsClient') as {
    loadPermissionStatus: jest.Mock;
  };
  settings.loadPermissionStatus.mockResolvedValueOnce({
    microphone: 'unknown',
    notifications: 'unknown',
    screen: 'denied',
  });
  const renderer = renderDesktop();
  await act(async () => {
    renderer.root
      .find(node => node.props.accessibilityLabel === 'Settings')
      .props.onPress();
    await Promise.resolve();
    await Promise.resolve();
  });
  const tree = renderedText(renderer);
  expect(tree).toContain(
    'Screen Recording access is denied in System Settings.',
  );
  expect(tree).not.toContain(
    'Omi needs Screen Recording to keep what you see.',
  );
  expect(tree).toContain('Screen Capture');
});

test('Settings audio recording labels are not raw mode tokens', async () => {
  const settings = jest.requireMock('../desktopSettingsClient') as {
    requestDesktopPermission: jest.Mock;
    setDesktopPreference: jest.Mock;
  };
  settings.requestDesktopPermission.mockResolvedValueOnce('granted');
  settings.setDesktopPreference.mockClear();
  const renderer = renderDesktop();
  await act(async () => {
    renderer.root
      .find(node => node.props.accessibilityLabel === 'Settings')
      .props.onPress();
    await Promise.resolve();
  });
  const tree = renderedText(renderer);
  expect(tree).toContain('Off');
  expect(tree).toContain('Always');
  expect(tree).toContain('Meetings');
  await act(async () => {
    pressText(renderer, 'Always');
    await Promise.resolve();
    await Promise.resolve();
  });
  expect(settings.setDesktopPreference).toHaveBeenCalledWith(
    'audioMode',
    'always',
  );
});

test('Settings Rewind retention does not show 0 as a keep-forever token', async () => {
  const settings = jest.requireMock('../desktopSettingsClient') as {
    setDesktopPreference: jest.Mock;
  };
  settings.setDesktopPreference.mockClear();
  const renderer = renderDesktop();
  await act(async () => {
    renderer.root
      .find(node => node.props.accessibilityLabel === 'Settings')
      .props.onPress();
    await Promise.resolve();
  });
  act(() => {
    renderer.root
      .find(
        node =>
          node.props.accessibilityLabel === 'Rewind' &&
          node.props.accessibilityRole === 'tab',
      )
      .props.onPress();
  });
  const tree = renderedText(renderer);
  expect(tree).toContain('Data Retention');
  expect(tree).toContain('Forever');
  expect(tree).toContain('7');
  expect(tree).toContain('14');
  expect(tree).toContain('30');
  await act(async () => {
    pressText(renderer, 'Forever');
    await Promise.resolve();
    await Promise.resolve();
  });
  expect(settings.setDesktopPreference).toHaveBeenCalledWith(
    'rewindRetentionDays',
    0,
  );
});

test('Settings surfaces sign-out failures without leaving the ready shell', async () => {
  const onSignOut = jest.fn(async () => {
    throw new Error('sign out failed');
  });
  const renderer = renderDesktop({onSignOut});
  await act(async () => {
    renderer.root
      .find(node => node.props.accessibilityLabel === 'Settings')
      .props.onPress();
    await Promise.resolve();
  });
  act(() => {
    renderer.root
      .find(node => node.props.accessibilityLabel === 'Account & Plan')
      .props.onPress();
  });
  await act(async () => {
    renderer.root
      .find(node => node.props.accessibilityLabel === signOutTitleCopy())
      .props.onPress();
    await Promise.resolve();
    await Promise.resolve();
  });
  expect(onSignOut).toHaveBeenCalledTimes(1);
  expect(renderedText(renderer)).toContain('Sign out failed. Try again.');
  expect(renderedText(renderer)).toContain('Account & Plan');
});

test('Settings reports a subscription read failure as unavailable', async () => {
  const {loadAccountSettings} = jest.requireMock('../desktopCloudClient') as {
    loadAccountSettings: jest.Mock;
  };
  loadAccountSettings.mockResolvedValueOnce({
    profile: null,
    profileError: null,
    subscription: null,
    subscriptionError: subscriptionLoadErrorCopy(),
    storeRecordingPermission: null,
    storeRecordingError: null,
    trainingOptedIn: null,
    trainingError: null,
    privateCloudSync: null,
    privateCloudSyncError: null,
    webhooks: null,
    webhooksError: null,
  });
  const renderer = renderDesktop();
  await act(async () => {
    renderer.root
      .find(node => node.props.accessibilityLabel === 'Settings')
      .props.onPress();
    await Promise.resolve();
    await Promise.resolve();
  });
  act(() => {
    renderer.root
      .find(node => node.props.accessibilityLabel === 'Account & Plan')
      .props.onPress();
  });
  expect(renderedText(renderer)).toContain(subscriptionLoadErrorCopy());
  expect(renderedText(renderer)).not.toContain(
    'Plan details load after sign-in.',
  );
});

test('Settings shows already-loaded transcription quota as minutes on Current plan', async () => {
  const {loadAccountSettings} = jest.requireMock('../desktopCloudClient') as {
    loadAccountSettings: jest.Mock;
  };
  loadAccountSettings.mockResolvedValueOnce({
    profile: {
      uid: 'user-1',
      name: 'Ada',
      email: 'ada@example.com',
      company: null,
      job: null,
      dataProtectionLevel: null,
    },
    profileError: null,
    subscription: {
      plan: 'plus',
      status: 'active',
      transcriptionSecondsUsed: 90,
      transcriptionSecondsLimit: 3600,
    },
    subscriptionError: null,
    storeRecordingPermission: null,
    storeRecordingError: null,
    trainingOptedIn: null,
    trainingError: null,
    privateCloudSync: null,
    privateCloudSyncError: null,
    webhooks: null,
    webhooksError: null,
  });
  const renderer = renderDesktop();
  await act(async () => {
    renderer.root
      .find(node => node.props.accessibilityLabel === 'Settings')
      .props.onPress();
    await Promise.resolve();
    await Promise.resolve();
  });
  act(() => {
    renderer.root
      .find(node => node.props.accessibilityLabel === 'Account & Plan')
      .props.onPress();
  });
  expect(renderedText(renderer)).toContain(
    'Plus · Active · 2 of 60 min used this month',
  );
  expect(renderedText(renderer)).not.toContain('Plan is unavailable.');
  expect(renderedText(renderer)).not.toContain('Company');
  expect(renderedText(renderer)).not.toContain('Job');
  expect(renderedText(renderer)).not.toContain('Data protection');
});

test('Settings names GET subscription period quotas without Upgrade', async () => {
  const {loadAccountSettings} = jest.requireMock('../desktopCloudClient') as {
    loadAccountSettings: jest.Mock;
  };
  loadAccountSettings.mockResolvedValueOnce({
    profile: {
      uid: 'user-1',
      name: 'Ada',
      email: 'ada@example.com',
      company: null,
      job: null,
      dataProtectionLevel: null,
    },
    profileError: null,
    subscription: {
      plan: 'basic',
      status: 'active',
      transcriptionSecondsUsed: null,
      transcriptionSecondsLimit: null,
      wordsTranscribedUsed: 12,
      wordsTranscribedLimit: 10000,
      insightsGainedUsed: 3,
      insightsGainedLimit: 500,
      chatQuotaUsed: 5,
      chatQuotaUnit: 'messages',
      chatQuestionsPerMonth: 100,
      chatCostUsdPerMonth: null,
    },
    subscriptionError: null,
    storeRecordingPermission: null,
    storeRecordingError: null,
    trainingOptedIn: null,
    trainingError: null,
    privateCloudSync: null,
    privateCloudSyncError: null,
    webhooks: null,
    webhooksError: null,
    usage: null,
    usageError: null,
    language: null,
    languageError: null,
    languageNames: null,
    languageNamesError: null,
  });
  const renderer = renderDesktop();
  await act(async () => {
    renderer.root
      .find(node => node.props.accessibilityLabel === 'Settings')
      .props.onPress();
    await Promise.resolve();
    await Promise.resolve();
  });
  act(() => {
    renderer.root
      .find(node => node.props.accessibilityLabel === 'Account & Plan')
      .props.onPress();
  });
  const tree = renderedText(renderer);
  expect(tree).toContain('Free Plan');
  expect(tree).not.toContain('Basic');
  expect(tree).toContain('Words this month');
  expect(tree).toContain('12 of 10,000 words used this month');
  expect(tree).toContain('Insights this month');
  expect(tree).toContain('Chat this month');
  expect(tree).toContain('5 Chat');
  expect(tree).toContain('AI chat messages used with Omi this month.');
  expect(tree).toContain('5 of 100 messages used this month');
  expect(tree).not.toContain('Upgrade');
});

test('Settings names Flutter UsagePage empty GET chatQuotaUnit without omitting Chat this month', async () => {
  const {loadAccountSettings} = jest.requireMock('../desktopCloudClient') as {
    loadAccountSettings: jest.Mock;
  };
  loadAccountSettings.mockResolvedValueOnce({
    profile: {
      uid: 'user-1',
      name: 'Ada',
      email: 'ada@example.com',
      company: null,
      job: null,
      dataProtectionLevel: null,
    },
    profileError: null,
    subscription: {
      plan: 'basic',
      status: 'active',
      transcriptionSecondsUsed: null,
      transcriptionSecondsLimit: null,
      wordsTranscribedUsed: null,
      wordsTranscribedLimit: null,
      insightsGainedUsed: null,
      insightsGainedLimit: null,
      chatQuotaUsed: 5,
      chatQuotaUnit: ' \t',
      chatQuestionsPerMonth: 100,
      chatCostUsdPerMonth: null,
    },
    subscriptionError: null,
    storeRecordingPermission: null,
    storeRecordingError: null,
    trainingOptedIn: null,
    trainingError: null,
    privateCloudSync: null,
    privateCloudSyncError: null,
    webhooks: null,
    webhooksError: null,
    usage: null,
    usageError: null,
    language: null,
    languageError: null,
    languageNames: null,
    languageNamesError: null,
  });
  const renderer = renderDesktop();
  await act(async () => {
    renderer.root
      .find(node => node.props.accessibilityLabel === 'Settings')
      .props.onPress();
    await Promise.resolve();
    await Promise.resolve();
  });
  act(() => {
    renderer.root
      .find(node => node.props.accessibilityLabel === 'Account & Plan')
      .props.onPress();
  });
  const tree = renderedText(renderer);
  expect(tree).toContain('Chat this month');
  expect(tree).toContain('5 Chat');
  expect(tree).toContain('AI chat messages used with Omi this month.');
  expect(tree).toContain('5 of 100 messages used this month');
  expect(tree).not.toContain('Upgrade');
});

test('Settings names GET usage today without Upgrade', async () => {
  const {loadAccountSettings} = jest.requireMock('../desktopCloudClient') as {
    loadAccountSettings: jest.Mock;
  };
  loadAccountSettings.mockResolvedValueOnce({
    profile: {
      uid: 'user-1',
      name: 'Ada',
      email: 'ada@example.com',
      company: null,
      job: null,
      dataProtectionLevel: null,
    },
    profileError: null,
    subscription: {
      plan: 'plus',
      status: 'active',
      transcriptionSecondsUsed: 90,
      transcriptionSecondsLimit: 3600,
    },
    subscriptionError: null,
    storeRecordingPermission: null,
    storeRecordingError: null,
    trainingOptedIn: null,
    trainingError: null,
    privateCloudSync: null,
    privateCloudSyncError: null,
    webhooks: null,
    webhooksError: null,
    usage: {
      transcriptionSeconds: 90,
      wordsTranscribed: 12,
      insightsGained: 3,
      memoriesCreated: 1,
    },
    usageError: null,
  });
  const renderer = renderDesktop();
  await act(async () => {
    renderer.root
      .find(node => node.props.accessibilityLabel === 'Settings')
      .props.onPress();
    await Promise.resolve();
    await Promise.resolve();
  });
  act(() => {
    renderer.root
      .find(node => node.props.accessibilityLabel === 'Account & Plan')
      .props.onPress();
  });
  const tree = renderedText(renderer);
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
});

test('Settings names a failed usage today GET instead of empty success', async () => {
  const {loadAccountSettings} = jest.requireMock('../desktopCloudClient') as {
    loadAccountSettings: jest.Mock;
  };
  loadAccountSettings.mockResolvedValueOnce({
    profile: {
      uid: 'user-1',
      name: 'Ada',
      email: 'ada@example.com',
      company: null,
      job: null,
      dataProtectionLevel: null,
    },
    profileError: null,
    subscription: {
      plan: 'plus',
      status: 'active',
      transcriptionSecondsUsed: 90,
      transcriptionSecondsLimit: 3600,
    },
    subscriptionError: null,
    storeRecordingPermission: null,
    storeRecordingError: null,
    trainingOptedIn: null,
    trainingError: null,
    privateCloudSync: null,
    privateCloudSyncError: null,
    webhooks: null,
    webhooksError: null,
    usage: null,
    usageError: usageLoadErrorCopy(),
    language: null,
    languageError: null,
    languageNames: null,
    languageNamesError: null,
  });
  const renderer = renderDesktop();
  await act(async () => {
    renderer.root
      .find(node => node.props.accessibilityLabel === 'Settings')
      .props.onPress();
    await Promise.resolve();
    await Promise.resolve();
  });
  act(() => {
    renderer.root
      .find(node => node.props.accessibilityLabel === 'Account & Plan')
      .props.onPress();
  });
  const tree = renderedText(renderer);
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

test('Settings names GET usage monthly yearly all-time without Upgrade', async () => {
  const {loadAccountSettings} = jest.requireMock('../desktopCloudClient') as {
    loadAccountSettings: jest.Mock;
  };
  const {omiBackend} = jest.requireMock('../omiNative') as {
    omiBackend: {request: jest.Mock};
  };
  loadAccountSettings.mockResolvedValueOnce({
    profile: {
      uid: 'user-1',
      name: 'Ada',
      email: 'ada@example.com',
      company: null,
      job: null,
      dataProtectionLevel: null,
    },
    profileError: null,
    subscription: {
      plan: 'plus',
      status: 'active',
      transcriptionSecondsUsed: null,
      transcriptionSecondsLimit: null,
    },
    subscriptionError: null,
    storeRecordingPermission: null,
    storeRecordingError: null,
    trainingOptedIn: null,
    trainingError: null,
    privateCloudSync: null,
    privateCloudSyncError: null,
    webhooks: null,
    webhooksError: null,
    usage: null,
    usageError: null,
    language: null,
    languageError: null,
    languageNames: null,
    languageNamesError: null,
  });
  omiBackend.request.mockImplementation(async request => {
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
  const renderer = renderDesktop();
  await act(async () => {
    renderer.root
      .find(node => node.props.accessibilityLabel === 'Settings')
      .props.onPress();
    await Promise.resolve();
    await Promise.resolve();
  });
  act(() => {
    renderer.root
      .find(node => node.props.accessibilityLabel === 'Account & Plan')
      .props.onPress();
  });
  const tree = renderedText(renderer);
  expect(tree).toContain('This Month · Listening');
  expect(tree).toContain('3 minutes');
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
  expect(omiBackend.request).toHaveBeenCalledWith({
    id: expect.any(String),
    method: 'GET',
    expectedApiContract: 'omi',
    path: '/v1/users/me/usage?period=monthly',
  });
});

test('Settings names a failed usage period GET instead of empty success', async () => {
  const {loadAccountSettings} = jest.requireMock('../desktopCloudClient') as {
    loadAccountSettings: jest.Mock;
  };
  const {omiBackend} = jest.requireMock('../omiNative') as {
    omiBackend: {request: jest.Mock};
  };
  loadAccountSettings.mockResolvedValueOnce({
    profile: {
      uid: 'user-1',
      name: 'Ada',
      email: 'ada@example.com',
      company: null,
      job: null,
      dataProtectionLevel: null,
    },
    profileError: null,
    subscription: {
      plan: 'plus',
      status: 'active',
      transcriptionSecondsUsed: null,
      transcriptionSecondsLimit: null,
    },
    subscriptionError: null,
    storeRecordingPermission: null,
    storeRecordingError: null,
    trainingOptedIn: null,
    trainingError: null,
    privateCloudSync: null,
    privateCloudSyncError: null,
    webhooks: null,
    webhooksError: null,
    usage: null,
    usageError: null,
    language: null,
    languageError: null,
    languageNames: null,
    languageNamesError: null,
  });
  omiBackend.request.mockImplementation(async request => {
    if (
      typeof request.path === 'string' &&
      request.path.startsWith('/v1/users/me/usage?period=')
    ) {
      throw Object.assign(new Error('lost'), {code: 'OMI_HTTP_TRANSPORT'});
    }
    return {id: request.id, status: 404, body: null};
  });
  const renderer = renderDesktop();
  await act(async () => {
    renderer.root
      .find(node => node.props.accessibilityLabel === 'Settings')
      .props.onPress();
    await Promise.resolve();
    await Promise.resolve();
  });
  act(() => {
    renderer.root
      .find(node => node.props.accessibilityLabel === 'Account & Plan')
      .props.onPress();
  });
  const tree = renderedText(renderer);
  expect(tree).toContain('Ada');
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

test('Settings names malformed usage period GET instead of empty success', async () => {
  const {loadAccountSettings} = jest.requireMock('../desktopCloudClient') as {
    loadAccountSettings: jest.Mock;
  };
  const {omiBackend} = jest.requireMock('../omiNative') as {
    omiBackend: {request: jest.Mock};
  };
  loadAccountSettings.mockResolvedValueOnce({
    profile: {
      uid: 'user-1',
      name: 'Ada',
      email: 'ada@example.com',
      company: null,
      job: null,
      dataProtectionLevel: null,
    },
    profileError: null,
    subscription: {
      plan: 'plus',
      status: 'active',
      transcriptionSecondsUsed: null,
      transcriptionSecondsLimit: null,
    },
    subscriptionError: null,
    storeRecordingPermission: null,
    storeRecordingError: null,
    trainingOptedIn: null,
    trainingError: null,
    privateCloudSync: null,
    privateCloudSyncError: null,
    webhooks: null,
    webhooksError: null,
    usage: null,
    usageError: null,
    language: null,
    languageError: null,
    languageNames: null,
    languageNamesError: null,
  });
  omiBackend.request.mockImplementation(async request => {
    if (
      typeof request.path === 'string' &&
      request.path.startsWith('/v1/users/me/usage?period=')
    ) {
      return {id: request.id, status: 200, body: '{'};
    }
    return {id: request.id, status: 404, body: null};
  });
  const renderer = renderDesktop();
  await act(async () => {
    renderer.root
      .find(node => node.props.accessibilityLabel === 'Settings')
      .props.onPress();
    await Promise.resolve();
    await Promise.resolve();
  });
  act(() => {
    renderer.root
      .find(node => node.props.accessibilityLabel === 'Account & Plan')
      .props.onPress();
  });
  const tree = renderedText(renderer);
  expect(tree).toContain('Ada');
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

test('Settings names HTTP 404 usage period GET Flutter usageLoadError instead of omitting', async () => {
  const {loadAccountSettings} = jest.requireMock('../desktopCloudClient') as {
    loadAccountSettings: jest.Mock;
  };
  const {omiBackend} = jest.requireMock('../omiNative') as {
    omiBackend: {request: jest.Mock};
  };
  loadAccountSettings.mockResolvedValueOnce({
    profile: {
      uid: 'user-1',
      name: 'Ada',
      email: 'ada@example.com',
      company: null,
      job: null,
      dataProtectionLevel: null,
    },
    profileError: null,
    subscription: {
      plan: 'plus',
      status: 'active',
      transcriptionSecondsUsed: null,
      transcriptionSecondsLimit: null,
    },
    subscriptionError: null,
    storeRecordingPermission: null,
    storeRecordingError: null,
    trainingOptedIn: null,
    trainingError: null,
    privateCloudSync: null,
    privateCloudSyncError: null,
    webhooks: null,
    webhooksError: null,
    usage: null,
    usageError: null,
    language: null,
    languageError: null,
    languageNames: null,
    languageNamesError: null,
  });
  omiBackend.request.mockImplementation(async request => {
    if (
      typeof request.path === 'string' &&
      request.path.startsWith('/v1/users/me/usage?period=')
    ) {
      return {id: request.id, status: 404, body: null};
    }
    return {id: request.id, status: 404, body: null};
  });
  const renderer = renderDesktop();
  await act(async () => {
    renderer.root
      .find(node => node.props.accessibilityLabel === 'Settings')
      .props.onPress();
    await Promise.resolve();
    await Promise.resolve();
  });
  act(() => {
    renderer.root
      .find(node => node.props.accessibilityLabel === 'Account & Plan')
      .props.onPress();
  });
  const tree = renderedText(renderer);
  expect(tree).toContain('Ada');
  expect(tree).toContain('This Month');
  expect(tree).toContain('This Year');
  expect(tree).toContain('All Time');
  expect(tree).toContain(usageLoadErrorCopy());
  expect(tree).not.toContain('This Month · Listening');
  expect(tree).not.toContain('No Activity Yet');
  expect(tree).not.toContain('Upgrade');
});

test('Settings names GET primary language without a write sheet', async () => {
  const {loadAccountSettings} = jest.requireMock('../desktopCloudClient') as {
    loadAccountSettings: jest.Mock;
  };
  loadAccountSettings.mockResolvedValueOnce({
    profile: {
      uid: 'user-1',
      name: 'Ada',
      email: 'ada@example.com',
      company: null,
      job: null,
      dataProtectionLevel: null,
    },
    profileError: null,
    subscription: {
      plan: 'plus',
      status: 'active',
      transcriptionSecondsUsed: null,
      transcriptionSecondsLimit: null,
    },
    subscriptionError: null,
    storeRecordingPermission: null,
    storeRecordingError: null,
    trainingOptedIn: null,
    trainingError: null,
    privateCloudSync: null,
    privateCloudSyncError: null,
    webhooks: null,
    webhooksError: null,
    usage: null,
    usageError: null,
    language: 'en',
    languageError: null,
    languageNames: [{code: 'en', name: 'English'}],
    languageNamesError: null,
  });
  const renderer = renderDesktop();
  await act(async () => {
    renderer.root
      .find(node => node.props.accessibilityLabel === 'Settings')
      .props.onPress();
    await Promise.resolve();
    await Promise.resolve();
  });
  act(() => {
    renderer.root
      .find(node => node.props.accessibilityLabel === 'Account & Plan')
      .props.onPress();
  });
  const tree = renderedText(renderer);
  expect(tree).toContain('Primary Language');
  expect(tree).toContain('English');
  expect(tree).not.toContain('Not set');
});

test('Settings names a failed language GET instead of empty success', async () => {
  const {loadAccountSettings} = jest.requireMock('../desktopCloudClient') as {
    loadAccountSettings: jest.Mock;
  };
  loadAccountSettings.mockResolvedValueOnce({
    profile: {
      uid: 'user-1',
      name: 'Ada',
      email: 'ada@example.com',
      company: null,
      job: null,
      dataProtectionLevel: null,
    },
    profileError: null,
    subscription: {
      plan: 'plus',
      status: 'active',
      transcriptionSecondsUsed: null,
      transcriptionSecondsLimit: null,
    },
    subscriptionError: null,
    storeRecordingPermission: null,
    storeRecordingError: null,
    trainingOptedIn: null,
    trainingError: null,
    privateCloudSync: null,
    privateCloudSyncError: null,
    webhooks: null,
    webhooksError: null,
    usage: null,
    usageError: null,
    language: null,
    languageError: desktopBackendServiceCopy,
    languageNames: null,
    languageNamesError: null,
  });
  const renderer = renderDesktop();
  await act(async () => {
    renderer.root
      .find(node => node.props.accessibilityLabel === 'Settings')
      .props.onPress();
    await Promise.resolve();
    await Promise.resolve();
  });
  act(() => {
    renderer.root
      .find(node => node.props.accessibilityLabel === 'Account & Plan')
      .props.onPress();
  });
  const tree = renderedText(renderer);
  expect(tree).toContain('Primary Language');
  expect(tree).toContain(desktopBackendServiceCopy);
  expect(tree).not.toContain('English');
  expect(tree).not.toContain('Not set');
});

test('Settings names Flutter notSet for empty GET language', async () => {
  const {loadAccountSettings} = jest.requireMock('../desktopCloudClient') as {
    loadAccountSettings: jest.Mock;
  };
  loadAccountSettings.mockResolvedValueOnce({
    profile: {
      uid: 'user-1',
      name: 'Ada',
      email: 'ada@example.com',
      company: null,
      job: null,
      dataProtectionLevel: null,
    },
    profileError: null,
    subscription: {
      plan: 'plus',
      status: 'active',
      transcriptionSecondsUsed: null,
      transcriptionSecondsLimit: null,
    },
    subscriptionError: null,
    storeRecordingPermission: null,
    storeRecordingError: null,
    trainingOptedIn: null,
    trainingError: null,
    privateCloudSync: null,
    privateCloudSyncError: null,
    webhooks: null,
    webhooksError: null,
    usage: null,
    usageError: null,
    language: null,
    languageError: null,
    languageNames: [{code: 'en', name: 'English'}],
    languageNamesError: null,
  });
  const renderer = renderDesktop();
  await act(async () => {
    renderer.root
      .find(node => node.props.accessibilityLabel === 'Settings')
      .props.onPress();
    await Promise.resolve();
    await Promise.resolve();
  });
  act(() => {
    renderer.root
      .find(node => node.props.accessibilityLabel === 'Account & Plan')
      .props.onPress();
  });
  const tree = renderedText(renderer);
  expect(tree).toContain('Primary Language');
  expect(tree).toContain('Not set');
  expect(tree).not.toContain('English');
});

test('Settings names GET people without a write sheet', async () => {
  const {loadAccountSettings} = jest.requireMock('../desktopCloudClient') as {
    loadAccountSettings: jest.Mock;
  };
  const {omiBackend} = jest.requireMock('../omiNative') as {
    omiBackend: {request: jest.Mock};
  };
  loadAccountSettings.mockResolvedValueOnce({
    profile: {
      uid: 'user-1',
      name: 'Ada',
      email: 'ada@example.com',
      company: null,
      job: null,
      dataProtectionLevel: null,
    },
    profileError: null,
    subscription: {
      plan: 'plus',
      status: 'active',
      transcriptionSecondsUsed: null,
      transcriptionSecondsLimit: null,
    },
    subscriptionError: null,
    storeRecordingPermission: null,
    storeRecordingError: null,
    trainingOptedIn: null,
    trainingError: null,
    privateCloudSync: null,
    privateCloudSyncError: null,
    webhooks: null,
    webhooksError: null,
    usage: null,
    usageError: null,
    language: null,
    languageError: null,
    languageNames: null,
    languageNamesError: null,
  });
  omiBackend.request.mockImplementation(async request => {
    if (request.path === '/v1/users/people?include_speech_samples=false') {
      return {
        id: request.id,
        status: 200,
        body: JSON.stringify([{id: 'person-alex', name: 'Alex Chen'}]),
      };
    }
    return {id: request.id, status: 404, body: null};
  });
  const renderer = renderDesktop();
  await act(async () => {
    renderer.root
      .find(node => node.props.accessibilityLabel === 'Settings')
      .props.onPress();
    await Promise.resolve();
    await Promise.resolve();
  });
  act(() => {
    renderer.root
      .find(node => node.props.accessibilityLabel === 'Account & Plan')
      .props.onPress();
  });
  const tree = renderedText(renderer);
  expect(tree).toContain('People');
  expect(tree).toContain('Alex Chen');
  expect(tree).not.toContain('person-alex');
  expect(tree).not.toContain(
    'Create a new person and train Omi to recognize their speech too!',
  );
});

test('Settings names a failed people GET instead of empty success', async () => {
  const {loadAccountSettings} = jest.requireMock('../desktopCloudClient') as {
    loadAccountSettings: jest.Mock;
  };
  const {omiBackend} = jest.requireMock('../omiNative') as {
    omiBackend: {request: jest.Mock};
  };
  loadAccountSettings.mockResolvedValueOnce({
    profile: {
      uid: 'user-1',
      name: 'Ada',
      email: 'ada@example.com',
      company: null,
      job: null,
      dataProtectionLevel: null,
    },
    profileError: null,
    subscription: {
      plan: 'plus',
      status: 'active',
      transcriptionSecondsUsed: null,
      transcriptionSecondsLimit: null,
    },
    subscriptionError: null,
    storeRecordingPermission: null,
    storeRecordingError: null,
    trainingOptedIn: null,
    trainingError: null,
    privateCloudSync: null,
    privateCloudSyncError: null,
    webhooks: null,
    webhooksError: null,
    usage: null,
    usageError: null,
    language: null,
    languageError: null,
    languageNames: null,
    languageNamesError: null,
  });
  omiBackend.request.mockImplementation(async request => {
    if (request.path === '/v1/users/people?include_speech_samples=false') {
      throw Object.assign(new Error('lost'), {code: 'OMI_HTTP_TRANSPORT'});
    }
    return {id: request.id, status: 404, body: null};
  });
  const renderer = renderDesktop();
  await act(async () => {
    renderer.root
      .find(node => node.props.accessibilityLabel === 'Settings')
      .props.onPress();
    await Promise.resolve();
    await Promise.resolve();
  });
  act(() => {
    renderer.root
      .find(node => node.props.accessibilityLabel === 'Account & Plan')
      .props.onPress();
  });
  const tree = renderedText(renderer);
  expect(tree).toContain('Ada');
  expect(tree).toContain('People');
  expect(tree).toContain(desktopBackendServiceCopy);
  expect(tree).not.toContain('Alex Chen');
  expect(tree).not.toContain('person-alex');
  expect(tree).not.toContain(
    'Create a new person and train Omi to recognize their speech too!',
  );
});

test('Settings names Flutter createPersonHint for empty GET people', async () => {
  const {loadAccountSettings} = jest.requireMock('../desktopCloudClient') as {
    loadAccountSettings: jest.Mock;
  };
  const {omiBackend} = jest.requireMock('../omiNative') as {
    omiBackend: {request: jest.Mock};
  };
  loadAccountSettings.mockResolvedValueOnce({
    profile: {
      uid: 'user-1',
      name: 'Ada',
      email: 'ada@example.com',
      company: null,
      job: null,
      dataProtectionLevel: null,
    },
    profileError: null,
    subscription: {
      plan: 'plus',
      status: 'active',
      transcriptionSecondsUsed: null,
      transcriptionSecondsLimit: null,
    },
    subscriptionError: null,
    storeRecordingPermission: null,
    storeRecordingError: null,
    trainingOptedIn: null,
    trainingError: null,
    privateCloudSync: null,
    privateCloudSyncError: null,
    webhooks: null,
    webhooksError: null,
    usage: null,
    usageError: null,
    language: null,
    languageError: null,
    languageNames: null,
    languageNamesError: null,
  });
  omiBackend.request.mockImplementation(async (request: {path?: string}) => {
    if (request.path === '/v1/users/people?include_speech_samples=false') {
      return {id: 'people', status: 200, body: JSON.stringify([])};
    }
    return {id: request.id ?? 'other', status: 404, body: null};
  });
  const renderer = renderDesktop();
  await act(async () => {
    renderer.root
      .find(node => node.props.accessibilityLabel === 'Settings')
      .props.onPress();
    await Promise.resolve();
    await Promise.resolve();
  });
  act(() => {
    renderer.root
      .find(node => node.props.accessibilityLabel === 'Account & Plan')
      .props.onPress();
  });
  const tree = renderedText(renderer);
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
  const {loadAccountSettings} = jest.requireMock('../desktopCloudClient') as {
    loadAccountSettings: jest.Mock;
  };
  const {omiBackend} = jest.requireMock('../omiNative') as {
    omiBackend: {request: jest.Mock};
  };
  loadAccountSettings.mockResolvedValueOnce({
    profile: {
      uid: 'user-1',
      name: 'Ada',
      email: 'ada@example.com',
      company: null,
      job: null,
      dataProtectionLevel: null,
    },
    profileError: null,
    subscription: {
      plan: 'plus',
      status: 'active',
      transcriptionSecondsUsed: null,
      transcriptionSecondsLimit: null,
    },
    subscriptionError: null,
    storeRecordingPermission: null,
    storeRecordingError: null,
    trainingOptedIn: null,
    trainingError: null,
    privateCloudSync: null,
    privateCloudSyncError: null,
    webhooks: null,
    webhooksError: null,
    usage: null,
    usageError: null,
    language: null,
    languageError: null,
    languageNames: null,
    languageNamesError: null,
  });
  omiBackend.request.mockImplementation(async (request: {path?: string}) => ({
    id: request.id ?? 'other',
    status: 404,
    body: null,
  }));
  const renderer = renderDesktop();
  await act(async () => {
    renderer.root
      .find(node => node.props.accessibilityLabel === 'Settings')
      .props.onPress();
    await Promise.resolve();
    await Promise.resolve();
  });
  act(() => {
    renderer.root
      .find(node => node.props.accessibilityLabel === 'Account & Plan')
      .props.onPress();
  });
  const tree = renderedText(renderer);
  expect(tree).not.toContain(
    'Create a new person and train Omi to recognize their speech too!',
  );
});

test('Settings names GET task integrations without Connect or a write sheet', async () => {
  const {loadAccountSettings} = jest.requireMock('../desktopCloudClient') as {
    loadAccountSettings: jest.Mock;
  };
  const {omiBackend} = jest.requireMock('../omiNative') as {
    omiBackend: {request: jest.Mock};
  };
  loadAccountSettings.mockResolvedValueOnce({
    profile: {
      uid: 'user-1',
      name: 'Ada',
      email: 'ada@example.com',
      company: null,
      job: null,
      dataProtectionLevel: null,
    },
    profileError: null,
    subscription: {
      plan: 'plus',
      status: 'active',
      transcriptionSecondsUsed: null,
      transcriptionSecondsLimit: null,
    },
    subscriptionError: null,
    storeRecordingPermission: null,
    storeRecordingError: null,
    trainingOptedIn: null,
    trainingError: null,
    privateCloudSync: null,
    privateCloudSyncError: null,
    webhooks: null,
    webhooksError: null,
    usage: null,
    usageError: null,
    language: null,
    languageError: null,
    languageNames: null,
    languageNamesError: null,
  });
  omiBackend.request.mockImplementation(async request => {
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
  const renderer = renderDesktop();
  await act(async () => {
    renderer.root
      .find(node => node.props.accessibilityLabel === 'Settings')
      .props.onPress();
    await Promise.resolve();
    await Promise.resolve();
  });
  act(() => {
    renderer.root
      .find(node => node.props.accessibilityLabel === 'Account & Plan')
      .props.onPress();
  });
  const tree = renderedText(renderer);
  expect(tree).toContain('Task Integrations');
  expect(tree).toContain('Todoist · Default');
  expect(tree).toContain('ClickUp');
  expect(tree).toContain(taskIntegrationsFooterCopy());
  expect(tree).not.toContain('Asana');
  expect(tree).not.toContain('secret-todoist');
  expect(tree).not.toContain('Coming Soon');
  expect(
    renderer.root.findAll(
      node => node.props.accessibilityLabel === 'Connect',
    ),
  ).toHaveLength(0);
  expect(omiBackend.request).toHaveBeenCalledWith({
    id: expect.any(String),
    method: 'GET',
    expectedApiContract: 'omi',
    path: '/v1/task-integrations',
  });
  expect(
    omiBackend.request.mock.calls.some(call => call[0].method === 'PUT'),
  ).toBe(false);
});

test('Settings names a failed task-integrations GET instead of empty success', async () => {
  const {loadAccountSettings} = jest.requireMock('../desktopCloudClient') as {
    loadAccountSettings: jest.Mock;
  };
  const {omiBackend} = jest.requireMock('../omiNative') as {
    omiBackend: {request: jest.Mock};
  };
  loadAccountSettings.mockResolvedValueOnce({
    profile: {
      uid: 'user-1',
      name: 'Ada',
      email: 'ada@example.com',
      company: null,
      job: null,
      dataProtectionLevel: null,
    },
    profileError: null,
    subscription: {
      plan: 'plus',
      status: 'active',
      transcriptionSecondsUsed: null,
      transcriptionSecondsLimit: null,
    },
    subscriptionError: null,
    storeRecordingPermission: null,
    storeRecordingError: null,
    trainingOptedIn: null,
    trainingError: null,
    privateCloudSync: null,
    privateCloudSyncError: null,
    webhooks: null,
    webhooksError: null,
    usage: null,
    usageError: null,
    language: null,
    languageError: null,
    languageNames: null,
    languageNamesError: null,
  });
  omiBackend.request.mockImplementation(async request => {
    if (request.path === '/v1/task-integrations') {
      throw Object.assign(new Error('lost'), {code: 'OMI_HTTP_TRANSPORT'});
    }
    return {id: request.id, status: 404, body: null};
  });
  const renderer = renderDesktop();
  await act(async () => {
    renderer.root
      .find(node => node.props.accessibilityLabel === 'Settings')
      .props.onPress();
    await Promise.resolve();
    await Promise.resolve();
  });
  act(() => {
    renderer.root
      .find(node => node.props.accessibilityLabel === 'Account & Plan')
      .props.onPress();
  });
  const tree = renderedText(renderer);
  expect(tree).toContain('Ada');
  expect(tree).toContain('Task Integrations');
  expect(tree).toContain(desktopBackendServiceCopy);
  expect(tree).not.toContain('Todoist');
  expect(tree).not.toContain('secret-todoist');
  expect(tree).not.toContain(taskIntegrationsFooterCopy());
  expect(
    renderer.root.findAll(
      node => node.props.accessibilityLabel === 'Connect',
    ),
  ).toHaveLength(0);
});

test('Settings names GET integrations without Connect or a write sheet', async () => {
  const {loadAccountSettings} = jest.requireMock('../desktopCloudClient') as {
    loadAccountSettings: jest.Mock;
  };
  const {omiBackend} = jest.requireMock('../omiNative') as {
    omiBackend: {request: jest.Mock};
  };
  loadAccountSettings.mockResolvedValueOnce({
    profile: {
      uid: 'user-1',
      name: 'Ada',
      email: 'ada@example.com',
      company: null,
      job: null,
      dataProtectionLevel: null,
    },
    profileError: null,
    subscription: {
      plan: 'plus',
      status: 'active',
      transcriptionSecondsUsed: null,
      transcriptionSecondsLimit: null,
    },
    subscriptionError: null,
    storeRecordingPermission: null,
    storeRecordingError: null,
    trainingOptedIn: null,
    trainingError: null,
    privateCloudSync: null,
    privateCloudSyncError: null,
    webhooks: null,
    webhooksError: null,
    usage: null,
    usageError: null,
    language: null,
    languageError: null,
    languageNames: null,
    languageNamesError: null,
  });
  omiBackend.request.mockImplementation(async request => {
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
  const renderer = renderDesktop();
  await act(async () => {
    renderer.root
      .find(node => node.props.accessibilityLabel === 'Settings')
      .props.onPress();
    await Promise.resolve();
    await Promise.resolve();
  });
  act(() => {
    renderer.root
      .find(node => node.props.accessibilityLabel === 'Account & Plan')
      .props.onPress();
  });
  const tree = renderedText(renderer);
  expect(tree).toContain('Integrations');
  expect(tree).toContain('Gmail');
  expect(tree).toContain('Apple Health');
  expect(tree).toContain(integrationsFooterCopy());
  expect(tree).not.toContain('Google Calendar');
  expect(tree).not.toContain('Coming Soon');
  expect(tree).not.toContain('Disconnect');
  expect(tree).not.toContain('Create your own');
  expect(
    renderer.root.findAll(
      node => node.props.accessibilityLabel === 'Connect',
    ),
  ).toHaveLength(0);
  expect(omiBackend.request).toHaveBeenCalledWith({
    id: expect.any(String),
    method: 'GET',
    expectedApiContract: 'omi',
    path: '/v1/integrations/gmail',
  });
  expect(
    omiBackend.request.mock.calls.some(
      call => call[0].method === 'PUT' || call[0].method === 'DELETE',
    ),
  ).toBe(false);
  expect(
    omiBackend.request.mock.calls.some(
      call =>
        typeof call[0].path === 'string' && call[0].path.includes('oauth-url'),
    ),
  ).toBe(false);
});

test('Settings names a failed integrations GET instead of empty success', async () => {
  const {loadAccountSettings} = jest.requireMock('../desktopCloudClient') as {
    loadAccountSettings: jest.Mock;
  };
  const {omiBackend} = jest.requireMock('../omiNative') as {
    omiBackend: {request: jest.Mock};
  };
  loadAccountSettings.mockResolvedValueOnce({
    profile: {
      uid: 'user-1',
      name: 'Ada',
      email: 'ada@example.com',
      company: null,
      job: null,
      dataProtectionLevel: null,
    },
    profileError: null,
    subscription: {
      plan: 'plus',
      status: 'active',
      transcriptionSecondsUsed: null,
      transcriptionSecondsLimit: null,
    },
    subscriptionError: null,
    storeRecordingPermission: null,
    storeRecordingError: null,
    trainingOptedIn: null,
    trainingError: null,
    privateCloudSync: null,
    privateCloudSyncError: null,
    webhooks: null,
    webhooksError: null,
    usage: null,
    usageError: null,
    language: null,
    languageError: null,
    languageNames: null,
    languageNamesError: null,
  });
  omiBackend.request.mockImplementation(async request => {
    if (
      typeof request.path === 'string' &&
      request.path.startsWith('/v1/integrations/')
    ) {
      throw Object.assign(new Error('lost'), {code: 'OMI_HTTP_TRANSPORT'});
    }
    return {id: request.id, status: 404, body: null};
  });
  const renderer = renderDesktop();
  await act(async () => {
    renderer.root
      .find(node => node.props.accessibilityLabel === 'Settings')
      .props.onPress();
    await Promise.resolve();
    await Promise.resolve();
  });
  act(() => {
    renderer.root
      .find(node => node.props.accessibilityLabel === 'Account & Plan')
      .props.onPress();
  });
  const tree = renderedText(renderer);
  expect(tree).toContain('Ada');
  expect(tree).toContain('Integrations');
  expect(tree).toContain(desktopBackendServiceCopy);
  expect(tree).not.toContain('Gmail');
  expect(tree).not.toContain(integrationsFooterCopy());
  expect(
    renderer.root.findAll(
      node => node.props.accessibilityLabel === 'Connect',
    ),
  ).toHaveLength(0);
});

test('Settings names Flutter ChangelogSheet empty GET change titles without omitting What\'s New', async () => {
  const {loadAccountSettings} = jest.requireMock('../desktopCloudClient') as {
    loadAccountSettings: jest.Mock;
  };
  const {omiBackend} = jest.requireMock('../omiNative') as {
    omiBackend: {request: jest.Mock};
  };
  loadAccountSettings.mockResolvedValueOnce({
    profile: {
      uid: 'user-1',
      name: 'Ada',
      email: 'ada@example.com',
      company: null,
      job: null,
      dataProtectionLevel: null,
    },
    profileError: null,
    subscription: {
      plan: 'plus',
      status: 'active',
      transcriptionSecondsUsed: null,
      transcriptionSecondsLimit: null,
    },
    subscriptionError: null,
    storeRecordingPermission: null,
    storeRecordingError: null,
    trainingOptedIn: null,
    trainingError: null,
    privateCloudSync: null,
    privateCloudSyncError: null,
    webhooks: null,
    webhooksError: null,
    usage: null,
    usageError: null,
    language: null,
    languageError: null,
    languageNames: null,
    languageNamesError: null,
  });
  omiBackend.request.mockImplementation(async request => {
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
  const renderer = renderDesktop();
  await act(async () => {
    renderer.root
      .find(node => node.props.accessibilityLabel === 'Settings')
      .props.onPress();
    await Promise.resolve();
    await Promise.resolve();
  });
  act(() => {
    renderer.root
      .find(node => node.props.accessibilityLabel === 'Account & Plan')
      .props.onPress();
  });
  const tree = renderedText(renderer);
  expect(tree).toContain("What's New in 1.2.0");
  expect(tree).toContain('✨ · Hidden empty title.');
  expect(tree).not.toContain('ann-empty');
  expect(tree).not.toContain('Dismiss');
});

test('Settings names Flutter ChangelogSheet empty GET icons without omitting What\'s New', async () => {
  const {loadAccountSettings} = jest.requireMock('../desktopCloudClient') as {
    loadAccountSettings: jest.Mock;
  };
  const {omiBackend} = jest.requireMock('../omiNative') as {
    omiBackend: {request: jest.Mock};
  };
  loadAccountSettings.mockResolvedValueOnce({
    profile: {
      uid: 'user-1',
      name: 'Ada',
      email: 'ada@example.com',
      company: null,
      job: null,
      dataProtectionLevel: null,
    },
    profileError: null,
    subscription: {
      plan: 'plus',
      status: 'active',
      transcriptionSecondsUsed: null,
      transcriptionSecondsLimit: null,
    },
    subscriptionError: null,
    storeRecordingPermission: null,
    storeRecordingError: null,
    trainingOptedIn: null,
    trainingError: null,
    privateCloudSync: null,
    privateCloudSyncError: null,
    webhooks: null,
    webhooksError: null,
    usage: null,
    usageError: null,
    language: null,
    languageError: null,
    languageNames: null,
    languageNamesError: null,
  });
  omiBackend.request.mockImplementation(async request => {
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
  const renderer = renderDesktop();
  await act(async () => {
    renderer.root
      .find(node => node.props.accessibilityLabel === 'Settings')
      .props.onPress();
    await Promise.resolve();
    await Promise.resolve();
  });
  act(() => {
    renderer.root
      .find(node => node.props.accessibilityLabel === 'Account & Plan')
      .props.onPress();
  });
  const tree = renderedText(renderer);
  expect(tree).toContain("What's New in 1.2.0");
  expect(tree).toContain(' · Empty icon · Kept description.');
  expect(tree).toContain(' · Whitespace icon · Kept description.');
  expect(tree).not.toContain('✨ · Empty icon');
  expect(tree).not.toContain('ann-empty-icon');
  expect(tree).not.toContain('Dismiss');
});

test('Settings names GET app changelogs without dismiss', async () => {
  const {loadAccountSettings} = jest.requireMock('../desktopCloudClient') as {
    loadAccountSettings: jest.Mock;
  };
  const {omiBackend} = jest.requireMock('../omiNative') as {
    omiBackend: {request: jest.Mock};
  };
  loadAccountSettings.mockResolvedValueOnce({
    profile: {
      uid: 'user-1',
      name: 'Ada',
      email: 'ada@example.com',
      company: null,
      job: null,
      dataProtectionLevel: null,
    },
    profileError: null,
    subscription: {
      plan: 'plus',
      status: 'active',
      transcriptionSecondsUsed: null,
      transcriptionSecondsLimit: null,
    },
    subscriptionError: null,
    storeRecordingPermission: null,
    storeRecordingError: null,
    trainingOptedIn: null,
    trainingError: null,
    privateCloudSync: null,
    privateCloudSyncError: null,
    webhooks: null,
    webhooksError: null,
    usage: null,
    usageError: null,
    language: null,
    languageError: null,
    languageNames: null,
    languageNamesError: null,
  });
  omiBackend.request.mockImplementation(async request => {
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
  const renderer = renderDesktop();
  await act(async () => {
    renderer.root
      .find(node => node.props.accessibilityLabel === 'Settings')
      .props.onPress();
    await Promise.resolve();
    await Promise.resolve();
  });
  act(() => {
    renderer.root
      .find(node => node.props.accessibilityLabel === 'Account & Plan')
      .props.onPress();
  });
  const tree = renderedText(renderer);
  expect(tree).toContain("What's New in 1.2.0");
  expect(tree).toContain('🚀 · Faster sync · Uploads finish sooner.');
  expect(tree).toContain('✨ · Offline replay · ');
  expect(tree).not.toContain('Release notes');
  expect(tree).not.toContain('ann-1');
  expect(tree).not.toContain('Dismiss');
  expect(omiBackend.request).toHaveBeenCalledWith({
    id: expect.any(String),
    method: 'GET',
    expectedApiContract: 'omi',
    path: '/v1/announcements/changelogs?limit=5',
  });
  expect(
    omiBackend.request.mock.calls.some(
      call => call[0].method === 'POST' || String(call[0].path).includes('dismiss'),
    ),
  ).toBe(false);
});

test('Settings names a failed app changelogs GET instead of empty success', async () => {
  const {loadAccountSettings} = jest.requireMock('../desktopCloudClient') as {
    loadAccountSettings: jest.Mock;
  };
  const {omiBackend} = jest.requireMock('../omiNative') as {
    omiBackend: {request: jest.Mock};
  };
  loadAccountSettings.mockResolvedValueOnce({
    profile: {
      uid: 'user-1',
      name: 'Ada',
      email: 'ada@example.com',
      company: null,
      job: null,
      dataProtectionLevel: null,
    },
    profileError: null,
    subscription: {
      plan: 'plus',
      status: 'active',
      transcriptionSecondsUsed: null,
      transcriptionSecondsLimit: null,
    },
    subscriptionError: null,
    storeRecordingPermission: null,
    storeRecordingError: null,
    trainingOptedIn: null,
    trainingError: null,
    privateCloudSync: null,
    privateCloudSyncError: null,
    webhooks: null,
    webhooksError: null,
    usage: null,
    usageError: null,
    language: null,
    languageError: null,
    languageNames: null,
    languageNamesError: null,
  });
  omiBackend.request.mockImplementation(async request => {
    if (request.path === '/v1/announcements/changelogs?limit=5') {
      throw Object.assign(new Error('lost'), {code: 'OMI_HTTP_TRANSPORT'});
    }
    return {id: request.id, status: 404, body: null};
  });
  const renderer = renderDesktop();
  await act(async () => {
    renderer.root
      .find(node => node.props.accessibilityLabel === 'Settings')
      .props.onPress();
    await Promise.resolve();
    await Promise.resolve();
  });
  act(() => {
    renderer.root
      .find(node => node.props.accessibilityLabel === 'Account & Plan')
      .props.onPress();
  });
  const tree = renderedText(renderer);
  expect(tree).toContain('Ada');
  expect(tree).toContain("What's New");
  expect(tree).toContain(appChangelogsLoadErrorCopy());
  expect(tree).not.toContain(desktopBackendServiceCopy);
  expect(tree).not.toContain("What's New in 1.2.0");
  expect(tree).not.toContain('Dismiss');
  expect(tree).not.toContain('✨');
});

test('Settings names malformed app changelogs GET instead of empty success', async () => {
  const {loadAccountSettings} = jest.requireMock('../desktopCloudClient') as {
    loadAccountSettings: jest.Mock;
  };
  const {omiBackend} = jest.requireMock('../omiNative') as {
    omiBackend: {request: jest.Mock};
  };
  loadAccountSettings.mockResolvedValueOnce({
    profile: {
      uid: 'user-1',
      name: 'Ada',
      email: 'ada@example.com',
      company: null,
      job: null,
      dataProtectionLevel: null,
    },
    profileError: null,
    subscription: {
      plan: 'plus',
      status: 'active',
      transcriptionSecondsUsed: null,
      transcriptionSecondsLimit: null,
    },
    subscriptionError: null,
    storeRecordingPermission: null,
    storeRecordingError: null,
    trainingOptedIn: null,
    trainingError: null,
    privateCloudSync: null,
    privateCloudSyncError: null,
    webhooks: null,
    webhooksError: null,
    usage: null,
    usageError: null,
    language: null,
    languageError: null,
    languageNames: null,
    languageNamesError: null,
  });
  omiBackend.request.mockImplementation(async request => {
    if (request.path === '/v1/announcements/changelogs?limit=5') {
      return {
        id: request.id,
        status: 200,
        body: JSON.stringify({changes: []}),
      };
    }
    return {id: request.id, status: 404, body: null};
  });
  const renderer = renderDesktop();
  await act(async () => {
    renderer.root
      .find(node => node.props.accessibilityLabel === 'Settings')
      .props.onPress();
    await Promise.resolve();
    await Promise.resolve();
  });
  act(() => {
    renderer.root
      .find(node => node.props.accessibilityLabel === 'Account & Plan')
      .props.onPress();
  });
  const tree = renderedText(renderer);
  expect(tree).toContain('Ada');
  expect(tree).toContain("What's New");
  expect(tree).toContain(appChangelogsLoadErrorCopy());
  expect(tree).not.toContain("What's New in 1.2.0");
  expect(tree).not.toContain('Dismiss');
  expect(tree).not.toContain('✨');
});

test('Settings names Flutter ChangelogSheet unknown GET type instead of empty success', async () => {
  const {loadAccountSettings} = jest.requireMock('../desktopCloudClient') as {
    loadAccountSettings: jest.Mock;
  };
  const {omiBackend} = jest.requireMock('../omiNative') as {
    omiBackend: {request: jest.Mock};
  };
  loadAccountSettings.mockResolvedValueOnce({
    profile: {
      uid: 'user-1',
      name: 'Ada',
      email: 'ada@example.com',
      company: null,
      job: null,
      dataProtectionLevel: null,
    },
    profileError: null,
    subscription: {
      plan: 'plus',
      status: 'active',
      transcriptionSecondsUsed: null,
      transcriptionSecondsLimit: null,
    },
    subscriptionError: null,
    storeRecordingPermission: null,
    storeRecordingError: null,
    trainingOptedIn: null,
    trainingError: null,
    privateCloudSync: null,
    privateCloudSyncError: null,
    webhooks: null,
    webhooksError: null,
    usage: null,
    usageError: null,
    language: null,
    languageError: null,
    languageNames: null,
    languageNamesError: null,
  });
  omiBackend.request.mockImplementation(async request => {
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
  const renderer = renderDesktop();
  await act(async () => {
    renderer.root
      .find(node => node.props.accessibilityLabel === 'Settings')
      .props.onPress();
    await Promise.resolve();
    await Promise.resolve();
  });
  act(() => {
    renderer.root
      .find(node => node.props.accessibilityLabel === 'Account & Plan')
      .props.onPress();
  });
  const tree = renderedText(renderer);
  expect(tree).toContain('Ada');
  expect(tree).toContain("What's New");
  expect(tree).toContain(appChangelogsLoadErrorCopy());
  expect(tree).not.toContain("What's New in 1.2.0");
  expect(tree).not.toContain('Offline replay');
  expect(tree).not.toContain('Dismiss');
  expect(tree).not.toContain('✨');
});

test('Settings names Flutter ChangelogSheet fromJson invalid created_at instead of undated success', async () => {
  const {loadAccountSettings} = jest.requireMock('../desktopCloudClient') as {
    loadAccountSettings: jest.Mock;
  };
  const {omiBackend} = jest.requireMock('../omiNative') as {
    omiBackend: {request: jest.Mock};
  };
  loadAccountSettings.mockResolvedValueOnce({
    profile: {
      uid: 'user-1',
      name: 'Ada',
      email: 'ada@example.com',
      company: null,
      job: null,
      dataProtectionLevel: null,
    },
    profileError: null,
    subscription: {
      plan: 'plus',
      status: 'active',
      transcriptionSecondsUsed: null,
      transcriptionSecondsLimit: null,
    },
    subscriptionError: null,
    storeRecordingPermission: null,
    storeRecordingError: null,
    trainingOptedIn: null,
    trainingError: null,
    privateCloudSync: null,
    privateCloudSyncError: null,
    webhooks: null,
    webhooksError: null,
    usage: null,
    usageError: null,
    language: null,
    languageError: null,
    languageNames: null,
    languageNamesError: null,
  });
  omiBackend.request.mockImplementation(async request => {
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
  const renderer = renderDesktop();
  await act(async () => {
    renderer.root
      .find(node => node.props.accessibilityLabel === 'Settings')
      .props.onPress();
    await Promise.resolve();
    await Promise.resolve();
  });
  act(() => {
    renderer.root
      .find(node => node.props.accessibilityLabel === 'Account & Plan')
      .props.onPress();
  });
  const tree = renderedText(renderer);
  expect(tree).toContain('Ada');
  expect(tree).toContain("What's New");
  expect(tree).toContain(appChangelogsLoadErrorCopy());
  expect(tree).not.toContain("What's New in 1.2.0");
  expect(tree).not.toContain('Offline replay');
  expect(tree).not.toContain('Skip me');
  expect(tree).not.toContain('Dismiss');
  expect(tree).not.toContain('✨');
});

test('Settings names Flutter ChangelogSheet fromJson missing GET content instead of empty success', async () => {
  const {loadAccountSettings} = jest.requireMock('../desktopCloudClient') as {
    loadAccountSettings: jest.Mock;
  };
  const {omiBackend} = jest.requireMock('../omiNative') as {
    omiBackend: {request: jest.Mock};
  };
  loadAccountSettings.mockResolvedValueOnce({
    profile: {
      uid: 'user-1',
      name: 'Ada',
      email: 'ada@example.com',
      company: null,
      job: null,
      dataProtectionLevel: null,
    },
    profileError: null,
    subscription: {
      plan: 'plus',
      status: 'active',
      transcriptionSecondsUsed: null,
      transcriptionSecondsLimit: null,
    },
    subscriptionError: null,
    storeRecordingPermission: null,
    storeRecordingError: null,
    trainingOptedIn: null,
    trainingError: null,
    privateCloudSync: null,
    privateCloudSyncError: null,
    webhooks: null,
    webhooksError: null,
    usage: null,
    usageError: null,
    language: null,
    languageError: null,
    languageNames: null,
    languageNamesError: null,
  });
  omiBackend.request.mockImplementation(async request => {
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
  const renderer = renderDesktop();
  await act(async () => {
    renderer.root
      .find(node => node.props.accessibilityLabel === 'Settings')
      .props.onPress();
    await Promise.resolve();
    await Promise.resolve();
  });
  act(() => {
    renderer.root
      .find(node => node.props.accessibilityLabel === 'Account & Plan')
      .props.onPress();
  });
  const tree = renderedText(renderer);
  expect(tree).toContain('Ada');
  expect(tree).toContain("What's New");
  expect(tree).toContain(appChangelogsLoadErrorCopy());
  expect(tree).not.toContain("What's New in 1.2.0");
  expect(tree).not.toContain('Offline replay');
  expect(tree).not.toContain('Dismiss');
  expect(tree).not.toContain('✨');
});

test('Settings names Flutter ChangelogSheet fromJson invalid GET active instead of empty success', async () => {
  const {loadAccountSettings} = jest.requireMock('../desktopCloudClient') as {
    loadAccountSettings: jest.Mock;
  };
  const {omiBackend} = jest.requireMock('../omiNative') as {
    omiBackend: {request: jest.Mock};
  };
  loadAccountSettings.mockResolvedValueOnce({
    profile: {
      uid: 'user-1',
      name: 'Ada',
      email: 'ada@example.com',
      company: null,
      job: null,
      dataProtectionLevel: null,
    },
    profileError: null,
    subscription: {
      plan: 'plus',
      status: 'active',
      transcriptionSecondsUsed: null,
      transcriptionSecondsLimit: null,
    },
    subscriptionError: null,
    storeRecordingPermission: null,
    storeRecordingError: null,
    trainingOptedIn: null,
    trainingError: null,
    privateCloudSync: null,
    privateCloudSyncError: null,
    webhooks: null,
    webhooksError: null,
    usage: null,
    usageError: null,
    language: null,
    languageError: null,
    languageNames: null,
    languageNamesError: null,
  });
  omiBackend.request.mockImplementation(async request => {
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
  const renderer = renderDesktop();
  await act(async () => {
    renderer.root
      .find(node => node.props.accessibilityLabel === 'Settings')
      .props.onPress();
    await Promise.resolve();
    await Promise.resolve();
  });
  act(() => {
    renderer.root
      .find(node => node.props.accessibilityLabel === 'Account & Plan')
      .props.onPress();
  });
  const tree = renderedText(renderer);
  expect(tree).toContain('Ada');
  expect(tree).toContain("What's New");
  expect(tree).toContain(appChangelogsLoadErrorCopy());
  expect(tree).not.toContain("What's New in 1.2.0");
  expect(tree).not.toContain('Offline replay');
  expect(tree).not.toContain('Dismiss');
  expect(tree).not.toContain('✨');
});

test('Settings names Flutter ChangelogSheet fromGenerated unknown GET trigger instead of empty success', async () => {
  const {loadAccountSettings} = jest.requireMock('../desktopCloudClient') as {
    loadAccountSettings: jest.Mock;
  };
  const {omiBackend} = jest.requireMock('../omiNative') as {
    omiBackend: {request: jest.Mock};
  };
  loadAccountSettings.mockResolvedValueOnce({
    profile: {
      uid: 'user-1',
      name: 'Ada',
      email: 'ada@example.com',
      company: null,
      job: null,
      dataProtectionLevel: null,
    },
    profileError: null,
    subscription: {
      plan: 'plus',
      status: 'active',
      transcriptionSecondsUsed: null,
      transcriptionSecondsLimit: null,
    },
    subscriptionError: null,
    storeRecordingPermission: null,
    storeRecordingError: null,
    trainingOptedIn: null,
    trainingError: null,
    privateCloudSync: null,
    privateCloudSyncError: null,
    webhooks: null,
    webhooksError: null,
    usage: null,
    usageError: null,
    language: null,
    languageError: null,
    languageNames: null,
    languageNamesError: null,
  });
  omiBackend.request.mockImplementation(async request => {
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
  const renderer = renderDesktop();
  await act(async () => {
    renderer.root
      .find(node => node.props.accessibilityLabel === 'Settings')
      .props.onPress();
    await Promise.resolve();
    await Promise.resolve();
  });
  act(() => {
    renderer.root
      .find(node => node.props.accessibilityLabel === 'Account & Plan')
      .props.onPress();
  });
  const tree = renderedText(renderer);
  expect(tree).toContain('Ada');
  expect(tree).toContain("What's New");
  expect(tree).toContain(appChangelogsLoadErrorCopy());
  expect(tree).not.toContain("What's New in 1.2.0");
  expect(tree).not.toContain('Offline replay');
  expect(tree).not.toContain('Skip me');
  expect(tree).not.toContain('Dismiss');
  expect(tree).not.toContain('✨');
});

test('Settings names GET fair use without Upgrade or a write sheet', async () => {
  const {loadAccountSettings} = jest.requireMock('../desktopCloudClient') as {
    loadAccountSettings: jest.Mock;
  };
  const {omiBackend} = jest.requireMock('../omiNative') as {
    omiBackend: {request: jest.Mock};
  };
  loadAccountSettings.mockResolvedValueOnce({
    profile: {
      uid: 'user-1',
      name: 'Ada',
      email: 'ada@example.com',
      company: null,
      job: null,
      dataProtectionLevel: null,
    },
    profileError: null,
    subscription: {
      plan: 'plus',
      status: 'active',
      transcriptionSecondsUsed: null,
      transcriptionSecondsLimit: null,
    },
    subscriptionError: null,
    storeRecordingPermission: null,
    storeRecordingError: null,
    trainingOptedIn: null,
    trainingError: null,
    privateCloudSync: null,
    privateCloudSyncError: null,
    webhooks: null,
    webhooksError: null,
    usage: null,
    usageError: null,
    language: null,
    languageError: null,
    languageNames: null,
    languageNamesError: null,
  });
  omiBackend.request.mockImplementation(async request => {
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
  const renderer = renderDesktop();
  await act(async () => {
    renderer.root
      .find(node => node.props.accessibilityLabel === 'Settings')
      .props.onPress();
    await Promise.resolve();
    await Promise.resolve();
  });
  act(() => {
    renderer.root
      .find(node => node.props.accessibilityLabel === 'Account & Plan')
      .props.onPress();
  });
  const tree = renderedText(renderer);
  expect(tree).toContain('Fair Use');
  expect(tree).toContain('Restricted');
  expect(tree).toContain('FU-1');
  expect(tree).toContain('Speech Usage');
  expect(tree).toContain('2.4h / 2h');
  expect(tree).toContain('Daily transcription limit reached');
  expect(tree).toContain('Daily Transcription');
  expect(tree).toMatch(/Resets \d+h/);
  expect(tree).toContain('About Fair Use');
  expect(tree).not.toContain('Upgrade');
});

test('Settings names Flutter FairUsePage whitespace GET message without omitting Fair Use', async () => {
  const {loadAccountSettings} = jest.requireMock('../desktopCloudClient') as {
    loadAccountSettings: jest.Mock;
  };
  const {omiBackend} = jest.requireMock('../omiNative') as {
    omiBackend: {request: jest.Mock};
  };
  loadAccountSettings.mockResolvedValueOnce({
    profile: {
      uid: 'user-1',
      name: 'Ada',
      email: 'ada@example.com',
      company: null,
      job: null,
      dataProtectionLevel: null,
    },
    profileError: null,
    subscription: {
      plan: 'plus',
      status: 'active',
      transcriptionSecondsUsed: null,
      transcriptionSecondsLimit: null,
    },
    subscriptionError: null,
    storeRecordingPermission: null,
    storeRecordingError: null,
    trainingOptedIn: null,
    trainingError: null,
    privateCloudSync: null,
    privateCloudSyncError: null,
    webhooks: null,
    webhooksError: null,
    usage: null,
    usageError: null,
    language: null,
    languageError: null,
    languageNames: null,
    languageNamesError: null,
  });
  omiBackend.request.mockImplementation(async request => {
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
  const renderer = renderDesktop();
  await act(async () => {
    renderer.root
      .find(node => node.props.accessibilityLabel === 'Settings')
      .props.onPress();
    await Promise.resolve();
    await Promise.resolve();
  });
  act(() => {
    renderer.root
      .find(node => node.props.accessibilityLabel === 'Account & Plan')
      .props.onPress();
  });
  const tree = renderedText(renderer);
  expect(
    renderer.root
      .findAllByType(Text)
      .some(node => node.props.children === 'Fair Use'),
  ).toBe(true);
  expect(tree).toContain('Speech Usage');
  expect(tree).toContain('About Fair Use');
  expect(tree).not.toContain('Restricted');
  expect(tree).not.toContain('Upgrade');
});

test('Settings names Flutter FairUsePage whitespace GET caseRef without omitting Fair Use', async () => {
  const {loadAccountSettings} = jest.requireMock('../desktopCloudClient') as {
    loadAccountSettings: jest.Mock;
  };
  const {omiBackend} = jest.requireMock('../omiNative') as {
    omiBackend: {request: jest.Mock};
  };
  loadAccountSettings.mockResolvedValueOnce({
    profile: {
      uid: 'user-1',
      name: 'Ada',
      email: 'ada@example.com',
      company: null,
      job: null,
      dataProtectionLevel: null,
    },
    profileError: null,
    subscription: {
      plan: 'plus',
      status: 'active',
      transcriptionSecondsUsed: null,
      transcriptionSecondsLimit: null,
    },
    subscriptionError: null,
    storeRecordingPermission: null,
    storeRecordingError: null,
    trainingOptedIn: null,
    trainingError: null,
    privateCloudSync: null,
    privateCloudSyncError: null,
    webhooks: null,
    webhooksError: null,
    usage: null,
    usageError: null,
    language: null,
    languageError: null,
    languageNames: null,
    languageNamesError: null,
  });
  omiBackend.request.mockImplementation(async request => {
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
  const renderer = renderDesktop();
  await act(async () => {
    renderer.root
      .find(node => node.props.accessibilityLabel === 'Settings')
      .props.onPress();
    await Promise.resolve();
    await Promise.resolve();
  });
  act(() => {
    renderer.root
      .find(node => node.props.accessibilityLabel === 'Account & Plan')
      .props.onPress();
  });
  const tree = renderedText(renderer);
  expect(tree).toContain('Restricted \u00b7 ');
  expect(tree).toContain('Speech Usage');
  expect(tree).toContain('About Fair Use');
  expect(tree).not.toContain('FU-1');
  expect(tree).not.toContain('Upgrade');
});

test('Settings names a failed fair use GET instead of empty success', async () => {
  const {loadAccountSettings} = jest.requireMock('../desktopCloudClient') as {
    loadAccountSettings: jest.Mock;
  };
  const {omiBackend} = jest.requireMock('../omiNative') as {
    omiBackend: {request: jest.Mock};
  };
  loadAccountSettings.mockResolvedValueOnce({
    profile: {
      uid: 'user-1',
      name: 'Ada',
      email: 'ada@example.com',
      company: null,
      job: null,
      dataProtectionLevel: null,
    },
    profileError: null,
    subscription: {
      plan: 'plus',
      status: 'active',
      transcriptionSecondsUsed: null,
      transcriptionSecondsLimit: null,
    },
    subscriptionError: null,
    storeRecordingPermission: null,
    storeRecordingError: null,
    trainingOptedIn: null,
    trainingError: null,
    privateCloudSync: null,
    privateCloudSyncError: null,
    webhooks: null,
    webhooksError: null,
    usage: null,
    usageError: null,
    language: null,
    languageError: null,
    languageNames: null,
    languageNamesError: null,
  });
  omiBackend.request.mockImplementation(async request => {
    if (request.path === '/v1/fair-use/status') {
      throw Object.assign(new Error('lost'), {code: 'OMI_HTTP_TRANSPORT'});
    }
    return {id: request.id, status: 404, body: null};
  });
  const renderer = renderDesktop();
  await act(async () => {
    renderer.root
      .find(node => node.props.accessibilityLabel === 'Settings')
      .props.onPress();
    await Promise.resolve();
    await Promise.resolve();
  });
  act(() => {
    renderer.root
      .find(node => node.props.accessibilityLabel === 'Account & Plan')
      .props.onPress();
  });
  const tree = renderedText(renderer);
  expect(tree).toContain('Ada');
  expect(tree).toContain('Fair Use');
  expect(tree).toContain(fairUseLoadErrorCopy());
  expect(tree).not.toContain(desktopBackendServiceCopy);
  expect(tree).not.toContain('Restricted');
  expect(tree).not.toContain('FU-1');
  expect(tree).not.toContain('Upgrade');
});

test('Settings names malformed fair use GET instead of empty success', async () => {
  const {loadAccountSettings} = jest.requireMock('../desktopCloudClient') as {
    loadAccountSettings: jest.Mock;
  };
  const {omiBackend} = jest.requireMock('../omiNative') as {
    omiBackend: {request: jest.Mock};
  };
  loadAccountSettings.mockResolvedValueOnce({
    profile: {
      uid: 'user-1',
      name: 'Ada',
      email: 'ada@example.com',
      company: null,
      job: null,
      dataProtectionLevel: null,
    },
    profileError: null,
    subscription: {
      plan: 'plus',
      status: 'active',
      transcriptionSecondsUsed: null,
      transcriptionSecondsLimit: null,
    },
    subscriptionError: null,
    storeRecordingPermission: null,
    storeRecordingError: null,
    trainingOptedIn: null,
    trainingError: null,
    privateCloudSync: null,
    privateCloudSyncError: null,
    webhooks: null,
    webhooksError: null,
    usage: null,
    usageError: null,
    language: null,
    languageError: null,
    languageNames: null,
    languageNamesError: null,
  });
  omiBackend.request.mockImplementation(async request => {
    if (request.path === '/v1/fair-use/status') {
      return {id: request.id, status: 200, body: '{'};
    }
    return {id: request.id, status: 404, body: null};
  });
  const renderer = renderDesktop();
  await act(async () => {
    renderer.root
      .find(node => node.props.accessibilityLabel === 'Settings')
      .props.onPress();
    await Promise.resolve();
    await Promise.resolve();
  });
  act(() => {
    renderer.root
      .find(node => node.props.accessibilityLabel === 'Account & Plan')
      .props.onPress();
  });
  const tree = renderedText(renderer);
  expect(tree).toContain('Ada');
  expect(tree).toContain('Fair Use');
  expect(tree).toContain(fairUseLoadErrorCopy());
  expect(tree).not.toContain('Restricted');
  expect(tree).not.toContain('FU-1');
  expect(tree).not.toContain('Upgrade');
});

test('Settings names HTTP 404 fair use GET Flutter fairUseLoadError instead of omitting', async () => {
  const {loadAccountSettings} = jest.requireMock('../desktopCloudClient') as {
    loadAccountSettings: jest.Mock;
  };
  const {omiBackend} = jest.requireMock('../omiNative') as {
    omiBackend: {request: jest.Mock};
  };
  loadAccountSettings.mockResolvedValueOnce({
    profile: {
      uid: 'user-1',
      name: 'Ada',
      email: 'ada@example.com',
      company: null,
      job: null,
      dataProtectionLevel: null,
    },
    profileError: null,
    subscription: {
      plan: 'plus',
      status: 'active',
      transcriptionSecondsUsed: null,
      transcriptionSecondsLimit: null,
    },
    subscriptionError: null,
    storeRecordingPermission: null,
    storeRecordingError: null,
    trainingOptedIn: null,
    trainingError: null,
    privateCloudSync: null,
    privateCloudSyncError: null,
    webhooks: null,
    webhooksError: null,
    usage: null,
    usageError: null,
    language: null,
    languageError: null,
    languageNames: null,
    languageNamesError: null,
  });
  omiBackend.request.mockImplementation(async request => {
    if (request.path === '/v1/fair-use/status') {
      return {id: request.id, status: 404, body: null};
    }
    return {id: request.id, status: 404, body: null};
  });
  const renderer = renderDesktop();
  await act(async () => {
    renderer.root
      .find(node => node.props.accessibilityLabel === 'Settings')
      .props.onPress();
    await Promise.resolve();
    await Promise.resolve();
  });
  act(() => {
    renderer.root
      .find(node => node.props.accessibilityLabel === 'Account & Plan')
      .props.onPress();
  });
  const tree = renderedText(renderer);
  expect(tree).toContain('Ada');
  expect(tree).toContain('Fair Use');
  expect(tree).toContain(fairUseLoadErrorCopy());
  expect(tree).not.toContain('Restricted');
  expect(tree).not.toContain('About Fair Use');
  expect(tree).not.toContain('Upgrade');
});

test('Settings omits Flutter DailySummaryCard unused GET stats emoji and overview', async () => {
  const {loadAccountSettings} = jest.requireMock('../desktopCloudClient') as {
    loadAccountSettings: jest.Mock;
  };
  const {omiBackend} = jest.requireMock('../omiNative') as {
    omiBackend: {request: jest.Mock};
  };
  loadAccountSettings.mockResolvedValueOnce({
    profile: {
      uid: 'user-1',
      name: 'Ada',
      email: 'ada@example.com',
      company: null,
      job: null,
      dataProtectionLevel: null,
    },
    profileError: null,
    subscription: {
      plan: 'plus',
      status: 'active',
      transcriptionSecondsUsed: null,
      transcriptionSecondsLimit: null,
    },
    subscriptionError: null,
    storeRecordingPermission: null,
    storeRecordingError: null,
    trainingOptedIn: null,
    trainingError: null,
    privateCloudSync: null,
    privateCloudSyncError: null,
    webhooks: null,
    webhooksError: null,
    usage: null,
    usageError: null,
    language: null,
    languageError: null,
    languageNames: null,
    languageNamesError: null,
  });
  omiBackend.request.mockImplementation(async request => {
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
          ],
        }),
      };
    }
    return {id: request.id, status: 404, body: null};
  });
  const renderer = renderDesktop();
  await act(async () => {
    renderer.root
      .find(node => node.props.accessibilityLabel === 'Settings')
      .props.onPress();
    await Promise.resolve();
    await Promise.resolve();
  });
  act(() => {
    renderer.root
      .find(node => node.props.accessibilityLabel === 'Account & Plan')
      .props.onPress();
  });
  const tree = renderedText(renderer);
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
  const {loadAccountSettings} = jest.requireMock('../desktopCloudClient') as {
    loadAccountSettings: jest.Mock;
  };
  const {omiBackend} = jest.requireMock('../omiNative') as {
    omiBackend: {request: jest.Mock};
  };
  loadAccountSettings.mockResolvedValueOnce({
    profile: {
      uid: 'user-1',
      name: 'Ada',
      email: 'ada@example.com',
      company: null,
      job: null,
      dataProtectionLevel: null,
    },
    profileError: null,
    subscription: {
      plan: 'plus',
      status: 'active',
      transcriptionSecondsUsed: null,
      transcriptionSecondsLimit: null,
    },
    subscriptionError: null,
    storeRecordingPermission: null,
    storeRecordingError: null,
    trainingOptedIn: null,
    trainingError: null,
    privateCloudSync: null,
    privateCloudSyncError: null,
    webhooks: null,
    webhooksError: null,
    usage: null,
    usageError: null,
    language: null,
    languageError: null,
    languageNames: null,
    languageNamesError: null,
  });
  omiBackend.request.mockImplementation(async request => {
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
  const renderer = renderDesktop();
  await act(async () => {
    renderer.root
      .find(node => node.props.accessibilityLabel === 'Settings')
      .props.onPress();
    await Promise.resolve();
    await Promise.resolve();
  });
  act(() => {
    renderer.root
      .find(node => node.props.accessibilityLabel === 'Account & Plan')
      .props.onPress();
  });
  const tree = renderedText(renderer);
  expect(tree).toContain('Daily summary');
  expect(tree).toContain(dailySummaryDefaultHeadlineCopy());
  expect(tree).toContain('Met with the team');
  expect(tree).not.toContain('📅');
  expect(tree).not.toContain('Regenerate');
});

test('Settings names a failed daily summaries GET instead of empty success', async () => {
  const {loadAccountSettings} = jest.requireMock('../desktopCloudClient') as {
    loadAccountSettings: jest.Mock;
  };
  const {omiBackend} = jest.requireMock('../omiNative') as {
    omiBackend: {request: jest.Mock};
  };
  loadAccountSettings.mockResolvedValueOnce({
    profile: {
      uid: 'user-1',
      name: 'Ada',
      email: 'ada@example.com',
      company: null,
      job: null,
      dataProtectionLevel: null,
    },
    profileError: null,
    subscription: {
      plan: 'plus',
      status: 'active',
      transcriptionSecondsUsed: null,
      transcriptionSecondsLimit: null,
    },
    subscriptionError: null,
    storeRecordingPermission: null,
    storeRecordingError: null,
    trainingOptedIn: null,
    trainingError: null,
    privateCloudSync: null,
    privateCloudSyncError: null,
    webhooks: null,
    webhooksError: null,
    usage: null,
    usageError: null,
    language: null,
    languageError: null,
    languageNames: null,
    languageNamesError: null,
  });
  omiBackend.request.mockImplementation(async request => {
    if (request.path === '/v1/users/daily-summaries?limit=3&offset=0') {
      throw Object.assign(new Error('lost'), {code: 'OMI_HTTP_TRANSPORT'});
    }
    return {id: request.id, status: 404, body: null};
  });
  const renderer = renderDesktop();
  await act(async () => {
    renderer.root
      .find(node => node.props.accessibilityLabel === 'Settings')
      .props.onPress();
    await Promise.resolve();
    await Promise.resolve();
  });
  act(() => {
    renderer.root
      .find(node => node.props.accessibilityLabel === 'Account & Plan')
      .props.onPress();
  });
  const tree = renderedText(renderer);
  expect(tree).toContain('Ada');
  expect(tree).toContain('Daily summary');
  expect(tree).toContain(desktopBackendServiceCopy);
  expect(tree).not.toContain('Met with the team');
  expect(tree).not.toContain('Your Day in Review');
  expect(tree).not.toContain('Regenerate');
});

test('Settings names GET daily-summary-settings without a picker or Flutter defaults', async () => {
  const {loadAccountSettings} = jest.requireMock('../desktopCloudClient') as {
    loadAccountSettings: jest.Mock;
  };
  const {omiBackend} = jest.requireMock('../omiNative') as {
    omiBackend: {request: jest.Mock};
  };
  loadAccountSettings.mockResolvedValueOnce({
    profile: {
      uid: 'user-1',
      name: 'Ada',
      email: 'ada@example.com',
      company: null,
      job: null,
      dataProtectionLevel: null,
    },
    profileError: null,
    subscription: {
      plan: 'plus',
      status: 'active',
      transcriptionSecondsUsed: null,
      transcriptionSecondsLimit: null,
    },
    subscriptionError: null,
    storeRecordingPermission: null,
    storeRecordingError: null,
    trainingOptedIn: null,
    trainingError: null,
    privateCloudSync: null,
    privateCloudSyncError: null,
    webhooks: null,
    webhooksError: null,
    usage: null,
    usageError: null,
    language: null,
    languageError: null,
    languageNames: null,
    languageNamesError: null,
  });
  omiBackend.request.mockImplementation(async request => {
    if (request.path === '/v1/users/daily-summary-settings') {
      return {
        id: request.id,
        status: 200,
        body: JSON.stringify({enabled: false, hour: 0}),
      };
    }
    return {id: request.id, status: 404, body: null};
  });
  const renderer = renderDesktop();
  await act(async () => {
    renderer.root
      .find(node => node.props.accessibilityLabel === 'Settings')
      .props.onPress();
    await Promise.resolve();
    await Promise.resolve();
  });
  act(() => {
    renderer.root
      .find(node => node.props.accessibilityLabel === 'Account & Plan')
      .props.onPress();
  });
  const tree = renderedText(renderer);
  expect(tree).toContain('Daily Summary');
  expect(tree).toContain('Off');
  expect(tree).toContain('Delivery Time');
  expect(tree).toContain('12:00 AM');
  expect(tree).toContain(
    "Get a personalized summary of your day's conversations delivered as a notification.",
  );
  expect(tree).not.toContain('10:00 PM');
  expect(tree).not.toContain('Your Day in Review');
  expect(
    omiBackend.request.mock.calls.some(call => call[0].method === 'PATCH'),
  ).toBe(false);
});

test('Settings names a failed daily-summary-settings GET instead of empty success', async () => {
  const {loadAccountSettings} = jest.requireMock('../desktopCloudClient') as {
    loadAccountSettings: jest.Mock;
  };
  const {omiBackend} = jest.requireMock('../omiNative') as {
    omiBackend: {request: jest.Mock};
  };
  loadAccountSettings.mockResolvedValueOnce({
    profile: {
      uid: 'user-1',
      name: 'Ada',
      email: 'ada@example.com',
      company: null,
      job: null,
      dataProtectionLevel: null,
    },
    profileError: null,
    subscription: {
      plan: 'plus',
      status: 'active',
      transcriptionSecondsUsed: null,
      transcriptionSecondsLimit: null,
    },
    subscriptionError: null,
    storeRecordingPermission: null,
    storeRecordingError: null,
    trainingOptedIn: null,
    trainingError: null,
    privateCloudSync: null,
    privateCloudSyncError: null,
    webhooks: null,
    webhooksError: null,
    usage: null,
    usageError: null,
    language: null,
    languageError: null,
    languageNames: null,
    languageNamesError: null,
  });
  omiBackend.request.mockImplementation(async request => {
    if (request.path === '/v1/users/daily-summary-settings') {
      throw Object.assign(new Error('lost'), {code: 'OMI_HTTP_TRANSPORT'});
    }
    return {id: request.id, status: 404, body: null};
  });
  const renderer = renderDesktop();
  await act(async () => {
    renderer.root
      .find(node => node.props.accessibilityLabel === 'Settings')
      .props.onPress();
    await Promise.resolve();
    await Promise.resolve();
  });
  act(() => {
    renderer.root
      .find(node => node.props.accessibilityLabel === 'Account & Plan')
      .props.onPress();
  });
  const tree = renderedText(renderer);
  expect(tree).toContain('Ada');
  expect(tree).toContain('Daily Summary');
  expect(tree).toContain(desktopBackendServiceCopy);
  expect(tree).not.toContain('Enabled');
  expect(tree).not.toContain('10:00 PM');
  expect(tree).not.toContain('Your Day in Review');
  expect(tree).not.toContain(dailySummaryDescriptionCopy());
});

test('Settings names GET mentor notification frequency without a purple slider', async () => {
  const {loadAccountSettings} = jest.requireMock('../desktopCloudClient') as {
    loadAccountSettings: jest.Mock;
  };
  const {omiBackend} = jest.requireMock('../omiNative') as {
    omiBackend: {request: jest.Mock};
  };
  loadAccountSettings.mockResolvedValueOnce({
    profile: {
      uid: 'user-1',
      name: 'Ada',
      email: 'ada@example.com',
      company: null,
      job: null,
      dataProtectionLevel: null,
    },
    profileError: null,
    subscription: {
      plan: 'plus',
      status: 'active',
      transcriptionSecondsUsed: null,
      transcriptionSecondsLimit: null,
    },
    subscriptionError: null,
    storeRecordingPermission: null,
    storeRecordingError: null,
    trainingOptedIn: null,
    trainingError: null,
    privateCloudSync: null,
    privateCloudSyncError: null,
    webhooks: null,
    webhooksError: null,
    usage: null,
    usageError: null,
    language: null,
    languageError: null,
    languageNames: null,
    languageNamesError: null,
  });
  omiBackend.request.mockImplementation(async request => {
    if (request.path === '/v1/users/mentor-notification-settings') {
      return {
        id: request.id,
        status: 200,
        body: JSON.stringify({frequency: 5}),
      };
    }
    return {id: request.id, status: 404, body: null};
  });
  const renderer = renderDesktop();
  await act(async () => {
    renderer.root
      .find(node => node.props.accessibilityLabel === 'Settings')
      .props.onPress();
    await Promise.resolve();
    await Promise.resolve();
  });
  act(() => {
    renderer.root
      .find(node => node.props.accessibilityLabel === 'Account & Plan')
      .props.onPress();
  });
  const tree = renderedText(renderer);
  expect(tree).toContain('Notification Frequency');
  expect(tree).toContain('Maximum');
  expect(tree).toContain('Stay constantly engaged');
  expect(tree).toContain(
    'Control how often Omi sends you proactive notifications and reminders.',
  );
  expect(tree).not.toContain('Balanced');
  expect(
    omiBackend.request.mock.calls.some(call => call[0].method === 'PATCH'),
  ).toBe(false);
});

test('Settings names a failed mentor notification GET instead of empty success', async () => {
  const {loadAccountSettings} = jest.requireMock('../desktopCloudClient') as {
    loadAccountSettings: jest.Mock;
  };
  const {omiBackend} = jest.requireMock('../omiNative') as {
    omiBackend: {request: jest.Mock};
  };
  loadAccountSettings.mockResolvedValueOnce({
    profile: {
      uid: 'user-1',
      name: 'Ada',
      email: 'ada@example.com',
      company: null,
      job: null,
      dataProtectionLevel: null,
    },
    profileError: null,
    subscription: {
      plan: 'plus',
      status: 'active',
      transcriptionSecondsUsed: null,
      transcriptionSecondsLimit: null,
    },
    subscriptionError: null,
    storeRecordingPermission: null,
    storeRecordingError: null,
    trainingOptedIn: null,
    trainingError: null,
    privateCloudSync: null,
    privateCloudSyncError: null,
    webhooks: null,
    webhooksError: null,
    usage: null,
    usageError: null,
    language: null,
    languageError: null,
    languageNames: null,
    languageNamesError: null,
  });
  omiBackend.request.mockImplementation(async request => {
    if (request.path === '/v1/users/mentor-notification-settings') {
      throw Object.assign(new Error('lost'), {code: 'OMI_HTTP_TRANSPORT'});
    }
    return {id: request.id, status: 404, body: null};
  });
  const renderer = renderDesktop();
  await act(async () => {
    renderer.root
      .find(node => node.props.accessibilityLabel === 'Settings')
      .props.onPress();
    await Promise.resolve();
    await Promise.resolve();
  });
  act(() => {
    renderer.root
      .find(node => node.props.accessibilityLabel === 'Account & Plan')
      .props.onPress();
  });
  const tree = renderedText(renderer);
  expect(tree).toContain('Ada');
  expect(tree).toContain('Notification Frequency');
  expect(tree).toContain(desktopBackendServiceCopy);
  expect(tree).not.toContain('Maximum');
  expect(tree).not.toContain('Balanced');
  expect(tree).not.toContain(
    'Control how often Omi sends you proactive notifications and reminders.',
  );
});

test('Settings names GET custom vocabulary without add/delete or Flutter false defaults', async () => {
  const {loadAccountSettings} = jest.requireMock('../desktopCloudClient') as {
    loadAccountSettings: jest.Mock;
  };
  const {omiBackend} = jest.requireMock('../omiNative') as {
    omiBackend: {request: jest.Mock};
  };
  loadAccountSettings.mockResolvedValueOnce({
    profile: {
      uid: 'user-1',
      name: 'Ada',
      email: 'ada@example.com',
      company: null,
      job: null,
      dataProtectionLevel: null,
    },
    profileError: null,
    subscription: {
      plan: 'plus',
      status: 'active',
      transcriptionSecondsUsed: null,
      transcriptionSecondsLimit: null,
    },
    subscriptionError: null,
    storeRecordingPermission: null,
    storeRecordingError: null,
    trainingOptedIn: null,
    trainingError: null,
    privateCloudSync: null,
    privateCloudSyncError: null,
    webhooks: null,
    webhooksError: null,
    usage: null,
    usageError: null,
    language: null,
    languageError: null,
    languageNames: null,
    languageNamesError: null,
  });
  omiBackend.request.mockImplementation(async request => {
    if (request.path === '/v1/users/transcription-preferences') {
      return {
        id: request.id,
        status: 200,
        body: JSON.stringify({
          vocabulary: ['Omi'],
          single_language_mode: false,
        }),
      };
    }
    return {id: request.id, status: 404, body: null};
  });
  const renderer = renderDesktop();
  await act(async () => {
    renderer.root
      .find(node => node.props.accessibilityLabel === 'Settings')
      .props.onPress();
    await Promise.resolve();
    await Promise.resolve();
  });
  act(() => {
    renderer.root
      .find(node => node.props.accessibilityLabel === 'Account & Plan')
      .props.onPress();
  });
  const tree = renderedText(renderer);
  expect(tree).toContain('Custom Vocabulary');
  expect(tree).toContain('Omi');
  expect(tree).toContain('Automatic Translation');
  expect(tree).toContain('Enabled');
  expect(tree).toContain('Detect 10+ languages');
  expect(tree).not.toContain('Add Words');
  expect(
    omiBackend.request.mock.calls.some(call => call[0].method === 'PATCH'),
  ).toBe(false);
});

test('Settings names Flutter omitted GET single_language_mode as Automatic Translation Enabled', async () => {
  const {loadAccountSettings} = jest.requireMock('../desktopCloudClient') as {
    loadAccountSettings: jest.Mock;
  };
  const {omiBackend} = jest.requireMock('../omiNative') as {
    omiBackend: {request: jest.Mock};
  };
  loadAccountSettings.mockResolvedValueOnce({
    profile: {
      uid: 'user-1',
      name: 'Ada',
      email: 'ada@example.com',
      company: null,
      job: null,
      dataProtectionLevel: null,
    },
    profileError: null,
    subscription: {
      plan: 'plus',
      status: 'active',
      transcriptionSecondsUsed: null,
      transcriptionSecondsLimit: null,
    },
    subscriptionError: null,
    storeRecordingPermission: null,
    storeRecordingError: null,
    trainingOptedIn: null,
    trainingError: null,
    privateCloudSync: null,
    privateCloudSyncError: null,
    webhooks: null,
    webhooksError: null,
    usage: null,
    usageError: null,
    language: null,
    languageError: null,
    languageNames: null,
    languageNamesError: null,
  });
  omiBackend.request.mockImplementation(async request => {
    if (request.path === '/v1/users/transcription-preferences') {
      return {
        id: request.id,
        status: 200,
        body: JSON.stringify({vocabulary: ['Omi']}),
      };
    }
    return {id: request.id, status: 404, body: null};
  });
  const renderer = renderDesktop();
  await act(async () => {
    renderer.root
      .find(node => node.props.accessibilityLabel === 'Settings')
      .props.onPress();
    await Promise.resolve();
    await Promise.resolve();
  });
  act(() => {
    renderer.root
      .find(node => node.props.accessibilityLabel === 'Account & Plan')
      .props.onPress();
  });
  const omittedTree = renderedText(renderer);
  expect(omittedTree).toContain('Custom Vocabulary');
  expect(omittedTree).toContain('Omi');
  expect(omittedTree).toContain('Automatic Translation');
  expect(omittedTree).toContain('Enabled');
  expect(omittedTree).toContain('Detect 10+ languages');
  expect(omittedTree).not.toContain('Add Words');
});

test('Settings names a failed transcription-preferences GET instead of empty success', async () => {
  const {loadAccountSettings} = jest.requireMock('../desktopCloudClient') as {
    loadAccountSettings: jest.Mock;
  };
  const {omiBackend} = jest.requireMock('../omiNative') as {
    omiBackend: {request: jest.Mock};
  };
  loadAccountSettings.mockResolvedValueOnce({
    profile: {
      uid: 'user-1',
      name: 'Ada',
      email: 'ada@example.com',
      company: null,
      job: null,
      dataProtectionLevel: null,
    },
    profileError: null,
    subscription: {
      plan: 'plus',
      status: 'active',
      transcriptionSecondsUsed: null,
      transcriptionSecondsLimit: null,
    },
    subscriptionError: null,
    storeRecordingPermission: null,
    storeRecordingError: null,
    trainingOptedIn: null,
    trainingError: null,
    privateCloudSync: null,
    privateCloudSyncError: null,
    webhooks: null,
    webhooksError: null,
    usage: null,
    usageError: null,
    language: null,
    languageError: null,
    languageNames: null,
    languageNamesError: null,
  });
  omiBackend.request.mockImplementation(async request => {
    if (request.path === '/v1/users/transcription-preferences') {
      throw Object.assign(new Error('lost'), {code: 'OMI_HTTP_TRANSPORT'});
    }
    return {id: request.id, status: 404, body: null};
  });
  const renderer = renderDesktop();
  await act(async () => {
    renderer.root
      .find(node => node.props.accessibilityLabel === 'Settings')
      .props.onPress();
    await Promise.resolve();
    await Promise.resolve();
  });
  act(() => {
    renderer.root
      .find(node => node.props.accessibilityLabel === 'Account & Plan')
      .props.onPress();
  });
  const tree = renderedText(renderer);
  expect(tree).toContain('Ada');
  expect(tree).toContain('Automatic Translation');
  expect(tree).toContain('Custom Vocabulary');
  expect(tree).toContain(desktopBackendServiceCopy);
  expect(tree).not.toContain('Based Hardware');
  expect(tree).not.toContain('Add Words');
  expect(tree).not.toContain('Detect 10+ languages');
});

test('Settings omits Flutter Profile.build() GET company, job, and data protection', async () => {
  const {loadAccountSettings} = jest.requireMock('../desktopCloudClient') as {
    loadAccountSettings: jest.Mock;
  };
  loadAccountSettings.mockResolvedValueOnce({
    profile: {
      uid: 'user-1',
      name: 'Ada',
      email: 'ada@example.com',
      company: 'Based Hardware',
      job: 'Engineer',
      dataProtectionLevel: 'standard',
    },
    profileError: null,
    subscription: null,
    subscriptionError: null,
    storeRecordingPermission: null,
    storeRecordingError: null,
    trainingOptedIn: null,
    trainingError: null,
    privateCloudSync: null,
    privateCloudSyncError: null,
    webhooks: null,
    webhooksError: null,
  });
  const renderer = renderDesktop();
  await act(async () => {
    renderer.root
      .find(node => node.props.accessibilityLabel === 'Settings')
      .props.onPress();
    await Promise.resolve();
    await Promise.resolve();
  });
  act(() => {
    renderer.root
      .find(node => node.props.accessibilityLabel === 'Account & Plan')
      .props.onPress();
  });
  const tree = renderedText(renderer);
  expect(tree).toContain('Ada');
  expect(tree).toContain('User ID');
  expect(tree).not.toContain('Company');
  expect(tree).not.toContain('Based Hardware');
  expect(tree).not.toContain('Job');
  expect(tree).not.toContain('Engineer');
  expect(tree).not.toContain('Data protection');
  expect(tree).not.toContain('Standard');
});

test('Settings names Flutter Profile truncated User ID', async () => {
  const {loadAccountSettings} = jest.requireMock('../desktopCloudClient') as {
    loadAccountSettings: jest.Mock;
  };
  loadAccountSettings.mockResolvedValueOnce({
    profile: {
      uid: 'firebase-uid-abcdefghijklmnopqrstuvwxyz',
      name: 'Ada',
      email: 'ada@example.com',
    },
    profileError: null,
    subscription: null,
    subscriptionError: null,
    storeRecordingPermission: null,
    storeRecordingError: null,
    trainingOptedIn: null,
    trainingError: null,
    privateCloudSync: null,
    privateCloudSyncError: null,
    webhooks: null,
    webhooksError: null,
  });
  const renderer = renderDesktop();
  await act(async () => {
    renderer.root
      .find(node => node.props.accessibilityLabel === 'Settings')
      .props.onPress();
    await Promise.resolve();
    await Promise.resolve();
  });
  act(() => {
    renderer.root
      .find(node => node.props.accessibilityLabel === 'Account & Plan')
      .props.onPress();
  });
  const tree = renderedText(renderer);
  expect(tree).toContain('User ID');
  expect(tree).toContain('fir•••••xyz');
  expect(tree).not.toContain('firebase-uid-abcdefghijklmnopqrstuvwxyz');
  expect(tree).toContain('Ada');
});

test('Settings reports a nested non-retryable profile read as unavailable', async () => {
  const {loadAccountSettings} = jest.requireMock('../desktopCloudClient') as {
    loadAccountSettings: jest.Mock;
  };
  loadAccountSettings.mockResolvedValueOnce({
    profile: null,
    profileError: desktopAccountSettingUnavailableCopy,
    subscription: null,
    subscriptionError: null,
    storeRecordingPermission: null,
    storeRecordingError: null,
    trainingOptedIn: null,
    trainingError: null,
    privateCloudSync: null,
    privateCloudSyncError: null,
    webhooks: null,
    webhooksError: null,
  });
  const renderer = renderDesktop();
  await act(async () => {
    renderer.root
      .find(node => node.props.accessibilityLabel === 'Settings')
      .props.onPress();
    await Promise.resolve();
    await Promise.resolve();
  });
  act(() => {
    renderer.root
      .find(node => node.props.accessibilityLabel === 'Account & Plan')
      .props.onPress();
  });
  expect(renderedText(renderer)).toContain(
    desktopAccountSettingUnavailableCopy,
  );
  expect(renderedText(renderer)).not.toContain('Signed in to Omi');
});

test('Settings does not claim Signed in to Omi when a loaded profile has no email', async () => {
  const {loadAccountSettings} = jest.requireMock('../desktopCloudClient') as {
    loadAccountSettings: jest.Mock;
  };
  loadAccountSettings.mockResolvedValueOnce({
    profile: {
      uid: 'user-1',
      name: 'Ada',
      email: null,
      company: null,
      job: null,
      dataProtectionLevel: null,
    },
    profileError: null,
    subscription: null,
    subscriptionError: null,
    storeRecordingPermission: null,
    storeRecordingError: null,
    trainingOptedIn: null,
    trainingError: null,
    privateCloudSync: null,
    privateCloudSyncError: null,
    webhooks: null,
    webhooksError: null,
  });
  const renderer = renderDesktop();
  await act(async () => {
    renderer.root
      .find(node => node.props.accessibilityLabel === 'Settings')
      .props.onPress();
    await Promise.resolve();
    await Promise.resolve();
  });
  act(() => {
    renderer.root
      .find(node => node.props.accessibilityLabel === 'Account & Plan')
      .props.onPress();
  });
  expect(renderedText(renderer)).toContain(primaryLanguageNotSetCopy());
  expect(renderedText(renderer)).not.toContain('Email not set on this account.');
  expect(renderedText(renderer)).toContain('Ada');
  expect(renderedText(renderer)).not.toContain('Signed in to Omi');
});

test('Settings shows already-loaded Account id and Name not set', async () => {
  const {loadAccountSettings} = jest.requireMock('../desktopCloudClient') as {
    loadAccountSettings: jest.Mock;
  };
  loadAccountSettings.mockResolvedValueOnce({
    profile: {
      uid: 'user-42',
      name: null,
      email: 'ada@example.com',
      company: null,
      job: null,
      dataProtectionLevel: null,
    },
    profileError: null,
    subscription: null,
    subscriptionError: null,
    storeRecordingPermission: null,
    storeRecordingError: null,
    trainingOptedIn: null,
    trainingError: null,
    privateCloudSync: null,
    privateCloudSyncError: null,
    webhooks: null,
    webhooksError: null,
  });
  const renderer = renderDesktop();
  await act(async () => {
    renderer.root
      .find(node => node.props.accessibilityLabel === 'Settings')
      .props.onPress();
    await Promise.resolve();
    await Promise.resolve();
  });
  act(() => {
    renderer.root
      .find(node => node.props.accessibilityLabel === 'Account & Plan')
      .props.onPress();
  });
  const tree = renderedText(renderer);
  expect(tree).toContain(primaryLanguageNotSetCopy());
  expect(tree).not.toContain('Name not set on this account.');
  expect(tree).toContain('User ID');
  expect(tree).not.toContain('Account id');
  expect(tree).toContain('use•••••-42');
  expect(tree).not.toContain('user-42');
  expect(tree).not.toContain('Signed in to Omi');
});

test('Settings treats whitespace-only Account name and email as unset', async () => {
  const {loadAccountSettings} = jest.requireMock('../desktopCloudClient') as {
    loadAccountSettings: jest.Mock;
  };
  loadAccountSettings.mockResolvedValueOnce({
    profile: {
      uid: 'user-42',
      name: ' \t\n',
      email: ' \t',
      company: ' \t',
      job: '\u00A0',
      dataProtectionLevel: null,
    },
    profileError: null,
    subscription: null,
    subscriptionError: null,
    storeRecordingPermission: null,
    storeRecordingError: null,
    trainingOptedIn: null,
    trainingError: null,
    privateCloudSync: null,
    privateCloudSyncError: null,
    webhooks: null,
    webhooksError: null,
  });
  const renderer = renderDesktop();
  await act(async () => {
    renderer.root
      .find(node => node.props.accessibilityLabel === 'Settings')
      .props.onPress();
    await Promise.resolve();
    await Promise.resolve();
  });
  act(() => {
    renderer.root
      .find(node => node.props.accessibilityLabel === 'Account & Plan')
      .props.onPress();
  });
  const tree = renderedText(renderer);
  expect(tree).toContain(primaryLanguageNotSetCopy());
  expect(tree).not.toContain('Name not set on this account.');
  expect(tree).not.toContain('Email not set on this account.');
  expect(tree).not.toContain('Company');
  expect(tree).not.toContain('Job');
});

test('Settings treats NEXT LINE-only company and job as unset', async () => {
  const {loadAccountSettings} = jest.requireMock('../desktopCloudClient') as {
    loadAccountSettings: jest.Mock;
  };
  loadAccountSettings.mockResolvedValueOnce({
    profile: {
      uid: 'user-42',
      name: 'Ada',
      email: 'ada@example.com',
      company: '\u0085',
      job: '\u0085',
      dataProtectionLevel: null,
    },
    profileError: null,
    subscription: null,
    subscriptionError: null,
    storeRecordingPermission: null,
    storeRecordingError: null,
    trainingOptedIn: null,
    trainingError: null,
    privateCloudSync: null,
    privateCloudSyncError: null,
    webhooks: null,
    webhooksError: null,
  });
  const renderer = renderDesktop();
  await act(async () => {
    renderer.root
      .find(node => node.props.accessibilityLabel === 'Settings')
      .props.onPress();
    await Promise.resolve();
    await Promise.resolve();
  });
  act(() => {
    renderer.root
      .find(node => node.props.accessibilityLabel === 'Account & Plan')
      .props.onPress();
  });
  const tree = renderedText(renderer);
  expect(tree).toContain('Ada');
  expect(tree).not.toContain('Company');
  expect(tree).not.toContain('Job');
  expect(tree).not.toContain('\u0085');
});

test('Settings treats whitespace-only Account id as unavailable', async () => {
  const {loadAccountSettings} = jest.requireMock('../desktopCloudClient') as {
    loadAccountSettings: jest.Mock;
  };
  loadAccountSettings.mockResolvedValueOnce({
    profile: {
      uid: ' \t\n',
      name: 'Ada',
      email: 'ada@example.com',
      company: null,
      job: null,
      dataProtectionLevel: null,
    },
    profileError: null,
    subscription: null,
    subscriptionError: null,
    storeRecordingPermission: null,
    storeRecordingError: null,
    trainingOptedIn: null,
    trainingError: null,
    privateCloudSync: null,
    privateCloudSyncError: null,
    webhooks: null,
    webhooksError: null,
  });
  const renderer = renderDesktop();
  await act(async () => {
    renderer.root
      .find(node => node.props.accessibilityLabel === 'Settings')
      .props.onPress();
    await Promise.resolve();
    await Promise.resolve();
  });
  act(() => {
    renderer.root
      .find(node => node.props.accessibilityLabel === 'Account & Plan')
      .props.onPress();
  });
  const tree = renderedText(renderer);
  expect(tree).toContain('Account id unavailable');
  expect(tree).toContain('Ada');
  expect(tree).not.toContain('Signed in to Omi');
});

test('Settings Alerts does not claim privacy slices unavailable while account is loading', async () => {
  const {loadAccountSettings} = jest.requireMock('../desktopCloudClient') as {
    loadAccountSettings: jest.Mock;
  };
  loadAccountSettings.mockReturnValueOnce(new Promise(() => {}));
  const renderer = renderDesktop();
  await act(async () => {
    renderer.root
      .find(node => node.props.accessibilityLabel === 'Settings')
      .props.onPress();
    await Promise.resolve();
  });
  act(() => {
    renderer.root
      .find(node => node.props.accessibilityLabel === 'Alerts & Privacy')
      .props.onPress();
  });
  expect(renderedText(renderer)).toContain('Loading recording storage…');
  expect(renderedText(renderer)).toContain('Loading private cloud sync…');
  expect(renderedText(renderer)).toContain('Loading training data…');
  expect(renderedText(renderer)).not.toContain(
    'Cloud recording storage status is unavailable.',
  );
  expect(renderedText(renderer)).not.toContain(
    'Private cloud sync status is unavailable.',
  );
  expect(renderedText(renderer)).not.toContain(
    'Training opt-in is unavailable.',
  );
  expect(
    renderer.root.findAll(node => node.props.accessibilityLabel === 'Update'),
  ).toHaveLength(0);
  expect(
    renderer.root.findAll(node => node.props.accessibilityLabel === 'Opt in'),
  ).toHaveLength(0);
});

test('Settings does not expose cloud mutations when account values failed to load', async () => {
  const renderer = renderDesktop();
  await act(async () => {
    renderer.root
      .find(node => node.props.accessibilityLabel === 'Settings')
      .props.onPress();
    await Promise.resolve();
    await Promise.resolve();
  });
  act(() => {
    renderer.root
      .find(node => node.props.accessibilityLabel === 'Account & Plan')
      .props.onPress();
  });
  expect(renderedText(renderer)).toContain(
    'This saved data could not be loaded. Retry without changing it.',
  );
  expect(renderedText(renderer)).not.toContain('Loading account…');
  expect(renderedText(renderer)).not.toContain('Loading plan…');
  act(() => {
    renderer.root
      .find(node => node.props.accessibilityLabel === 'Alerts & Privacy')
      .props.onPress();
  });
  expect(renderedText(renderer)).toContain(
    'This saved data could not be loaded. Retry without changing it.',
  );
  expect(renderedText(renderer)).not.toContain('Loading recording storage…');
  expect(renderedText(renderer)).not.toContain('Loading private cloud sync…');
  expect(renderedText(renderer)).not.toContain('Loading training data…');
  expect(
    renderer.root.findAll(node => node.props.accessibilityLabel === 'Update'),
  ).toHaveLength(0);
  expect(
    renderer.root.findAll(node => node.props.accessibilityLabel === 'Opt in'),
  ).toHaveLength(0);
});

test('Settings does not claim a plan is loading after the backend is missing', async () => {
  const native = jest.requireMock('../omiNative') as {
    omiBackend: {request: jest.Mock} | null;
  };
  const previous = native.omiBackend;
  native.omiBackend = null;
  try {
    const renderer = renderDesktop();
    await act(async () => {
      renderer.root
        .find(node => node.props.accessibilityLabel === 'Settings')
        .props.onPress();
      await Promise.resolve();
      await Promise.resolve();
    });
    act(() => {
      renderer.root
        .find(node => node.props.accessibilityLabel === 'Account & Plan')
        .props.onPress();
    });
    const account = renderedText(renderer);
    expect(account).toContain(desktopBackendConfigurationCopy);
    expect(account).not.toContain('Loading account…');
    expect(account).not.toContain('Loading plan…');
    act(() => {
      renderer.root
        .find(node => node.props.accessibilityLabel === 'Alerts & Privacy')
        .props.onPress();
    });
    const alerts = renderedText(renderer);
    expect(alerts).toContain(desktopBackendConfigurationCopy);
    expect(alerts).not.toContain('Loading recording storage…');
    expect(alerts).not.toContain('Loading private cloud sync…');
    expect(alerts).not.toContain('Loading training data…');
    expect(
      renderer.root.findAll(node => node.props.accessibilityLabel === 'Update'),
    ).toHaveLength(0);
    expect(
      renderer.root.findAll(node => node.props.accessibilityLabel === 'Opt in'),
    ).toHaveLength(0);
    act(() => {
      renderer.root
        .find(node => node.props.accessibilityLabel === 'AI & Automation')
        .props.onPress();
    });
    const automation = renderedText(renderer);
    expect(automation).toContain(desktopBackendConfigurationCopy);
    expect(automation).not.toContain('Loading developer webhooks…');
  } finally {
    native.omiBackend = previous;
  }
});

test('Settings reports a nested non-retryable recording-storage read as unavailable', async () => {
  const {loadAccountSettings} = jest.requireMock('../desktopCloudClient') as {
    loadAccountSettings: jest.Mock;
  };
  loadAccountSettings.mockResolvedValueOnce({
    profile: null,
    profileError: null,
    subscription: null,
    subscriptionError: null,
    storeRecordingPermission: null,
    storeRecordingError: desktopAccountSettingUnavailableCopy,
    trainingOptedIn: null,
    trainingError: desktopAccountSettingUnavailableCopy,
    privateCloudSync: null,
    privateCloudSyncError: desktopAccountSettingUnavailableCopy,
    webhooks: null,
    webhooksError: null,
  });
  const renderer = renderDesktop();
  await act(async () => {
    renderer.root
      .find(node => node.props.accessibilityLabel === 'Settings')
      .props.onPress();
    await Promise.resolve();
    await Promise.resolve();
  });
  act(() => {
    renderer.root
      .find(node => node.props.accessibilityLabel === 'Alerts & Privacy')
      .props.onPress();
  });
  expect(renderedText(renderer)).toContain(
    desktopAccountSettingUnavailableCopy,
  );
  expect(renderedText(renderer)).not.toContain(
    'Cloud recording storage status is unavailable.',
  );
  expect(renderedText(renderer)).not.toContain(
    'Private cloud sync status is unavailable.',
  );
  expect(renderedText(renderer)).not.toContain(
    'Training opt-in is unavailable.',
  );
  expect(
    renderer.root.findAll(node => node.props.accessibilityLabel === 'Update'),
  ).toHaveLength(0);
  expect(
    renderer.root.findAll(node => node.props.accessibilityLabel === 'Opt in'),
  ).toHaveLength(0);
});

test('nested non-retryable account setting writes omit Try again', async () => {
  const {loadAccountSettings, setStoreRecordingPermission} = jest.requireMock(
    '../desktopCloudClient',
  ) as {
    loadAccountSettings: jest.Mock;
    setStoreRecordingPermission: jest.Mock;
  };
  loadAccountSettings.mockResolvedValue({
    profile: null,
    profileError: null,
    subscription: null,
    subscriptionError: null,
    storeRecordingPermission: false,
    storeRecordingError: null,
    trainingOptedIn: false,
    trainingError: null,
    privateCloudSync: false,
    privateCloudSyncError: null,
    webhooks: null,
    webhooksError: null,
  });
  setStoreRecordingPermission.mockRejectedValueOnce(
    Object.assign(new Error(desktopAccountSettingUnavailableCopy), {
      retryable: false,
    }),
  );
  const renderer = renderDesktop();
  await act(async () => {
    renderer.root
      .find(node => node.props.accessibilityLabel === 'Settings')
      .props.onPress();
    await Promise.resolve();
    await Promise.resolve();
  });
  act(() => {
    renderer.root
      .find(node => node.props.accessibilityLabel === 'Alerts & Privacy')
      .props.onPress();
  });
  await act(async () => {
    renderer.root
      .findAll(node => node.props.accessibilityLabel === 'Update')[0]!
      .props.onPress();
    await Promise.resolve();
    await Promise.resolve();
  });
  expect(renderedText(renderer)).toContain(
    desktopAccountSettingUnavailableCopy,
  );
  expect(renderedText(renderer)).not.toContain(
    'Settings change could not be saved. Try again.',
  );
  expect(
    renderer.root.findAll(
      node =>
        node.props.accessibilityLabel === 'Update' &&
        node.props.disabled === true,
    ),
  ).toHaveLength(0);
  expect(
    renderer.root.find(node => node.props.accessibilityLabel === 'Opt in').props
      .disabled,
  ).toBe(false);
});

test('nested non-retryable training opt-in writes omit Try again', async () => {
  const {loadAccountSettings, optInTrainingData} = jest.requireMock(
    '../desktopCloudClient',
  ) as {
    loadAccountSettings: jest.Mock;
    optInTrainingData: jest.Mock;
  };
  loadAccountSettings.mockResolvedValue({
    profile: null,
    profileError: null,
    subscription: null,
    subscriptionError: null,
    storeRecordingPermission: null,
    storeRecordingError: null,
    trainingOptedIn: false,
    trainingError: null,
    privateCloudSync: null,
    privateCloudSyncError: null,
    webhooks: null,
    webhooksError: null,
  });
  optInTrainingData.mockRejectedValueOnce(
    Object.assign(new Error(desktopAccountSettingUnavailableCopy), {
      retryable: false,
    }),
  );
  const renderer = renderDesktop();
  await act(async () => {
    renderer.root
      .find(node => node.props.accessibilityLabel === 'Settings')
      .props.onPress();
    await Promise.resolve();
    await Promise.resolve();
  });
  act(() => {
    renderer.root
      .find(node => node.props.accessibilityLabel === 'Alerts & Privacy')
      .props.onPress();
  });
  await act(async () => {
    renderer.root
      .find(node => node.props.accessibilityLabel === 'Opt in')
      .props.onPress();
    await Promise.resolve();
    await Promise.resolve();
  });
  expect(renderedText(renderer)).toContain(
    desktopAccountSettingUnavailableCopy,
  );
  expect(renderedText(renderer)).not.toContain(
    'Settings change could not be saved. Try again.',
  );
  expect(
    renderer.root.findAll(
      node =>
        node.props.accessibilityLabel === 'Opt in' &&
        node.props.accessibilityRole === 'button',
    ),
  ).toHaveLength(0);
});

test('Settings AI does not claim developer webhooks unavailable while account is loading', async () => {
  const {loadAccountSettings} = jest.requireMock('../desktopCloudClient') as {
    loadAccountSettings: jest.Mock;
  };
  loadAccountSettings.mockReturnValueOnce(new Promise(() => {}));
  const renderer = renderDesktop();
  await act(async () => {
    renderer.root
      .find(node => node.props.accessibilityLabel === 'Settings')
      .props.onPress();
    await Promise.resolve();
  });
  act(() => {
    renderer.root
      .find(node => node.props.accessibilityLabel === 'AI & Automation')
      .props.onPress();
  });
  expect(renderedText(renderer)).toContain('Loading developer webhooks…');
  expect(renderedText(renderer)).not.toContain(
    'Developer webhook status is unavailable.',
  );
  expect(renderedText(renderer)).not.toContain(
    'No developer webhooks were returned.',
  );
});

test('Settings reports a nested non-retryable webhook read as unavailable', async () => {
  const {loadAccountSettings} = jest.requireMock('../desktopCloudClient') as {
    loadAccountSettings: jest.Mock;
  };
  loadAccountSettings.mockResolvedValueOnce({
    profile: null,
    profileError: null,
    subscription: null,
    subscriptionError: null,
    storeRecordingPermission: null,
    storeRecordingError: null,
    trainingOptedIn: null,
    trainingError: null,
    privateCloudSync: null,
    privateCloudSyncError: null,
    webhooks: null,
    webhooksError: desktopAccountSettingUnavailableCopy,
  });
  const renderer = renderDesktop();
  await act(async () => {
    renderer.root
      .find(node => node.props.accessibilityLabel === 'Settings')
      .props.onPress();
    await Promise.resolve();
    await Promise.resolve();
  });
  act(() => {
    renderer.root
      .find(node => node.props.accessibilityLabel === 'AI & Automation')
      .props.onPress();
  });
  expect(renderedText(renderer)).toContain(
    desktopAccountSettingUnavailableCopy,
  );
  expect(renderedText(renderer)).not.toContain(
    'Developer webhook status is unavailable.',
  );
  expect(renderedText(renderer)).not.toContain(
    'No developer webhooks were returned.',
  );
});

test('Settings keeps an honest empty developer webhook catalogue', async () => {
  const {loadAccountSettings} = jest.requireMock('../desktopCloudClient') as {
    loadAccountSettings: jest.Mock;
  };
  const {omiBackend} = jest.requireMock('../omiNative') as {
    omiBackend: {request: jest.Mock};
  };
  omiBackend.request.mockImplementation(async request => {
    return {id: request.id, status: 404, body: null};
  });
  loadAccountSettings.mockResolvedValueOnce({
    profile: null,
    profileError: null,
    subscription: null,
    subscriptionError: null,
    storeRecordingPermission: null,
    storeRecordingError: null,
    trainingOptedIn: null,
    trainingError: null,
    privateCloudSync: null,
    privateCloudSyncError: null,
    webhooks: [],
    webhooksError: null,
  });
  const renderer = renderDesktop();
  await act(async () => {
    renderer.root
      .find(node => node.props.accessibilityLabel === 'Settings')
      .props.onPress();
    await Promise.resolve();
    await Promise.resolve();
  });
  act(() => {
    renderer.root
      .find(node => node.props.accessibilityLabel === 'AI & Automation')
      .props.onPress();
  });
  expect(renderedText(renderer)).toContain(
    'No developer webhooks were returned.',
  );
  expect(renderedText(renderer)).not.toContain('New conversation created');
  expect(renderedText(renderer)).not.toContain('Transcript received');
  expect(renderedText(renderer)).not.toContain(
    'Developer webhook status is unavailable.',
  );
});

test('Settings developer webhook titles are not raw API keys', async () => {
  const {loadAccountSettings} = jest.requireMock('../desktopCloudClient') as {
    loadAccountSettings: jest.Mock;
  };
  const {omiBackend} = jest.requireMock('../omiNative') as {
    omiBackend: {request: jest.Mock};
  };
  omiBackend.request.mockImplementation(async request => {
    return {id: request.id, status: 404, body: null};
  });
  loadAccountSettings.mockResolvedValueOnce({
    profile: null,
    profileError: null,
    subscription: null,
    subscriptionError: null,
    storeRecordingPermission: null,
    storeRecordingError: null,
    trainingOptedIn: null,
    trainingError: null,
    privateCloudSync: null,
    privateCloudSyncError: null,
    webhooks: [
      {
        type: 'memory_created',
        enabled: true,
        url: 'https://example.test/conversation',
      },
      {
        type: 'realtime_transcript',
        enabled: false,
        url: null,
      },
      {
        type: 'button_event',
        enabled: null,
        url: 'https://example.test/button',
      },
    ],
    webhooksError: null,
  });
  const renderer = renderDesktop();
  await act(async () => {
    renderer.root
      .find(node => node.props.accessibilityLabel === 'Settings')
      .props.onPress();
    await Promise.resolve();
    await Promise.resolve();
  });
  act(() => {
    renderer.root
      .find(node => node.props.accessibilityLabel === 'AI & Automation')
      .props.onPress();
  });
  const tree = renderedText(renderer);
  expect(tree).toContain('Conversation Events');
  expect(tree).toContain('Real-time Transcript');
  expect(tree).toContain('Enabled');
  expect(tree).toContain('Disabled');
  expect(tree).toContain('Status unavailable');
  expect(tree).not.toContain('Status unknown');
  expect(tree).toContain('New conversation created');
  expect(tree).toContain('Transcript received');
  expect(tree).not.toContain('memory_created');
  expect(tree).not.toContain('realtime_transcript');
});

test('Settings developer webhook URLs omit empty or whitespace values', async () => {
  const {loadAccountSettings} = jest.requireMock('../desktopCloudClient') as {
    loadAccountSettings: jest.Mock;
  };
  const {omiBackend} = jest.requireMock('../omiNative') as {
    omiBackend: {request: jest.Mock};
  };
  omiBackend.request.mockImplementation(async request => {
    return {id: request.id, status: 404, body: null};
  });
  loadAccountSettings.mockResolvedValueOnce({
    profile: null,
    profileError: null,
    subscription: null,
    subscriptionError: null,
    storeRecordingPermission: null,
    storeRecordingError: null,
    trainingOptedIn: null,
    trainingError: null,
    privateCloudSync: null,
    privateCloudSyncError: null,
    webhooks: [
      {type: 'memory_created', enabled: true, url: ' \t\n'},
      {
        type: 'day_summary',
        enabled: false,
        url: '  https://example.test/day  ',
      },
    ],
    webhooksError: null,
  });
  const renderer = renderDesktop();
  await act(async () => {
    renderer.root
      .find(node => node.props.accessibilityLabel === 'Settings')
      .props.onPress();
    await Promise.resolve();
    await Promise.resolve();
  });
  act(() => {
    renderer.root
      .find(node => node.props.accessibilityLabel === 'AI & Automation')
      .props.onPress();
  });
  const tree = renderedText(renderer);
  expect(tree).toContain('Enabled');
  expect(tree).toContain('Disabled');
  expect(tree).toContain('https://example.test/day');
  expect(tree).not.toContain(' \t\n');
});

test('Settings names GET developer webhook URLs without enable writes', async () => {
  const {loadAccountSettings} = jest.requireMock('../desktopCloudClient') as {
    loadAccountSettings: jest.Mock;
  };
  const {omiBackend} = jest.requireMock('../omiNative') as {
    omiBackend: {request: jest.Mock};
  };
  loadAccountSettings.mockResolvedValueOnce({
    profile: null,
    profileError: null,
    subscription: null,
    subscriptionError: null,
    storeRecordingPermission: null,
    storeRecordingError: null,
    trainingOptedIn: null,
    trainingError: null,
    privateCloudSync: null,
    privateCloudSyncError: null,
    webhooks: [
      {type: 'memory_created', enabled: true, url: null},
      {type: 'realtime_transcript', enabled: false, url: null},
      {type: 'audio_bytes', enabled: true, url: null},
      {type: 'day_summary', enabled: true, url: null},
    ],
    webhooksError: null,
  });
  omiBackend.request.mockImplementation(async request => {
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
  const renderer = renderDesktop();
  await act(async () => {
    renderer.root
      .find(node => node.props.accessibilityLabel === 'Settings')
      .props.onPress();
    await Promise.resolve();
    await Promise.resolve();
  });
  act(() => {
    renderer.root
      .find(node => node.props.accessibilityLabel === 'AI & Automation')
      .props.onPress();
  });
  const tree = renderedText(renderer);
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
  expect(
    omiBackend.request.mock.calls.some(call => call[0].method === 'POST'),
  ).toBe(false);
  expect(
    omiBackend.request.mock.calls.some(
      call => call[0].path === '/v1/users/developer/webhook/button_event',
    ),
  ).toBe(false);
});

test('Settings names a failed developer webhook URLs GET instead of empty success', async () => {
  const {loadAccountSettings} = jest.requireMock('../desktopCloudClient') as {
    loadAccountSettings: jest.Mock;
  };
  const {omiBackend} = jest.requireMock('../omiNative') as {
    omiBackend: {request: jest.Mock};
  };
  loadAccountSettings.mockResolvedValueOnce({
    profile: null,
    profileError: null,
    subscription: null,
    subscriptionError: null,
    storeRecordingPermission: null,
    storeRecordingError: null,
    trainingOptedIn: null,
    trainingError: null,
    privateCloudSync: null,
    privateCloudSyncError: null,
    webhooks: [
      {type: 'memory_created', enabled: true, url: null},
      {type: 'realtime_transcript', enabled: false, url: null},
      {type: 'audio_bytes', enabled: true, url: null},
      {type: 'day_summary', enabled: true, url: null},
    ],
    webhooksError: null,
  });
  omiBackend.request.mockImplementation(async request => {
    if (request.path.startsWith('/v1/users/developer/webhook/')) {
      throw Object.assign(new Error('lost'), {code: 'OMI_HTTP_TRANSPORT'});
    }
    return {id: request.id, status: 404, body: null};
  });
  const renderer = renderDesktop();
  await act(async () => {
    renderer.root
      .find(node => node.props.accessibilityLabel === 'Settings')
      .props.onPress();
    await Promise.resolve();
    await Promise.resolve();
  });
  act(() => {
    renderer.root
      .find(node => node.props.accessibilityLabel === 'AI & Automation')
      .props.onPress();
  });
  const tree = renderedText(renderer);
  expect(tree).toContain('Webhooks');
  expect(tree).not.toContain('Developer Webhooks');
  expect(tree).toContain(desktopBackendServiceCopy);
  expect(tree).not.toContain('https://example.test/conversation');
  expect(
    omiBackend.request.mock.calls.some(call => call[0].method === 'POST'),
  ).toBe(false);
  expect(
    omiBackend.request.mock.calls.some(
      call => call[0].path === '/v1/users/developer/webhook/button_event',
    ),
  ).toBe(false);
});

test('Settings names GET developer and MCP keys without revoke or a full secret', async () => {
  const {loadAccountSettings} = jest.requireMock('../desktopCloudClient') as {
    loadAccountSettings: jest.Mock;
  };
  const {omiBackend} = jest.requireMock('../omiNative') as {
    omiBackend: {request: jest.Mock};
  };
  loadAccountSettings.mockResolvedValueOnce({
    profile: null,
    profileError: null,
    subscription: null,
    subscriptionError: null,
    storeRecordingPermission: null,
    storeRecordingError: null,
    trainingOptedIn: null,
    trainingError: null,
    privateCloudSync: null,
    privateCloudSyncError: null,
    webhooks: [],
    webhooksError: null,
  });
  omiBackend.request.mockImplementation(async request => {
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
  const renderer = renderDesktop();
  await act(async () => {
    renderer.root
      .find(node => node.props.accessibilityLabel === 'Settings')
      .props.onPress();
    await Promise.resolve();
    await Promise.resolve();
  });
  act(() => {
    renderer.root
      .find(node => node.props.accessibilityLabel === 'AI & Automation')
      .props.onPress();
  });
  const tree = renderedText(renderer);
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
  expect(
    omiBackend.request.mock.calls.some(
      call => call[0].method === 'POST' || call[0].method === 'DELETE',
    ),
  ).toBe(false);
});

test('Settings names Flutter McpApiKeyListItem empty GET keyPrefix without omitting MCP', async () => {
  const {loadAccountSettings} = jest.requireMock('../desktopCloudClient') as {
    loadAccountSettings: jest.Mock;
  };
  const {omiBackend} = jest.requireMock('../omiNative') as {
    omiBackend: {request: jest.Mock};
  };
  loadAccountSettings.mockResolvedValueOnce({
    profile: null,
    profileError: null,
    subscription: null,
    subscriptionError: null,
    storeRecordingPermission: null,
    storeRecordingError: null,
    trainingOptedIn: null,
    trainingError: null,
    privateCloudSync: null,
    privateCloudSyncError: null,
    webhooks: [],
    webhooksError: null,
  });
  omiBackend.request.mockImplementation(async request => {
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
  const renderer = renderDesktop();
  await act(async () => {
    renderer.root
      .find(node => node.props.accessibilityLabel === 'Settings')
      .props.onPress();
    await Promise.resolve();
    await Promise.resolve();
  });
  act(() => {
    renderer.root
      .find(node => node.props.accessibilityLabel === 'AI & Automation')
      .props.onPress();
  });
  const tree = renderedText(renderer);
  expect(tree).toContain('MCP');
  expect(tree).toContain('Cursor \u00b7 ');
  expect(tree).toContain('Whitespace prefix \u00b7 ');
  expect(tree).not.toContain('mcp-empty');
  expect(tree).not.toContain('***');
  expect(tree).not.toContain('No API keys yet');
  expect(tree).not.toContain('Revoke');
  expect(tree).not.toContain('Create Key');
});

test('Settings names Flutter DevApiKeyListItem empty GET names without noApiKeys', async () => {
  const {loadAccountSettings} = jest.requireMock('../desktopCloudClient') as {
    loadAccountSettings: jest.Mock;
  };
  const {omiBackend} = jest.requireMock('../omiNative') as {
    omiBackend: {request: jest.Mock};
  };
  loadAccountSettings.mockResolvedValueOnce({
    profile: null,
    profileError: null,
    subscription: null,
    subscriptionError: null,
    storeRecordingPermission: null,
    storeRecordingError: null,
    trainingOptedIn: null,
    trainingError: null,
    privateCloudSync: null,
    privateCloudSyncError: null,
    webhooks: [],
    webhooksError: null,
  });
  omiBackend.request.mockImplementation(async request => {
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
  const renderer = renderDesktop();
  await act(async () => {
    renderer.root
      .find(node => node.props.accessibilityLabel === 'Settings')
      .props.onPress();
    await Promise.resolve();
    await Promise.resolve();
  });
  act(() => {
    renderer.root
      .find(node => node.props.accessibilityLabel === 'AI & Automation')
      .props.onPress();
  });
  const tree = renderedText(renderer);
  expect(tree).toContain('Developer API');
  expect(tree).toContain(' \u00b7 omi_sk_cd***');
  expect(tree).not.toContain('key-empty');
  expect(tree).toContain('MCP');
  expect(tree).toContain(' \u00b7 omi_mcp_cd');
  expect(tree).not.toContain('omi_mcp_cd***');
  expect(tree).not.toContain('mcp-empty');
  expect(tree).not.toContain('No API keys yet');
  expect(tree).not.toContain('Revoke');
  expect(tree).not.toContain('Create Key');
});

test('Settings names GET developer-key empty scopes Read Only without inventing it on MCP keys', async () => {
  const {loadAccountSettings} = jest.requireMock('../desktopCloudClient') as {
    loadAccountSettings: jest.Mock;
  };
  const {omiBackend} = jest.requireMock('../omiNative') as {
    omiBackend: {request: jest.Mock};
  };
  loadAccountSettings.mockResolvedValueOnce({
    profile: null,
    profileError: null,
    subscription: null,
    subscriptionError: null,
    storeRecordingPermission: null,
    storeRecordingError: null,
    trainingOptedIn: null,
    trainingError: null,
    privateCloudSync: null,
    privateCloudSyncError: null,
    webhooks: [],
    webhooksError: null,
  });
  omiBackend.request.mockImplementation(async request => {
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
  const renderer = renderDesktop();
  await act(async () => {
    renderer.root
      .find(node => node.props.accessibilityLabel === 'Settings')
      .props.onPress();
    await Promise.resolve();
    await Promise.resolve();
  });
  act(() => {
    renderer.root
      .find(node => node.props.accessibilityLabel === 'AI & Automation')
      .props.onPress();
  });
  const tree = renderedText(renderer);
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
  const {loadAccountSettings} = jest.requireMock('../desktopCloudClient') as {
    loadAccountSettings: jest.Mock;
  };
  const {omiBackend} = jest.requireMock('../omiNative') as {
    omiBackend: {request: jest.Mock};
  };
  loadAccountSettings.mockResolvedValueOnce({
    profile: {
      uid: 'user-1',
      name: 'Ada',
      email: 'ada@example.com',
      company: null,
      job: null,
      dataProtectionLevel: null,
    },
    profileError: null,
    subscription: {
      plan: 'plus',
      status: 'active',
      transcriptionSecondsUsed: null,
      transcriptionSecondsLimit: null,
    },
    subscriptionError: null,
    storeRecordingPermission: null,
    storeRecordingError: null,
    trainingOptedIn: null,
    trainingError: null,
    privateCloudSync: null,
    privateCloudSyncError: null,
    webhooks: [],
    webhooksError: null,
    usage: null,
    usageError: null,
    language: null,
    languageError: null,
    languageNames: null,
    languageNamesError: null,
  });
  omiBackend.request.mockImplementation(async request => {
    if (request.path === '/v1/dev/keys' || request.path === '/v1/mcp/keys') {
      throw Object.assign(new Error('lost'), {code: 'OMI_HTTP_TRANSPORT'});
    }
    return {id: request.id, status: 404, body: null};
  });
  const renderer = renderDesktop();
  await act(async () => {
    renderer.root
      .find(node => node.props.accessibilityLabel === 'Settings')
      .props.onPress();
    await Promise.resolve();
    await Promise.resolve();
  });
  act(() => {
    renderer.root
      .find(node => node.props.accessibilityLabel === 'AI & Automation')
      .props.onPress();
  });
  const tree = renderedText(renderer);
  expect(tree).toContain('Developer API');
  expect(tree).not.toContain('Developer key');
  expect(tree).toContain('MCP');
  expect(tree).not.toContain('MCP key');
  expect(tree).toContain(desktopBackendServiceCopy);
  expect(tree).not.toContain('omi_sk_abcdef_secret');
  expect(tree).not.toContain('Revoke');
  expect(tree).not.toContain('No API keys yet');
});

test('Settings names HTTP 500 developer and MCP keys GET instead of empty success', async () => {
  const {loadAccountSettings} = jest.requireMock('../desktopCloudClient') as {
    loadAccountSettings: jest.Mock;
  };
  const {omiBackend} = jest.requireMock('../omiNative') as {
    omiBackend: {request: jest.Mock};
  };
  loadAccountSettings.mockResolvedValueOnce({
    profile: {
      uid: 'user-1',
      name: 'Ada',
      email: 'ada@example.com',
      company: null,
      job: null,
      dataProtectionLevel: null,
    },
    profileError: null,
    subscription: {
      plan: 'plus',
      status: 'active',
      transcriptionSecondsUsed: null,
      transcriptionSecondsLimit: null,
    },
    subscriptionError: null,
    storeRecordingPermission: null,
    storeRecordingError: null,
    trainingOptedIn: null,
    trainingError: null,
    privateCloudSync: null,
    privateCloudSyncError: null,
    webhooks: [],
    webhooksError: null,
    usage: null,
    usageError: null,
    language: null,
    languageError: null,
    languageNames: null,
    languageNamesError: null,
  });
  omiBackend.request.mockImplementation(async request => {
    if (request.path === '/v1/dev/keys' || request.path === '/v1/mcp/keys') {
      return {id: request.id, status: 500, body: '{"error":"internal"}'};
    }
    return {id: request.id, status: 404, body: null};
  });
  const renderer = renderDesktop();
  await act(async () => {
    renderer.root
      .find(node => node.props.accessibilityLabel === 'Settings')
      .props.onPress();
    await Promise.resolve();
    await Promise.resolve();
  });
  act(() => {
    renderer.root
      .find(node => node.props.accessibilityLabel === 'AI & Automation')
      .props.onPress();
  });
  const tree = renderedText(renderer);
  expect(tree).toContain('Developer API');
  expect(tree).not.toContain('Developer key');
  expect(tree).toContain('MCP');
  expect(tree).not.toContain('MCP key');
  expect(tree).toContain(
    desktopReadErrorCopy(new Error('Omi developer keys are malformed')),
  );
  expect(tree).not.toContain('omi_sk_abcdef_secret');
  expect(tree).not.toContain('Revoke');
  expect(tree).not.toContain('No API keys yet');
});

test('Settings names Flutter DevApiKey fromJson invalid created_at instead of undated success', async () => {
  const {loadAccountSettings} = jest.requireMock('../desktopCloudClient') as {
    loadAccountSettings: jest.Mock;
  };
  const {omiBackend} = jest.requireMock('../omiNative') as {
    omiBackend: {request: jest.Mock};
  };
  loadAccountSettings.mockResolvedValueOnce({
    profile: {
      uid: 'user-1',
      name: 'Ada',
      email: 'ada@example.com',
      company: null,
      job: null,
      dataProtectionLevel: null,
    },
    profileError: null,
    subscription: {
      plan: 'plus',
      status: 'active',
      transcriptionSecondsUsed: null,
      transcriptionSecondsLimit: null,
    },
    subscriptionError: null,
    storeRecordingPermission: null,
    storeRecordingError: null,
    trainingOptedIn: null,
    trainingError: null,
    privateCloudSync: null,
    privateCloudSyncError: null,
    webhooks: [],
    webhooksError: null,
    usage: null,
    usageError: null,
    language: null,
    languageError: null,
    languageNames: null,
    languageNamesError: null,
  });
  omiBackend.request.mockImplementation(async request => {
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
  const renderer = renderDesktop();
  await act(async () => {
    renderer.root
      .find(node => node.props.accessibilityLabel === 'Settings')
      .props.onPress();
    await Promise.resolve();
    await Promise.resolve();
  });
  act(() => {
    renderer.root
      .find(node => node.props.accessibilityLabel === 'AI & Automation')
      .props.onPress();
  });
  const tree = renderedText(renderer);
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
  const {loadAccountSettings} = jest.requireMock('../desktopCloudClient') as {
    loadAccountSettings: jest.Mock;
  };
  const {omiBackend} = jest.requireMock('../omiNative') as {
    omiBackend: {request: jest.Mock};
  };
  loadAccountSettings.mockResolvedValueOnce({
    profile: {
      uid: 'user-1',
      name: 'Ada',
      email: 'ada@example.com',
      company: null,
      job: null,
      dataProtectionLevel: null,
    },
    profileError: null,
    subscription: {
      plan: 'plus',
      status: 'active',
      transcriptionSecondsUsed: null,
      transcriptionSecondsLimit: null,
    },
    subscriptionError: null,
    storeRecordingPermission: null,
    storeRecordingError: null,
    trainingOptedIn: null,
    trainingError: null,
    privateCloudSync: null,
    privateCloudSyncError: null,
    webhooks: [],
    webhooksError: null,
    usage: null,
    usageError: null,
    language: null,
    languageError: null,
    languageNames: null,
    languageNamesError: null,
  });
  omiBackend.request.mockImplementation(async request => {
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
  const renderer = renderDesktop();
  await act(async () => {
    renderer.root
      .find(node => node.props.accessibilityLabel === 'Settings')
      .props.onPress();
    await Promise.resolve();
    await Promise.resolve();
  });
  act(() => {
    renderer.root
      .find(node => node.props.accessibilityLabel === 'AI & Automation')
      .props.onPress();
  });
  const tree = renderedText(renderer);
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

test('Settings names Flutter noApiKeys for empty GET developer and MCP keys', async () => {
  const {omiBackend} = jest.requireMock('../omiNative') as {
    omiBackend: {request: jest.Mock};
  };
  omiBackend.request.mockImplementation(async (request: {path?: string}) => {
    if (request.path === '/v1/dev/keys' || request.path === '/v1/mcp/keys') {
      return {id: 'keys', status: 200, body: JSON.stringify([])};
    }
    return {id: 'other', status: 404, body: null};
  });
  const renderer = renderDesktop();
  await act(async () => {
    renderer.root
      .find(node => node.props.accessibilityLabel === 'Settings')
      .props.onPress();
    await Promise.resolve();
    await Promise.resolve();
  });
  act(() => {
    renderer.root
      .find(node => node.props.accessibilityLabel === 'AI & Automation')
      .props.onPress();
  });
  const tree = renderedText(renderer);
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
  const {omiBackend} = jest.requireMock('../omiNative') as {
    omiBackend: {request: jest.Mock};
  };
  omiBackend.request.mockImplementation(async (request: {path?: string}) => ({
    id: request.id ?? 'other',
    status: 404,
    body: null,
  }));
  const renderer = renderDesktop();
  await act(async () => {
    renderer.root
      .find(node => node.props.accessibilityLabel === 'Settings')
      .props.onPress();
    await Promise.resolve();
    await Promise.resolve();
  });
  act(() => {
    renderer.root
      .find(node => node.props.accessibilityLabel === 'AI & Automation')
      .props.onPress();
  });
  const tree = renderedText(renderer);
  expect(tree).toContain('Developer API');
  expect(tree).toContain('MCP');
  expect(tree).toContain(
    desktopReadErrorCopy(new Error('Omi developer keys are malformed')),
  );
  expect(tree).not.toContain('No API keys yet');
  expect(tree).not.toContain('Revoke');
});

test('Settings names GET import jobs without Start import or Limitless', async () => {
  const {loadAccountSettings} = jest.requireMock('../desktopCloudClient') as {
    loadAccountSettings: jest.Mock;
  };
  const {omiBackend} = jest.requireMock('../omiNative') as {
    omiBackend: {request: jest.Mock};
  };
  loadAccountSettings.mockResolvedValueOnce({
    profile: null,
    profileError: null,
    subscription: null,
    subscriptionError: null,
    storeRecordingPermission: null,
    storeRecordingError: null,
    trainingOptedIn: null,
    trainingError: null,
    privateCloudSync: null,
    privateCloudSyncError: null,
    webhooks: [],
    webhooksError: null,
  });
  omiBackend.request.mockImplementation(async request => {
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
  const renderer = renderDesktop();
  await act(async () => {
    renderer.root
      .find(node => node.props.accessibilityLabel === 'Settings')
      .props.onPress();
    await Promise.resolve();
    await Promise.resolve();
  });
  act(() => {
    renderer.root
      .find(node => node.props.accessibilityLabel === 'AI & Automation')
      .props.onPress();
  });
  const tree = renderedText(renderer);
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
  expect(omiBackend.request).toHaveBeenCalledWith({
    id: expect.any(String),
    method: 'GET',
    expectedApiContract: 'omi',
    path: '/v1/import/jobs?limit=50',
  });
  expect(
    omiBackend.request.mock.calls.some(
      call => call[0].method === 'POST' || call[0].method === 'DELETE',
    ),
  ).toBe(false);
  expect(
    omiBackend.request.mock.calls.some(call =>
      String(call[0].path).includes('limitless'),
    ),
  ).toBe(false);
});

test('Settings names a failed import jobs GET instead of empty success', async () => {
  const {loadAccountSettings} = jest.requireMock('../desktopCloudClient') as {
    loadAccountSettings: jest.Mock;
  };
  const {omiBackend} = jest.requireMock('../omiNative') as {
    omiBackend: {request: jest.Mock};
  };
  loadAccountSettings.mockResolvedValueOnce({
    profile: {
      uid: 'user-1',
      name: 'Ada',
      email: 'ada@example.com',
      company: null,
      job: null,
      dataProtectionLevel: null,
    },
    profileError: null,
    subscription: {
      plan: 'plus',
      status: 'active',
      transcriptionSecondsUsed: null,
      transcriptionSecondsLimit: null,
    },
    subscriptionError: null,
    storeRecordingPermission: null,
    storeRecordingError: null,
    trainingOptedIn: null,
    trainingError: null,
    privateCloudSync: null,
    privateCloudSyncError: null,
    webhooks: [],
    webhooksError: null,
    usage: null,
    usageError: null,
    language: null,
    languageError: null,
    languageNames: null,
    languageNamesError: null,
  });
  omiBackend.request.mockImplementation(async request => {
    if (request.path === '/v1/import/jobs?limit=50') {
      throw Object.assign(new Error('lost'), {code: 'OMI_HTTP_TRANSPORT'});
    }
    return {id: request.id, status: 404, body: null};
  });
  const renderer = renderDesktop();
  await act(async () => {
    renderer.root
      .find(node => node.props.accessibilityLabel === 'Settings')
      .props.onPress();
    await Promise.resolve();
    await Promise.resolve();
  });
  act(() => {
    renderer.root
      .find(node => node.props.accessibilityLabel === 'AI & Automation')
      .props.onPress();
  });
  const tree = renderedText(renderer);
  expect(tree).toContain('Import Data');
  expect(tree).toContain(desktopBackendServiceCopy);
  expect(tree).not.toContain('job-1');
  expect(tree).not.toContain('No imports yet');
  expect(tree).not.toContain('Limitless');
});

test('Settings names Flutter ImportHistoryPage empty GET error without omitting Import Data', async () => {
  const {loadAccountSettings} = jest.requireMock('../desktopCloudClient') as {
    loadAccountSettings: jest.Mock;
  };
  const {omiBackend} = jest.requireMock('../omiNative') as {
    omiBackend: {request: jest.Mock};
  };
  loadAccountSettings.mockResolvedValueOnce({
    profile: null,
    profileError: null,
    subscription: null,
    subscriptionError: null,
    storeRecordingPermission: null,
    storeRecordingError: null,
    trainingOptedIn: null,
    trainingError: null,
    privateCloudSync: null,
    privateCloudSyncError: null,
    webhooks: [],
    webhooksError: null,
  });
  omiBackend.request.mockImplementation(async request => {
    if (request.path === '/v1/import/jobs?limit=50') {
      return {
        id: request.id,
        status: 200,
        body: JSON.stringify([
          {job_id: 'job-empty-error', status: 'failed', error: ''},
          {job_id: 'job-whitespace-error', status: 'failed', error: ' \t'},
          {job_id: 'job-omitted-error', status: 'failed'},
        ]),
      };
    }
    return {id: request.id, status: 404, body: null};
  });
  const renderer = renderDesktop();
  await act(async () => {
    renderer.root
      .find(node => node.props.accessibilityLabel === 'Settings')
      .props.onPress();
    await Promise.resolve();
    await Promise.resolve();
  });
  act(() => {
    renderer.root
      .find(node => node.props.accessibilityLabel === 'AI & Automation')
      .props.onPress();
  });
  const tree = renderedText(renderer);
  expect(tree).toContain('Import Data');
  expect(tree).toContain('Failed · ');
  expect(tree).toContain('Failed');
  expect(tree).not.toContain('job-empty-error');
  expect(tree).not.toContain('No imports yet');
  expect(tree).not.toContain('Limitless');
  expect(tree).not.toContain('Start import');
});

test('Settings names Flutter noImportsYet for empty GET import jobs', async () => {
  const {omiBackend} = jest.requireMock('../omiNative') as {
    omiBackend: {request: jest.Mock};
  };
  omiBackend.request.mockImplementation(async (request: {path?: string}) => {
    if (request.path === '/v1/import/jobs?limit=50') {
      return {id: 'jobs', status: 200, body: JSON.stringify([])};
    }
    return {id: 'other', status: 404, body: null};
  });
  const renderer = renderDesktop();
  await act(async () => {
    renderer.root
      .find(node => node.props.accessibilityLabel === 'Settings')
      .props.onPress();
    await Promise.resolve();
    await Promise.resolve();
  });
  act(() => {
    renderer.root
      .find(node => node.props.accessibilityLabel === 'AI & Automation')
      .props.onPress();
  });
  const tree = renderedText(renderer);
  expect(tree).toContain('Import Data');
  expect(tree).toContain('No imports yet');
  expect(tree).not.toContain(desktopBackendServiceCopy);
  expect(tree).not.toContain('Limitless');
});

test('desktop Tasks does not claim editing unavailable over a failed task read', () => {
  const renderer = renderDesktop({
    outcomes: {
      ...outcomes,
      tasks: {status: 'error', error: desktopBackendUnavailableCopy},
    },
  });
  act(() => {
    renderer.root
      .find(node => node.props.accessibilityLabel === 'Tasks')
      .props.onPress();
  });
  expect(renderedText(renderer)).toContain(desktopBackendUnavailableCopy);
  expect(renderedText(renderer)).not.toContain(
    'Task editing is unavailable for this connection.',
  );
});

test('desktop Tasks reports a closed write door after tasks load', () => {
  const renderer = renderDesktop({writesAvailable: false});
  act(() => {
    renderer.root
      .find(node => node.props.accessibilityLabel === 'Tasks')
      .props.onPress();
  });
  expect(renderedText(renderer)).toContain(
    'Task editing is unavailable for this connection.',
  );
  expect(
    renderer.root.find(
      node => node.props.accessibilityLabel === 'Task: Ship the desktop chrome',
    ).props.disabled,
  ).toBe(true);
  expect(
    renderer.root.findAll(
      node =>
        node.props.accessibilityLabel ===
        'Complete task: Ship the desktop chrome',
    ),
  ).toHaveLength(0);
});

test('actual desktop Tasks controls toggle and edit through shared mutation callbacks', () => {
  const onTaskToggle = jest.fn();
  const onTaskEdit = jest.fn();
  const renderer = renderDesktop({
    writesAvailable: true,
    onTaskToggle,
    onTaskEdit,
    outcomes: {
      ...outcomes,
      tasks: {
        ...outcomes.tasks,
        value: {
          ...outcomes.tasks.value,
          accountEpoch: 0,
          items: outcomes.tasks.value.items.map(item => ({
            ...item,
            revision: 'a'.repeat(64),
          })),
        },
      },
    },
  });
  act(() => {
    renderer.root
      .find(node => node.props.accessibilityLabel === 'Tasks')
      .props.onPress();
  });
  const toggle = renderer.root.find(
    node =>
      node.props.accessibilityLabel ===
      'Complete task: Ship the desktop chrome',
  );
  expect(toggle.props.accessibilityRole).toBe('checkbox');
  expect(toggle.props.disabled).toBe(false);
  act(() => {
    toggle.props.onPress();
  });
  expect(onTaskToggle).toHaveBeenCalledWith('task-1');
  act(() => {
    renderer.root
      .find(
        node =>
          node.props.accessibilityLabel ===
          'Edit task: Ship the desktop chrome',
      )
      .props.onPress();
  });
  act(() => {
    renderer.root
      .find(node => node.props.accessibilityLabel === 'Task description')
      .props.onChangeText('Ship the tested desktop task controls');
  });
  act(() => {
    renderer.root
      .find(node => node.props.accessibilityLabel === 'Save task description')
      .props.onPress();
  });
  expect(onTaskEdit).toHaveBeenCalledWith(
    'task-1',
    'Ship the tested desktop task controls',
  );
});

test('desktop task edits stay disabled during an unconfirmed pending mutation', () => {
  const onRetryTaskMutation = jest.fn();
  const renderer = renderDesktop({
    writesAvailable: true,
    onTaskToggle: jest.fn(),
    onTaskEdit: jest.fn(),
    busyTaskId: 'task-1',
    taskMutationError: 'Task edit could not be confirmed',
    onRetryTaskMutation,
  });
  act(() => {
    renderer.root
      .find(node => node.props.accessibilityLabel === 'Tasks')
      .props.onPress();
  });
  expect(
    renderer.root.find(
      node =>
        node.props.accessibilityLabel ===
        'Complete task: Ship the desktop chrome',
    ).props.disabled,
  ).toBe(true);
  expect(renderedText(renderer)).toContain('Task edit could not be confirmed');
  act(() => {
    renderer.root
      .find(node => node.props.accessibilityLabel === 'Retry task change')
      .props.onPress();
  });
  expect(onRetryTaskMutation).toHaveBeenCalledTimes(1);
});

test('desktop General settings mounts the live device composition slot', async () => {
  const renderer = renderDesktop({
    deviceContent: <Text>Live device controls</Text>,
  });
  expect(renderedText(renderer)).not.toContain('Live device controls');
  await act(async () => {
    renderer.root
      .find(node => node.props.accessibilityLabel === 'Settings')
      .props.onPress();
  });
  expect(renderedText(renderer)).toContain('Live device controls');
  await act(async () => renderer.unmount());
});

test('actual desktop task page exposes the shared pagination action', () => {
  const onLoadMore = jest.fn();
  const renderer = renderDesktop({
    taskPagination: (
      <TaskPagination
        hasMore
        busy={false}
        notice={null}
        onLoadMore={onLoadMore}
      />
    ),
  });
  act(() =>
    renderer.root
      .find(node => node.props.accessibilityLabel === 'Tasks')
      .props.onPress(),
  );
  act(() =>
    renderer.root
      .findAll(node => node.props.accessibilityLabel === 'Load more tasks')[0]!
      .props.onPress(),
  );
  expect(onLoadMore).toHaveBeenCalledTimes(1);
});

function pagedTaskOutcomes() {
  return {
    ...outcomes,
    tasks: {
      ...outcomes.tasks,
      value: {
        ...outcomes.tasks.value,
        page: {
          ...outcomes.tasks.value.page,
          hasMore: true,
          nextCursor: 'tasks-next',
          complete: false,
          windowStatus: 'more' as const,
        },
      },
    },
  };
}

test('actual desktop task page exposes Load more when more pages exist', () => {
  const onLoadMore = jest.fn();
  const renderer = renderDesktop({
    outcomes: pagedTaskOutcomes(),
    taskPagination: (
      <TaskPagination
        hasMore
        busy={false}
        notice={null}
        onLoadMore={onLoadMore}
      />
    ),
  });
  act(() =>
    renderer.root
      .find(node => node.props.accessibilityLabel === 'Tasks')
      .props.onPress(),
  );
  expect(renderedText(renderer)).toContain('More tasks are available.');
  expect(visibleButtonCopy(renderer, 'Load more tasks')).toEqual([
    'Load more tasks',
  ]);
  act(() =>
    renderer.root
      .find(node => node.props.accessibilityLabel === 'Load more tasks')
      .props.onPress(),
  );
  expect(onLoadMore).toHaveBeenCalledTimes(1);
});

test('nested non-retryable later task pages keep rows and omit Load more', () => {
  const renderer = renderDesktop({
    taskNotice: desktopBackendUnavailableCopy,
    outcomes: pagedTaskOutcomes(),
    taskPagination: (
      <TaskPagination
        hasMore={false}
        busy={false}
        notice={desktopBackendUnavailableCopy}
        onLoadMore={jest.fn()}
      />
    ),
  });
  act(() =>
    renderer.root
      .find(node => node.props.accessibilityLabel === 'Tasks')
      .props.onPress(),
  );
  const tree = renderedText(renderer);
  expect(tree).toContain('Ship the desktop chrome');
  expect(tree).toContain(desktopBackendUnavailableCopy);
  expect(
    renderer.root.findAll(
      node => node.props.accessibilityLabel === 'Load more tasks',
    ),
  ).toHaveLength(0);
  expect(tree).not.toContain('More tasks are available.');
});

test('generic later-page task failures keep Load more', () => {
  const onLoadMore = jest.fn();
  const renderer = renderDesktop({
    taskNotice: 'More tasks could not be loaded. Try again.',
    outcomes: pagedTaskOutcomes(),
    taskPagination: (
      <TaskPagination
        hasMore
        busy={false}
        notice="More tasks could not be loaded. Try again."
        onLoadMore={onLoadMore}
      />
    ),
  });
  act(() =>
    renderer.root
      .find(node => node.props.accessibilityLabel === 'Tasks')
      .props.onPress(),
  );
  expect(renderedText(renderer)).toContain(
    'More tasks could not be loaded. Try again.',
  );
  expect(renderedText(renderer)).toContain('More tasks are available.');
  expect(visibleButtonCopy(renderer, 'Load more tasks')).toEqual([
    'Load more tasks',
  ]);
});

function pagedConversationOutcomes() {
  return {
    ...outcomes,
    conversations: {
      ...outcomes.conversations,
      value: {
        ...outcomes.conversations.value,
        page: {
          ...outcomes.conversations.value.page,
          hasMore: true,
          nextCursor: 'conversations-next',
          complete: false,
          windowStatus: 'more' as const,
        },
      },
    },
  };
}

test('actual desktop conversation page exposes Load more when more pages exist', () => {
  const onLoadMoreConversations = jest.fn();
  const renderer = renderDesktop({
    onLoadMoreConversations,
    outcomes: pagedConversationOutcomes(),
  });
  act(() =>
    renderer.root
      .find(node => node.props.accessibilityLabel === 'Conversations')
      .props.onPress(),
  );
  expect(renderedText(renderer)).toContain('More conversations are available.');
  expect(visibleButtonCopy(renderer, 'Load more conversations')).toEqual([
    'Load more conversations',
  ]);
  act(() =>
    renderer.root
      .find(node => node.props.accessibilityLabel === 'Load more conversations')
      .props.onPress(),
  );
  expect(onLoadMoreConversations).toHaveBeenCalledTimes(1);
});

test('nested non-retryable later conversation pages keep rows and omit Load more', () => {
  const renderer = renderDesktop({
    conversationNotice: desktopBackendUnavailableCopy,
    outcomes: pagedConversationOutcomes(),
  });
  act(() =>
    renderer.root
      .find(node => node.props.accessibilityLabel === 'Conversations')
      .props.onPress(),
  );
  const tree = renderedText(renderer);
  expect(tree).toContain('Product review');
  expect(tree).toContain(desktopBackendUnavailableCopy);
  expect(
    renderer.root.findAll(
      node => node.props.accessibilityLabel === 'Load more conversations',
    ),
  ).toHaveLength(0);
  expect(tree).not.toContain('More conversations are available.');
});

test('generic later-page conversation failures keep Load more', () => {
  const onLoadMoreConversations = jest.fn();
  const renderer = renderDesktop({
    conversationNotice: 'More conversations could not be loaded. Try again.',
    onLoadMoreConversations,
    outcomes: pagedConversationOutcomes(),
  });
  act(() =>
    renderer.root
      .find(node => node.props.accessibilityLabel === 'Conversations')
      .props.onPress(),
  );
  expect(renderedText(renderer)).toContain(
    'More conversations could not be loaded. Try again.',
  );
  expect(visibleButtonCopy(renderer, 'Load more conversations')).toEqual([
    'Load more conversations',
  ]);
});

const homeMemory = {
  kind: 'memory' as const,
  id: 'memory-page-1',
  title: 'Prefers concise release notes',
  summary: 'Release notes should lead with the outcome.',
  searchableText: 'prefers concise release notes',
  citations: [] as string[],
  timestamp: 1788492408,
  provenance: {
    label: null,
    synthesisVersion: 'v1',
    inputDigest: 'input',
    outputDigest: 'output',
  },
};

function pagedMemoryOutcomes() {
  return {
    ...outcomes,
    memories: {
      status: 'success' as const,
      value: {
        items: [homeMemory],
        page: {
          ...outcomes.memories.value.page,
          hasMore: true,
          nextCursor: 'memories-next',
          complete: false,
          windowStatus: 'more' as const,
        },
      },
    },
  };
}

test('actual desktop Home exposes Load more memories when more memories exist', () => {
  const onLoadMoreMemories = jest.fn();
  const renderer = renderDesktop({
    onLoadMoreMemories,
    outcomes: pagedMemoryOutcomes(),
    reads: [...outcomes.conversations.value.items, homeMemory],
  });
  expect(renderedText(renderer)).toContain('More memories are available.');
  expect(visibleButtonCopy(renderer, 'Load more memories')).toEqual([
    'Load more memories',
  ]);
  act(() =>
    renderer.root
      .find(node => node.props.accessibilityLabel === 'Load more memories')
      .props.onPress(),
  );
  expect(onLoadMoreMemories).toHaveBeenCalledTimes(1);
});

test('actual desktop Home Load more memories stays memories-only when conversations also have more', () => {
  const onLoadMoreMemories = jest.fn();
  const renderer = renderDesktop({
    onLoadMoreMemories,
    outcomes: {
      ...pagedConversationOutcomes(),
      memories: pagedMemoryOutcomes().memories,
    },
    reads: [...outcomes.conversations.value.items, homeMemory],
  });
  const tree = renderedText(renderer);
  expect(tree).toContain('More conversations are available.');
  expect(tree).toContain('More memories are available.');
  expect(visibleButtonCopy(renderer, 'Load more memories')).toEqual([
    'Load more memories',
  ]);
  expect(
    renderer.root.findAll(
      node => node.props.accessibilityLabel === 'Load more conversations',
    ),
  ).toHaveLength(0);
  act(() =>
    renderer.root
      .find(node => node.props.accessibilityLabel === 'Load more memories')
      .props.onPress(),
  );
  expect(onLoadMoreMemories).toHaveBeenCalledTimes(1);
});

test('nested non-retryable later conversation pages omit more-available on Home', () => {
  const renderer = renderDesktop({
    conversationNotice: desktopBackendUnavailableCopy,
    outcomes: pagedConversationOutcomes(),
  });
  const tree = renderedText(renderer);
  expect(tree).toContain('Product review');
  expect(tree).toContain(desktopBackendUnavailableCopy);
  expect(tree).not.toContain('More conversations are available.');
});

test('nested non-retryable later task pages omit more-available on Home', () => {
  const renderer = renderDesktop({
    taskNotice: desktopBackendUnavailableCopy,
    outcomes: pagedTaskOutcomes(),
  });
  const tree = renderedText(renderer);
  expect(tree).toContain('Ship the desktop chrome');
  expect(tree).toContain(desktopBackendUnavailableCopy);
  expect(tree).not.toContain('More tasks are available.');
});

test('nested non-retryable later conversation pages do not claim more-available in a Home search miss', () => {
  const renderer = renderDesktop({
    conversationNotice: desktopBackendUnavailableCopy,
    draft: 'nomatch',
    outcomes: pagedConversationOutcomes(),
    reads: outcomes.conversations.value.items,
  });
  const tree = renderedText(renderer);
  expect(tree).toContain('Nothing captured matches this search.');
  expect(tree).toContain(desktopBackendUnavailableCopy);
  expect(tree).not.toContain('More conversations are available.');
});

test('nested non-retryable later task pages do not claim more-available in a Home search miss', () => {
  const renderer = renderDesktop({
    draft: 'nomatch',
    outcomes: pagedTaskOutcomes(),
    taskNotice: desktopBackendUnavailableCopy,
  });
  const tree = renderedText(renderer);
  expect(tree).toContain('No tasks match this search.');
  expect(tree).toContain(desktopBackendUnavailableCopy);
  expect(tree).not.toContain('More tasks are available.');
});

test('nested non-retryable later memory pages do not claim more-available in a Home search miss', () => {
  const renderer = renderDesktop({
    draft: 'nomatch',
    memoryNotice: desktopBackendUnavailableCopy,
    outcomes: pagedMemoryOutcomes(),
    reads: [...outcomes.conversations.value.items, homeMemory],
  });
  const tree = renderedText(renderer);
  expect(tree).toContain('Nothing captured matches this search.');
  expect(tree).toContain(desktopBackendUnavailableCopy);
  expect(tree).not.toContain('More memories are available.');
});

test('an unfiltered empty Home with remaining conversations still reports more-available after a closed later page', () => {
  const paged = pagedConversationOutcomes();
  const renderer = renderDesktop({
    conversationNotice: desktopBackendUnavailableCopy,
    outcomes: {
      ...paged,
      conversations: {
        ...paged.conversations,
        value: {
          ...paged.conversations.value,
          items: [],
        },
      },
    },
    reads: [],
  });
  const tree = renderedText(renderer);
  expect(tree).toContain('More conversations are available.');
  expect(tree).not.toContain('Nothing captured yet.');
  expect(tree).toContain(desktopBackendUnavailableCopy);
});

test('nested non-retryable later memory pages keep rows and omit Load more', () => {
  const renderer = renderDesktop({
    memoryNotice: desktopBackendUnavailableCopy,
    outcomes: pagedMemoryOutcomes(),
    reads: [...outcomes.conversations.value.items, homeMemory],
  });
  const tree = renderedText(renderer);
  expect(tree).toContain('Prefers concise release notes');
  expect(tree).toContain(desktopBackendUnavailableCopy);
  expect(
    renderer.root.findAll(
      node => node.props.accessibilityLabel === 'Load more memories',
    ),
  ).toHaveLength(0);
  expect(tree).not.toContain('More memories are available.');
});

test('generic later-page memory failures keep Load more', () => {
  const onLoadMoreMemories = jest.fn();
  const renderer = renderDesktop({
    memoryNotice: 'More memories could not be loaded.',
    onLoadMoreMemories,
    outcomes: pagedMemoryOutcomes(),
    reads: [...outcomes.conversations.value.items, homeMemory],
  });
  expect(renderedText(renderer)).toContain(
    'More memories could not be loaded.',
  );
  expect(visibleButtonCopy(renderer, 'Load more memories')).toEqual([
    'Load more memories',
  ]);
});

test('Settings does not inherit unrelated chat and history failures', async () => {
  const renderer = renderDesktop({
    chatError: 'This request cannot be completed.',
    readsPhase: 'unavailable',
  });
  expect(renderedText(renderer)).toContain('This request cannot be completed.');
  await act(async () => {
    renderer.root
      .find(node => node.props.accessibilityLabel === 'Settings')
      .props.onPress();
    await Promise.resolve();
  });
  expect(renderedText(renderer)).toContain('Old backend');
  expect(renderedText(renderer)).not.toContain(
    'This request cannot be completed.',
  );
  expect(renderedText(renderer)).not.toContain(
    "Some of your history isn't loaded yet.",
  );
  act(() =>
    renderer.root
      .find(node => node.props.accessibilityLabel === 'Home')
      .props.onPress(),
  );
  expect(renderedText(renderer)).toContain('This request cannot be completed.');
});
