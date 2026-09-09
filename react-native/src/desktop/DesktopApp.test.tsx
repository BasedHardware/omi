import {readFileSync} from 'node:fs';
import {resolve} from 'node:path';
import React from 'react';
import ReactTestRenderer, {act} from 'react-test-renderer';
import {
  FlatList,
  NativeModules,
  ScrollView,
  Switch,
  Text,
  TextInput,
} from 'react-native';
import {DesktopApp} from './DesktopApp';
import {TaskPagination} from '../ui/TaskPagination';
import {subscribeDesktopSearchCommand} from '../desktopCommands';

jest.mock('../desktopCommands', () => ({
  subscribeDesktopSearchCommand: jest.fn(() => ({remove: jest.fn()})),
}));

jest.mock('../app/useReduceMotion', () => ({
  useReduceMotion: () => true,
}));

jest.mock('../omiNative', () => ({
  omiBackend: {request: jest.fn()},
  subscribeOmiBackendSessionInvalidated: jest.fn(() => () => undefined),
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
  loadAccountSettings: jest.fn(async () => {
    throw new Error('unused');
  }),
  loadConnectors: jest.fn(async () => ({
    apps: [],
    enabledError: null,
    enabledIds: [],
    ownerUid: null,
  })),
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
  expect(placeholders).toContain('Ask about your day…');
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

test.each(['tasks', 'conversations'] as const)(
  'Home limits both previews to three and opens the full %s list',
  section => {
    const tasks = Array.from({length: 5}, (_, index) => ({
      ...outcomes.tasks.value.items[0],
      id: `preview-task-${index}`,
      title: `Preview task ${index}`,
    }));
    const conversations = Array.from({length: 5}, (_, index) => ({
      ...outcomes.conversations.value.items[0],
      id: `preview-conversation-${index}`,
      title: `Preview conversation ${index}`,
    }));
    const renderer = renderDesktop({
      reads: [...conversations, ...tasks],
      outcomes: {
        ...outcomes,
        tasks: {
          ...outcomes.tasks,
          value: {...outcomes.tasks.value, items: tasks},
        },
        conversations: {
          ...outcomes.conversations,
          value: {...outcomes.conversations.value, items: conversations},
        },
      },
    });
    const home = renderedText(renderer);
    for (const prefix of ['Preview task', 'Preview conversation']) {
      for (let index = 0; index < 5; index++) {
        if (index < 3) {
          expect(home).toContain(`${prefix} ${index}`);
        } else {
          expect(home).not.toContain(`${prefix} ${index}`);
        }
      }
    }
    expect(home).toContain('Open Recall');
    expect(
      renderer.root.findAll(
        node => node.props.accessibilityLabel === 'Open Recall',
      ).length,
    ).toBeGreaterThan(0);
    act(() => {
      renderer.root
        .find(node => node.props.accessibilityLabel === `Show more ${section}`)
        .props.onPress();
    });
    const page = renderedText(renderer);
    const prefix =
      section === 'tasks' ? 'Preview task' : 'Preview conversation';
    for (let index = 0; index < 5; index++) {
      expect(page).toContain(`${prefix} ${index}`);
    }
    expect(page).not.toContain('Open Recall');
  },
);

test('persistent capture toggle uses the existing owner across Home, Recall and Chat', async () => {
  const capture = {
    available: true,
    capturing: false,
    busy: false,
    error: null,
    start: jest.fn(async () => undefined),
    stop: jest.fn(async () => undefined),
  };
  const hook = jest
    .spyOn(require('../app/useRewindCapture'), 'useRewindCapture')
    .mockReturnValue(capture);
  try {
    const renderer = renderDesktop();
    const toggle = () =>
      renderer.root
        .findAllByType(Switch)
        .find(node => node.props.accessibilityLabel === 'Screen capture')!;
    expect(toggle().props.value).toBe(false);
    await act(async () => toggle().props.onValueChange(true));
    expect(capture.start).toHaveBeenCalledTimes(1);
    capture.capturing = true;
    await act(async () =>
      renderer.root
        .find(node => node.props.accessibilityLabel === 'Use Recall mode')
        .props.onPress(),
    );
    expect(toggle().props.value).toBe(true);
    expect(
      renderer.root
        .findAllByType(Switch)
        .filter(node => node.props.accessibilityLabel === 'Screen capture'),
    ).toHaveLength(1);
    await act(async () =>
      renderer.root
        .find(node => node.props.accessibilityLabel === 'Use Ask mode')
        .props.onPress(),
    );
    await act(async () => toggle().props.onValueChange(false));
    expect(capture.stop).toHaveBeenCalledTimes(1);
    act(() => renderer.unmount());
    renderers.splice(renderers.indexOf(renderer), 1);
  } finally {
    hook.mockRestore();
  }
});

test('keyboard search from Chat focuses the persistent omnibar', () => {
  const focus = jest.mocked(TextInput.prototype.focus);
  focus.mockClear();
  const renderer = renderDesktop();
  act(() =>
    renderer.root
      .find(node => node.props.accessibilityLabel === 'Use Ask mode')
      .props.onPress(),
  );
  expect(renderer.root.findByType(TextInput).props.accessibilityLabel).toBe(
    'Ask Omi',
  );
  const command = jest
    .mocked(subscribeDesktopSearchCommand)
    .mock.calls.at(-1)![0];
  act(() => command());
  expect(renderer.root.findByType(TextInput).props.accessibilityLabel).toBe(
    'Search history',
  );
  expect(focus).toHaveBeenCalledTimes(1);
  act(() => command());
  expect(focus).toHaveBeenCalledTimes(2);
});

test.each(['Search', 'Recall'])(
  '%s click remains a search while a chat generation is active',
  async mode => {
    const onSend = jest.fn();
    const onStop = jest.fn();
    const renderer = renderDesktop({
      activeGenerationId: 'active',
      draft: 'query',
      onSend,
      onStop,
    });
    await act(async () =>
      renderer.root
        .find(node => node.props.accessibilityLabel === `Use ${mode} mode`)
        .props.onPress(),
    );
    await act(async () =>
      renderer.root
        .find(node => node.props.accessibilityLabel === 'Search')
        .props.onPress(),
    );
    expect(onSend).not.toHaveBeenCalled();
    expect(onStop).not.toHaveBeenCalled();
  },
);

test('Chat shows disabled Sending until there is an actual cancellable request', () => {
  const onStop = jest.fn();
  const onSend = jest.fn();
  const renderer = renderDesktop({
    chatBusy: true,
    draft: 'pending',
    onStop,
    onSend,
  });
  act(() =>
    renderer.root
      .find(node => node.props.accessibilityLabel === 'Use Ask mode')
      .props.onPress(),
  );
  const pending = renderer.root.find(
    node => node.props.accessibilityLabel === 'Sending…',
  );
  expect(pending.props.disabled).toBe(true);
  act(() => pending.props.onPress());
  expect(onStop).not.toHaveBeenCalled();
  expect(onSend).not.toHaveBeenCalled();
  const props = renderer.root.findByType(DesktopApp)
    .props as React.ComponentProps<typeof DesktopApp>;
  act(() =>
    renderer.update(<DesktopApp {...props} activeGenerationId="admitted" />),
  );
  act(() =>
    renderer.root
      .find(node => node.props.accessibilityLabel === 'Stop')
      .props.onPress(),
  );
  expect(onStop).toHaveBeenCalledTimes(1);
});

test('a task search with no matches does not claim there are no tasks', () => {
  const renderer = renderDesktop({draft: 'unmatched query'});
  act(() =>
    renderer.root
      .find(node => node.props.accessibilityLabel === 'Use Search mode')
      .props.onPress(),
  );
  expect(renderedText(renderer)).toContain('No tasks match this search.');
  expect(renderedText(renderer)).not.toContain('No tasks yet');
});

test('empty Ask is disabled and Enter cannot send, while its mode icon still opens Chat', () => {
  const onSend = jest.fn();
  const renderer = renderDesktop({draft: '   ', onSend});
  expect(renderer.root.findByType(TextInput).props.accessibilityLabel).toBe(
    'Ask Omi',
  );
  const send = renderer.root.find(
    node => node.props.accessibilityLabel === 'Send',
  );
  expect(send.props.disabled).toBe(true);
  act(() => renderer.root.findByType(TextInput).props.onSubmitEditing());
  act(() => send.props.onPress());
  expect(onSend).not.toHaveBeenCalled();
  act(() =>
    renderer.root
      .find(node => node.props.accessibilityLabel === 'Use Ask mode')
      .props.onPress(),
  );
  expect(renderer.root.findByType(TextInput).props.accessibilityLabel).toBe(
    'Ask Omi',
  );
});

test.each(['initial-loading', 'refreshing', 'unavailable'] as const)(
  'Home hides more actions during %s',
  readsPhase => {
    const renderer = renderDesktop({
      readsPhase,
      ...(readsPhase === 'unavailable' ? {outcomes: null, reads: []} : {}),
    });
    expect(
      renderer.root.findAll(
        node =>
          node.props.accessibilityLabel === 'Show more tasks' ||
          node.props.accessibilityLabel === 'Show more conversations',
      ),
    ).toHaveLength(0);
  },
);

test('Home empty results have no more action and matching searches explicitly open the unfiltered page', () => {
  const renderer = renderDesktop({draft: 'product'});
  act(() =>
    renderer.root
      .find(node => node.props.accessibilityLabel === 'Use Search mode')
      .props.onPress(),
  );
  expect(
    renderer.root.findAll(
      node =>
        node.props.accessibilityLabel === 'Show more tasks' ||
        node.props.accessibilityLabel === 'Show more conversations' ||
        node.props.accessibilityLabel === 'Open tasks',
    ),
  ).toHaveLength(0);
  act(() =>
    renderer.root
      .find(node => node.props.accessibilityLabel === 'Open conversations')
      .props.onPress(),
  );
  expect(renderedText(renderer)).toContain('Product review');
  const empty = renderDesktop({
    reads: [],
    outcomes: {
      ...outcomes,
      tasks: {...outcomes.tasks, value: {...outcomes.tasks.value, items: []}},
      conversations: {
        ...outcomes.conversations,
        value: {...outcomes.conversations.value, items: []},
      },
    },
  });
  expect(
    empty.root.findAll(
      node =>
        node.props.accessibilityLabel === 'Show more tasks' ||
        node.props.accessibilityLabel === 'Show more conversations',
    ),
  ).toHaveLength(0);
});

test('Home pre-admission sending disables Ask while Search remains usable', () => {
  const onSend = jest.fn();
  const onStop = jest.fn();
  const renderer = renderDesktop({
    chatBusy: true,
    draft: 'pending request',
    onSend,
    onStop,
  });
  const sending = renderer.root.find(
    node => node.props.accessibilityLabel === 'Sending…',
  );
  expect(sending.props.disabled).toBe(true);
  act(() => sending.props.onPress());
  act(() => renderer.root.findByType(TextInput).props.onSubmitEditing());
  expect(onSend).not.toHaveBeenCalled();
  expect(onStop).not.toHaveBeenCalled();
  act(() =>
    renderer.root
      .find(node => node.props.accessibilityLabel === 'Use Search mode')
      .props.onPress(),
  );
  const search = renderer.root.find(
    node => node.props.accessibilityLabel === 'Search',
  );
  expect(search.props.disabled).toBe(false);
  act(() => search.props.onPress());
  expect(onSend).not.toHaveBeenCalled();
  expect(onStop).not.toHaveBeenCalled();
});

test('Chat has its own selected destination, keeps one omnibar, and closes to the previous route and mode', async () => {
  const onSend = jest.fn();
  const renderer = renderDesktop({draft: 'question', onSend});
  await act(async () =>
    renderer.root
      .find(node => node.props.accessibilityLabel === 'Use Recall mode')
      .props.onPress(),
  );
  await act(async () =>
    renderer.root
      .find(node => node.props.accessibilityLabel === 'Chat')
      .props.onPress(),
  );
  expect(renderer.root.findAllByType(TextInput)).toHaveLength(1);
  expect(renderer.root.findByType(TextInput).props.accessibilityLabel).toBe(
    'Ask Omi',
  );
  expect(renderedText(renderer)).toContain('Enter to submit');
  expect(
    renderer.root.find(node => node.props.accessibilityLabel === 'Chat').props
      .accessibilityState.selected,
  ).toBe(true);
  act(() => renderer.root.findByType(TextInput).props.onSubmitEditing());
  expect(onSend).toHaveBeenCalledTimes(1);
  await act(async () =>
    renderer.root
      .find(node => node.props.accessibilityLabel === 'Close chat')
      .props.onPress(),
  );
  expect(renderer.root.findByType(TextInput).props.accessibilityLabel).toBe(
    'Search Recall',
  );
  expect(
    renderer.root.findAll(
      node => node.props.accessibilityLabel === 'Recall screen history',
    ).length,
  ).toBeGreaterThan(0);
  expect(
    renderer.root.findAll(
      node => node.props.accessibilityLabel === 'Chat with Omi',
    ),
  ).toHaveLength(0);
});

test('only an explicit Ask submission resumes following after reading earlier messages', () => {
  const scrollToEnd = jest
    .spyOn(FlatList.prototype, 'scrollToEnd')
    .mockImplementation(() => undefined);
  const onSend = jest.fn();
  const onLoadOlderChat = jest.fn();
  try {
    const renderer = renderDesktop({
      draft: 'a new question',
      hasOlderChat: true,
      onSend,
      onLoadOlderChat,
      messages: [
        {
          id: 'initial',
          text: 'Earlier conversation',
          sender: 'human',
          createdAt: 1,
          generationOutcome: null,
        },
      ],
    });
    act(() =>
      renderer.root
        .find(node => node.props.accessibilityLabel === 'Use Ask mode')
        .props.onPress(),
    );
    const list = () => renderer.root.findByType(FlatList);
    const scrollUp = () =>
      list().props.onScroll({
        nativeEvent: {
          contentOffset: {x: 0, y: 0},
          contentSize: {width: 600, height: 2000},
          layoutMeasurement: {width: 600, height: 500},
        },
      });
    act(scrollUp);
    scrollToEnd.mockClear();
    const props = renderer.root.findByType(DesktopApp)
      .props as React.ComponentProps<typeof DesktopApp>;
    act(() =>
      renderer.update(
        <DesktopApp
          {...props}
          messages={[
            ...props.messages,
            {
              id: 'passive',
              text: 'Incoming message',
              sender: 'ai',
              createdAt: 2,
              generationOutcome: null,
            },
          ]}
        />,
      ),
    );
    act(() => list().props.onContentSizeChange(600, 2200));
    expect(scrollToEnd).not.toHaveBeenCalled();
    act(() =>
      renderer.root
        .find(node => node.props.accessibilityLabel === 'Load earlier messages')
        .props.onPress(),
    );
    expect(onLoadOlderChat).toHaveBeenCalledTimes(1);
    act(() => list().props.onContentSizeChange(600, 2400));
    expect(scrollToEnd).not.toHaveBeenCalled();
    act(() => renderer.root.findByType(TextInput).props.onSubmitEditing());
    expect(onSend).toHaveBeenCalledTimes(1);
    expect(scrollToEnd).toHaveBeenCalledWith({animated: false});
    scrollToEnd.mockClear();
    act(() => list().props.onContentSizeChange(600, 2600));
    expect(scrollToEnd).toHaveBeenCalledTimes(1);
    act(scrollUp);
    scrollToEnd.mockClear();
    act(() => list().props.onContentSizeChange(600, 2800));
    expect(scrollToEnd).not.toHaveBeenCalled();
    act(() => renderer.unmount());
    renderers.splice(renderers.indexOf(renderer), 1);
  } finally {
    scrollToEnd.mockRestore();
  }
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
    .find(node => node.props.placeholder === 'Ask about your day…');
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

test('sending from another page opens Chat and an active response can stop', async () => {
  const onSend = jest.fn();
  const onStop = jest.fn();
  const renderer = renderDesktop({onSend, onStop, draft: 'Send from Tasks'});
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
  expect(
    renderer.root.findAllByType(TextInput).map(node => node.props.placeholder),
  ).toEqual(['Ask about your day…']);

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
        createdAt: 1,
        generationOutcome: 'failed',
        generationRetryable: true,
      },
    ],
  });
  act(() => pressText(renderer, 'Continue chat'));
  expect(renderedText(renderer)).toContain('Response failed. Try again.');
  expect(
    renderer.root.findAll(
      node => node.props.accessibilityLabel === 'Failed response',
    ),
  ).not.toHaveLength(0);
});

test('desktop chat can load earlier messages', () => {
  const onLoadOlderChat = jest.fn();
  const renderer = renderDesktop({hasOlderChat: true, onLoadOlderChat});
  act(() =>
    renderer.root
      .find(node => node.props.accessibilityLabel === 'Use Ask mode')
      .props.onPress(),
  );
  act(() => {
    renderer.root
      .find(node => node.props.accessibilityLabel === 'Load earlier messages')
      .props.onPress();
  });
  expect(onLoadOlderChat).toHaveBeenCalledTimes(1);
});

test('Continue chat opens full loaded history with one persistent omnibar', () => {
  const messages = Array.from({length: 5}, (_, index) => ({
    id: `chat-${index}`,
    text: `Loaded message ${index}`,
    sender: 'human' as const,
    generationOutcome: null,
    createdAt: index,
  }));
  const renderer = renderDesktop({messages});
  expect(renderedText(renderer)).not.toContain('Loaded message');
  act(() => pressText(renderer, 'Continue chat'));
  for (const message of messages) {
    expect(renderedText(renderer)).toContain(message.text);
  }
  expect(
    renderer.root.findAllByType(TextInput).map(node => node.props.placeholder),
  ).toEqual(['Ask about your day…']);
});

test.each(['Search', 'Recall'])(
  '%s submits without sending chat',
  async mode => {
    const onSend = jest.fn();
    const renderer = renderDesktop({draft: 'a saved moment', onSend});
    await act(async () =>
      renderer.root
        .find(node => node.props.accessibilityLabel === `Use ${mode} mode`)
        .props.onPress(),
    );
    expect(renderer.root.findAllByType(TextInput)).toHaveLength(1);
    await act(async () =>
      renderer.root.findByType(TextInput).props.onSubmitEditing(),
    );
    expect(onSend).not.toHaveBeenCalled();
    expect(
      renderer.root.findAll(
        node => node.props.accessibilityLabel === 'Chat with Omi',
      ),
    ).toHaveLength(0);
  },
);

test('Recall typing debounces the shared input into actual timeline reads', async () => {
  jest.useFakeTimers();
  const previous = NativeModules.OmiRewind;
  const listFrames = jest.fn(async () => ({frames: [], nextCursor: null}));
  NativeModules.OmiRewind = {listFrames};
  try {
    const onDraftChange = jest.fn();
    const renderer = renderDesktop({onDraftChange});
    await act(async () =>
      renderer.root
        .find(node => node.props.accessibilityLabel === 'Use Recall mode')
        .props.onPress(),
    );
    listFrames.mockClear();
    act(() =>
      renderer.root.findByType(TextInput).props.onChangeText('project notes'),
    );
    expect(onDraftChange).toHaveBeenCalledWith('project notes');
    const props = renderer.root.findByType(DesktopApp)
      .props as React.ComponentProps<typeof DesktopApp>;
    await act(async () =>
      renderer.update(<DesktopApp {...props} draft="project notes" />),
    );
    await act(async () => jest.advanceTimersByTime(199));
    expect(listFrames).not.toHaveBeenCalled();
    await act(async () => jest.advanceTimersByTime(1));
    expect(listFrames).toHaveBeenCalledWith(
      expect.objectContaining({query: 'project notes', source: 'captured'}),
    );
    expect(listFrames).toHaveBeenCalledWith(
      expect.objectContaining({query: 'project notes', source: 'shipping'}),
    );
    expect(renderer.root.findAllByType(TextInput)).toHaveLength(1);
    act(() => renderer.unmount());
    renderers.splice(renderers.indexOf(renderer), 1);
  } finally {
    NativeModules.OmiRewind = previous;
    jest.useRealTimers();
  }
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
  expect(tree).toContain('Get started');
  expect(tree).not.toContain('Sign in');
  // No nav pills, no omnibar, no Home currents, no Settings.
  expect(
    renderer.root.findAllByType(TextInput).map(node => node.props.placeholder),
  ).not.toContain('Ask about your day…');
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
  act(() => pressText(renderer, 'Get started'));
  expect(renderedText(renderer)).toContain('Cloud AI services');
  act(() => pressText(renderer, 'Continue'));
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
  ).not.toContain('Ask about your day…');
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
  ).toContain('Ask about your day…');
  expect(tree).not.toContain('Saved data unavailable');
  expect(tree).not.toContain('Sign in to Omi cloud');
  expect(tree).not.toContain('Offline · showing what is available on this Mac');
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

test('chat transport errors appear only in the lower Chat view', () => {
  const renderer = renderDesktop({
    chatError: 'Chat is temporarily unavailable.',
  });
  expect(renderedText(renderer)).not.toContain(
    'Chat is temporarily unavailable.',
  );
  act(() =>
    renderer.root
      .find(node => node.props.accessibilityLabel === 'Use Ask mode')
      .props.onPress(),
  );
  expect(renderedText(renderer)).toContain('Chat is temporarily unavailable.');
  expect(
    renderer.root.findAllByType(TextInput).map(node => node.props.placeholder),
  ).toEqual(['Ask about your day…']);
  act(() =>
    renderer.root
      .find(node => node.props.accessibilityLabel === 'Home')
      .props.onPress(),
  );
  expect(renderedText(renderer)).not.toContain(
    'Chat is temporarily unavailable.',
  );
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
  act(() =>
    renderer.root
      .find(node => node.props.accessibilityLabel === 'Use Search mode')
      .props.onPress(),
  );
  const tree = renderedText(renderer);
  expect(tree).toContain('Product review');
  expect(tree).not.toContain('Ship the desktop chrome');
  expect(tree).not.toContain('0 screen moments');
  expect(tree).not.toContain('💬');
  expect(tree).not.toContain('🧠');
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
  expect(tree).toContain('Memory');
});

test('Home opens the real Rewind destination', async () => {
  const renderer = renderDesktop();
  expect(renderedText(renderer)).toContain('Open Recall');
  await act(async () => {
    renderer.root
      .find(node => node.props.accessibilityLabel === 'Open Recall')
      .props.onPress();
    await Promise.resolve();
  });
  expect(
    renderer.root.findAll(
      node => node.props.accessibilityLabel === 'Recall screen history',
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

test('static tripwire: desktop stage preserves real state copy and shared glass ownership', () => {
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
  expect(chrome).toMatch(
    /omnibarInput:\s*\{[^}]*textAlignVertical:\s*'center'/,
  );
  expect(chrome).toMatch(/omnibarInput:\s*\{[^}]*paddingVertical:\s*6/);
  expect(chrome).not.toMatch(/navItem:\s*\{[^}]*borderRadius/);
  expect(chrome).toMatch(/omnibar:\s*\{[^}]*minWidth:\s*220/);
  expect(home).toMatch(/section:\s*\{[^}]*borderRadius:\s*16/);
  expect(home).not.toMatch(/filterRow:\s*\{/);
  expect(home).not.toContain('chatScrollRef');
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
  const tree = renderedText(renderer);
  expect(tree).toContain('Nothing captured yet.');
  expect(tree).toContain('No tasks yet');
  expect(tree).not.toContain(
    'Conversations will show here when your day is loaded.',
  );
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
  expect(tree).toContain('No apps are available.');
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
    pressText(renderer, 'always');
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
      .find(node => node.props.accessibilityLabel === 'Sign out')
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
    subscriptionError: 'Plan is temporarily unavailable.',
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
  expect(renderedText(renderer)).toContain('Plan is temporarily unavailable.');
  expect(renderedText(renderer)).not.toContain(
    'Plan details load after sign-in.',
  );
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
      .find(node => node.props.accessibilityLabel === 'Alerts & Privacy')
      .props.onPress();
  });
  expect(renderedText(renderer)).toContain(
    'Cloud recording storage status is unavailable.',
  );
  expect(renderedText(renderer)).toContain(
    'Private cloud sync status is unavailable.',
  );
  expect(
    renderer.root.findAll(node => node.props.accessibilityLabel === 'Update'),
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

test('desktop Library forwards pagination and prevents another click while loading', () => {
  const onLoadMoreConversations = jest.fn();
  const renderer = renderDesktop({
    onLoadMoreConversations,
    outcomes: {
      ...outcomes,
      conversations: {
        ...outcomes.conversations,
        value: {
          ...outcomes.conversations.value,
          page: {
            ...outcomes.conversations.value.page,
            hasMore: true,
            nextCursor: 'next-page',
          },
        },
      },
    },
  });
  act(() =>
    renderer.root
      .find(node => node.props.accessibilityLabel === 'Conversations')
      .props.onPress(),
  );
  const more = () =>
    renderer.root.find(
      node => node.props.accessibilityLabel === 'Load more conversations',
    );
  expect(more().props.disabled).toBe(false);
  act(() => more().props.onPress());
  expect(onLoadMoreConversations).toHaveBeenCalledTimes(1);
  const props = renderer.root.findByType(DesktopApp)
    .props as React.ComponentProps<typeof DesktopApp>;
  act(() =>
    renderer.update(<DesktopApp {...props} conversationsLoadingMore />),
  );
  expect(more().props.disabled).toBe(true);
  expect(renderedText(renderer)).toContain('Loading…');
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

test('Settings does not inherit unrelated chat and history failures', async () => {
  const renderer = renderDesktop({
    chatError: 'This request cannot be completed.',
    readsPhase: 'unavailable',
  });
  expect(renderedText(renderer)).not.toContain(
    'This request cannot be completed.',
  );
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
  expect(renderedText(renderer)).not.toContain(
    'This request cannot be completed.',
  );
});
