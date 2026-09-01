import {readFileSync} from 'node:fs';
import {resolve} from 'node:path';
import React from 'react';
import ReactTestRenderer, {act} from 'react-test-renderer';
import {ScrollView, Text, TextInput} from 'react-native';
import {DesktopApp} from './DesktopApp';

jest.mock('../app/useReduceMotion', () => ({
  useReduceMotion: () => true,
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
  setPrivateCloudSync: jest.fn(),
  setStoreRecordingPermission: jest.fn(),
}));

jest.mock('../ui/GlassPanel', () => {
  const ReactModule = require('react');
  const {View} = require('react-native');
  return {
    GlassPanel: (props: Record<string, unknown>) =>
      ReactModule.createElement(View, props),
  };
});

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
        chatBusy={false}
        chatError={null}
        draft=""
        messages={[]}
        onDraftChange={jest.fn()}
        onRefresh={jest.fn()}
        onSend={jest.fn()}
        onSignIn={jest.fn()}
        onSignOut={jest.fn()}
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
  expect(tree).toContain('Library');
  expect(tree).toContain('Tasks');
  expect(tree).toContain('Rewind');
  expect(tree).toContain('Apps');
  expect(tree).toContain('Currents');
  expect(tree).toContain('Product review');
  expect(tree).toContain('Ship the desktop chrome');
  expect(tree).not.toContain("I'm ready.");
  expect(tree).not.toContain('Saved data unavailable');
  expect(tree).not.toContain('Omi disconnected');
  expect(tree).not.toContain('Devices');
  expect(tree).not.toContain('Your day is clear');
  expect(renderer.root.findAllByType(ScrollView).length).toBeGreaterThan(0);
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

test('keeps signed-out users in the real desktop shell', () => {
  const onSignIn = jest.fn();
  const renderer = renderDesktop({
    onSignIn,
    outcomes: null,
    reads: [],
    readsPhase: 'unavailable',
    session: 'signed-out',
  });
  const tree = renderedText(renderer);
  expect(
    renderer.root.findAllByType(TextInput).map(node => node.props.placeholder),
  ).toContain("Search what you've seen and heard…");
  expect(tree).toContain('Home');
  expect(tree).toContain('Sign in');
  expect(tree).toContain('Sign in to load conversations and memories.');
  expect(tree).not.toContain('Saved data unavailable');
  expect(tree).not.toContain('Sign in to Omi cloud');
  expect(tree).not.toContain('Welcome to Omi');
  expect(tree).not.toContain('Omi disconnected');
  expect(tree).not.toContain('Devices');
  act(() => {
    renderer.root
      .find(node => node.props.accessibilityLabel === 'Sign in')
      .props.onPress();
  });
  expect(onSignIn).toHaveBeenCalled();
});

test('holds the desktop shell while the session probe is running', () => {
  const renderer = renderDesktop({
    outcomes: null,
    reads: [],
    readsPhase: 'initial-loading',
    session: 'probing',
  });
  const tree = renderedText(renderer);
  expect(tree).toContain('Home');
  expect(tree).toContain('Restoring your session…');
  expect(
    renderer.root.findAllByType(TextInput).map(node => node.props.placeholder),
  ).toContain("Search what you've seen and heard…");
  expect(tree).not.toContain('Saved data unavailable');
  expect(tree).not.toContain('Welcome to Omi');
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

test('signed-out first paint does not show a chat transport error', () => {
  const renderer = renderDesktop({
    chatError: 'Chat is temporarily unavailable.',
    outcomes: null,
    reads: [],
    readsPhase: 'unavailable',
    session: 'signed-out',
  });
  const tree = renderedText(renderer);
  expect(tree).toContain('Sign in to load conversations and memories.');
  expect(tree).not.toContain('Chat is temporarily unavailable.');
});

test('ready chat transport error is not painted on Home', () => {
  const renderer = renderDesktop({
    chatError: 'Chat is temporarily unavailable.',
    session: 'ready',
  });
  expect(renderedText(renderer)).not.toContain(
    'Chat is temporarily unavailable.',
  );
  expect(renderedText(renderer)).toContain('Currents');
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
  expect(tree).toContain('Permissions');
  expect(tree).toContain('AI & Automation');
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
  expect(advanced).toContain('Advanced');
  expect(advanced).toContain('Backend');
  expect(advanced).toContain('old');
  expect(advanced).toContain('new');
  expect(advanced).not.toContain('workers.dev');
});

test('searches real projections instead of a fake timeline', () => {
  const renderer = renderDesktop({
    draft: 'product',
  });
  const tree = renderedText(renderer);
  expect(tree).toContain('Product review');
  expect(tree).not.toContain('Ship the desktop chrome');
  expect(tree).not.toContain('0 screen moments');
  expect(tree).not.toContain('💬');
  expect(tree).not.toContain('🧠');
});

test('Home stage lists never use FlatList', () => {
  const source = readFileSync(resolve(__dirname, 'DesktopApp.tsx'), 'utf8');
  expect(source).not.toMatch(/\bFlatList\b/);
  expect(source).toContain('ScrollView');
  expect(source).not.toContain('function GlassSurface');
  expect(source).not.toContain("I'm ready.");
  expect(source).not.toContain('Ask a follow-up');
  expect(source).toMatch(/filterRow:\s*\{[^}]*flexDirection:\s*'row'/);
  expect(source).not.toMatch(/chip:\s*\{[^}]*borderRadius:\s*14/);
  expect(source).not.toMatch(/banner:\s*\{[^}]*borderRadius:/);
  expect(source).not.toMatch(/composer:\s*\{/);
  expect(source).toContain('accessibilityLabel="Home currents"');
  expect(source).toContain('accessibilityLabel="Home tasks"');
  expect(source).toContain('visibleChatError');
  expect(source).not.toContain('omnibarError');
  expect(source).not.toMatch(/active=\{route === label\}/);
  expect(source).not.toMatch(/navItem:\s*\{[^}]*borderRadius/);
  expect(source).not.toMatch(
    /sendButton:\s*\{[^}]*backgroundColor:\s*token\.color\.dark/,
  );
  expect(source).not.toMatch(/sendButton:\s*\{[^}]*borderRadius/);
  expect(source).toMatch(/omnibarInput:\s*\{[^}]*minWidth:\s*0/);
  expect(source).toMatch(/omnibar:\s*\{[^}]*minWidth:\s*220/);
});
