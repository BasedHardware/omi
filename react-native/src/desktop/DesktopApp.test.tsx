import {readFileSync} from 'node:fs';
import {resolve} from 'node:path';
import React from 'react';
import ReactTestRenderer, {act} from 'react-test-renderer';
import {Text, TextInput} from 'react-native';
import {DesktopApp, DesktopChromeGuard} from './DesktopApp';
import type {TaskProjection} from '../desktopReadClient';
import {desktopTokens as token} from './tokens';

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
        reads={outcomes.conversations.value.items}
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
  expect(
    renderer.root.findAllByType(TextInput).map(node => node.props.placeholder),
  ).toContain("Search what you've seen and heard…");
  expect(tree).toContain('Home');
  expect(tree).toContain('Library');
  expect(tree).toContain('Tasks');
  expect(tree).toContain('Rewind');
  expect(tree).toContain('Apps');
  expect(tree).toContain("I'm ready.");
  expect(
    renderer.root.findAllByType(TextInput).map(node => node.props.placeholder),
  ).toContain('Ask a follow-up…');
  expect(tree).not.toContain('Saved data unavailable');
  expect(tree).not.toContain('Omi disconnected');
  expect(tree).not.toContain('Devices');
  expect(tree).not.toContain('Your day is clear');
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

const sampleTask: TaskProjection = {
  kind: 'task',
  id: 'task-1',
  title: 'Ship the glass chrome',
  summary: 'Pending',
  searchableText: 'Ship the glass chrome',
  completed: false,
  completedAt: null,
  dueAt: null,
  owner: null,
  source: 'desktop',
  provenance: [],
  sortOrder: 0,
  indentLevel: 0,
  createdAt: 1_725_000_000,
  updatedAt: 1_725_000_000,
  revision: null,
};

function pressLabeledButton(
  renderer: ReactTestRenderer.ReactTestRenderer,
  label: string,
) {
  const match = renderer.root
    .findAll(node => node.props.accessibilityRole === 'button')
    .find(node =>
      node.findAllByType(Text).some(text => text.props.children === label),
    );
  expect(match).toBeDefined();
  act(() => {
    match!.props.onPress();
  });
}

test('renders Tasks with empty outcomes and with a success list', () => {
  const empty = renderDesktop({
    outcomes: null,
    reads: [],
    readsPhase: 'unavailable',
    session: 'signed-out',
  });
  pressLabeledButton(empty, 'Tasks');
  expect(renderedText(empty)).toContain('No tasks yet');

  const failed = renderDesktop({
    outcomes: {
      conversations: {status: 'error', error: 'unavailable'},
      memories: {status: 'error', error: 'unavailable'},
      tasks: {status: 'error', error: 'unavailable'},
    },
    reads: [],
    readsPhase: 'unavailable',
  });
  pressLabeledButton(failed, 'Tasks');
  expect(renderedText(failed)).toContain('No tasks yet');

  const loaded = renderDesktop({
    outcomes: {
      ...outcomes,
      tasks: {
        status: 'success',
        value: {
          items: [sampleTask],
          page: outcomes.tasks.value.page,
        },
      },
    },
  });
  pressLabeledButton(loaded, 'Tasks');
  expect(renderedText(loaded)).toContain('Ship the glass chrome');
});

test('Home Tasks Library Rewind Apps never throw for empty outcomes', () => {
  const renderer = renderDesktop({
    outcomes: null,
    reads: [],
    readsPhase: 'unavailable',
    session: 'signed-out',
  });
  for (const label of ['Tasks', 'Library', 'Rewind', 'Apps', 'Home'] as const) {
    expect(() => pressLabeledButton(renderer, label)).not.toThrow();
  }
  pressLabeledButton(renderer, 'Library');
  expect(renderedText(renderer)).toContain('Activity');
  pressLabeledButton(renderer, 'Rewind');
  expect(renderedText(renderer)).toContain(
    'Screen history is ready when capture is on',
  );
  pressLabeledButton(renderer, 'Apps');
  expect(renderedText(renderer)).toContain('Imports');
  pressLabeledButton(renderer, 'Home');
  expect(renderedText(renderer)).toContain("I'm ready.");
});

test('Tasks page does not mount FlatList inside the shipping stage', () => {
  const source = readFileSync(resolve(__dirname, './DesktopApp.tsx'), 'utf8');
  const start = source.indexOf('function TasksPage');
  const end = source.indexOf('const imports');
  const tasksPage = source.slice(start, end);
  expect(start).toBeGreaterThan(-1);
  expect(tasksPage).not.toContain('FlatList');
  expect(tasksPage).toContain('ScrollView');
});

test('Apps page does not mount FlatList and still paints import cards', () => {
  const source = readFileSync(resolve(__dirname, './DesktopApp.tsx'), 'utf8');
  const start = source.indexOf('function AppsPage');
  const end = source.indexOf('export function DesktopApp');
  const appsPage = source.slice(start, end);
  expect(start).toBeGreaterThan(-1);
  expect(appsPage).not.toContain('FlatList');
  expect(appsPage).toContain('ScrollView');

  const renderer = renderDesktop();
  pressLabeledButton(renderer, 'Apps');
  const tree = renderedText(renderer);
  expect(tree).toContain('Imports');
  expect(tree).toContain('Google Calendar');
  expect(tree).toContain('This Mac');
  expect(tree).toContain('Home');
  expect(tree).toContain('Tasks');
});

test('paints shipping chrome as yoga children of translucent Views', () => {
  const source = readFileSync(resolve(__dirname, './DesktopApp.tsx'), 'utf8');
  const start = source.indexOf('function GlassSurface');
  const end = source.indexOf('export class DesktopChromeGuard');
  const glassSurface = source.slice(start, end);
  expect(start).toBeGreaterThan(-1);
  expect(glassSurface).toContain('{children}');
  expect(glassSurface).not.toContain('GlassPanel');
  expect(glassSurface).not.toContain('OmiGlassPanel');
  expect(source).not.toContain("from '../ui/GlassPanel'");
  expect(source).not.toContain('glassHost');
  expect(source).toContain('token.color.glassStrong');
  expect(source).toContain('token.color.glassQuiet');

  const renderer = renderDesktop();
  const tree = renderedText(renderer);
  expect(tree).toContain('Home');
  expect(tree).toContain('Library');
  expect(tree).toContain('Tasks');
  expect(tree).toContain('Rewind');
  expect(tree).toContain('Apps');
  expect(tree).toContain("I'm ready.");

  const home = renderer.root
    .findAllByType(Text)
    .find(node => node.props.children === 'Home');
  expect(home).toBeDefined();
  let ancestor: ReactTestRenderer.ReactTestInstance | null = home!.parent;
  let foundGlassSurface = false;
  while (ancestor != null) {
    expect(ancestor.props.glassCornerRadius).toBeUndefined();
    const styles = ([] as unknown[]).concat(ancestor.props.style ?? []);
    if (
      styles.some(
        entry =>
          entry != null &&
          typeof entry === 'object' &&
          'backgroundColor' in entry &&
          (entry as {backgroundColor?: string}).backgroundColor ===
            token.color.glassStrong,
      )
    ) {
      foundGlassSurface = true;
    }
    ancestor = ancestor.parent;
  }
  expect(foundGlassSurface).toBe(true);

  expect(
    renderer.root.findAll(node => node.props.glassCornerRadius !== undefined),
  ).toHaveLength(0);
});

test('root chrome guard keeps nav labels when a child throws', () => {
  function Boom(): React.JSX.Element {
    throw new Error('chrome exploded');
  }
  const spy = jest.spyOn(console, 'error').mockImplementation(() => undefined);
  let renderer: ReactTestRenderer.ReactTestRenderer;
  act(() => {
    renderer = ReactTestRenderer.create(
      <DesktopChromeGuard>
        <Boom />
      </DesktopChromeGuard>,
    );
  });
  const tree = renderedText(renderer!);
  expect(tree).toContain('Home');
  expect(tree).toContain('Library');
  expect(tree).toContain('Tasks');
  expect(tree).toContain('Rewind');
  expect(tree).toContain('Apps');
  expect(tree).toContain('chrome exploded');
  expect(tree).not.toBe('');
  act(() => {
    renderer.unmount();
  });
  spy.mockRestore();
});

test('Home and Library chips share a sliding glass pill', () => {
  const source = readFileSync(resolve(__dirname, './DesktopApp.tsx'), 'utf8');
  expect(source.match(/<ChipRail/g)?.length).toBeGreaterThanOrEqual(2);
  expect(source).not.toContain('active={filter === label}');
  expect(source).not.toContain('active={hub === label}');
});

test('uses discrete glass panels instead of one window material', () => {
  const renderer = renderDesktop();
  const panels = renderer.root.findAll(node => {
    const styles = ([] as unknown[]).concat(node.props.style ?? []);
    return styles.some(
      entry =>
        entry != null &&
        typeof entry === 'object' &&
        'backgroundColor' in entry &&
        (entry as {backgroundColor?: string}).backgroundColor ===
          token.color.glassStrong,
    );
  });
  expect(panels.length).toBeGreaterThanOrEqual(4);
  expect(
    renderer.root.find(node => node.props.accessibilityLabel === 'Omi desktop')
      .props.style,
  ).toEqual(
    expect.objectContaining({
      backgroundColor: 'transparent',
      paddingTop: expect.anything(),
    }),
  );
  const source = readFileSync(resolve(__dirname, './DesktopApp.tsx'), 'utf8');
  expect(source).not.toContain('UnderWindowBackground');
  expect(source.match(/<GlassSurface/g)?.length).toBeGreaterThanOrEqual(4);
  expect(source).toContain('token.color.onGlass');
  expect(source).toContain('token.color.glassStrong');
});

test('searches real projections instead of a fake timeline', () => {
  const renderer = renderDesktop({
    draft: '',
  });
  const search = renderer.root
    .findAllByType(TextInput)
    .find(
      node => node.props.placeholder === "Search what you've seen and heard…",
    );
  act(() => {
    search!.props.onChangeText('product');
  });
  const tree = renderedText(renderer);
  expect(tree).toContain('Product review');
  expect(tree).not.toContain('0 screen moments');
  expect(tree).not.toContain('💬');
  expect(tree).not.toContain('🧠');
});
