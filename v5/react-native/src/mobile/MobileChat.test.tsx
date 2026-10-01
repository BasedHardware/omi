import React from 'react';
import Renderer, {act} from 'react-test-renderer';
import {Pressable, ScrollView, Text, TextInput, View} from 'react-native';
import {MobileChat} from './MobileChat';
import {MobileOmnibar} from './MobileOmnibar';
import {ChatThinking} from '../ui/ChatTranscript';

jest.mock('../app/useReduceMotion', () => ({useReduceMotion: () => true}));
jest.mock('../omiNative', () => ({omiBackend: {}}));

function setup(
  overrides: Partial<React.ComponentProps<typeof MobileChat>> = {},
) {
  const onSend = jest.fn(),
    onStop = jest.fn();
  const props: React.ComponentProps<typeof MobileChat> = {
    messages: [],
    busy: false,
    error: null,
    loadingHistory: false,
    hasOlder: false,
    loadingOlder: false,
    onLoadOlder: jest.fn(),
    onClose: jest.fn(),
    onUsePrompt: jest.fn(),
    prompts: ['Find my next step'],
    scrollRef: {current: null},
    onScroll: jest.fn(),
    shouldAnimate: () => false,
    ...overrides,
  };
  let tree!: Renderer.ReactTestRenderer;
  act(() => {
    tree = Renderer.create(
      <View>
        <MobileChat {...props} />
        <MobileOmnibar
          mode="Ask"
          onModeChange={jest.fn()}
          inputRef={{current: null}}
          value="A draft"
          onChange={jest.fn()}
          busy={overrides.busy ?? false}
          canStop={overrides.busy ?? false}
          onSubmit={onSend}
          onStop={onStop}
        />
      </View>,
    );
  });
  const control = (label: string) =>
    tree.root.findAll(node => node.props.accessibilityLabel === label)[0];
  return {tree, props, control, onSend, onStop};
}

test('mobile chat keeps Back outside scrolling content and suggestions never send', () => {
  const {tree, props, control, onSend} = setup();
  act(() => control('Try: Find my next step').props.onPress());
  expect(props.onUsePrompt).toHaveBeenCalledWith('Find my next step');
  expect(onSend).not.toHaveBeenCalled();
  const scroll = tree.root.findByType(ScrollView);
  expect(
    scroll.findAll(node => node.props.accessibilityLabel === 'Back from chat'),
  ).toHaveLength(0);
  expect(scroll.findAllByType(TextInput)).toHaveLength(0);
  act(() => control('Back from chat').props.onPress());
  expect(props.onClose).toHaveBeenCalledTimes(1);
  act(() => tree.unmount());
});

test.each([
  {loadingHistory: true},
  {busy: true},
  {error: 'Please retry your request.'},
])(
  'mobile chat does not show a ready empty state while unsettled: %p',
  state => {
    const {tree} = setup(state);
    expect(
      tree.root.findAll(
        node => node.props.accessibilityLabel === 'Try: Find my next step',
      ),
    ).toHaveLength(0);
    if (state.error) {
      expect(
        tree.root.findAll(node => node.props.accessibilityRole === 'alert')
          .length,
      ).toBeGreaterThan(0);
    }
    act(() => tree.unmount());
  },
);

test('streaming chat uses one pending response, retains stop and gates older loading', () => {
  const {tree, control, onSend, onStop} = setup({
    busy: true,
    hasOlder: true,
    loadingOlder: true,
    messages: [
      {
        id: 'pending:1',
        sender: 'ai',
        text: '',
        createdAt: 1000,
        generationId: 'generation',
        generationOutcome: null,
      },
    ],
  });
  // One thinking indicator: the pending reply's own, never a second row.
  expect(tree.root.findAllByType(ChatThinking)).toHaveLength(1);
  expect(control('Waiting for response').props.accessibilityState.busy).toBe(
    true,
  );
  expect(control('Load earlier messages').props.disabled).toBe(true);
  act(() => control('Stop response').props.onPress());
  expect(onStop).toHaveBeenCalledTimes(1);
  expect(onSend).not.toHaveBeenCalled();
  act(() => tree.unmount());
});

test('scrolling away exposes Jump to Latest and restores follow on activation', () => {
  const scrollToEnd = jest
    .spyOn(ScrollView.prototype, 'scrollToEnd')
    .mockImplementation(() => undefined);
  const onJumpLatest = jest.fn();
  const {tree, control} = setup({
    messages: [
      {
        id: 'reply',
        sender: 'ai',
        text: 'Answer',
        createdAt: 1000,
        generationOutcome: 'completed',
      },
    ],
    onJumpLatest,
  });
  const scroll = tree.root.findByType(ScrollView);
  // A programmatic scroll (content growing) never counts as leaving the end.
  act(() =>
    scroll.props.onScroll({
      nativeEvent: {
        contentOffset: {y: 0},
        contentSize: {height: 1000},
        layoutMeasurement: {height: 200},
      },
    }),
  );
  expect(control('Jump to Latest')).toBeUndefined();
  act(() => {
    scroll.props.onScrollBeginDrag();
    scroll.props.onScroll({
      nativeEvent: {
        contentOffset: {y: 0},
        contentSize: {height: 1000},
        layoutMeasurement: {height: 200},
      },
    });
  });
  act(() => control('Jump to Latest').props.onPress());
  expect(onJumpLatest).toHaveBeenCalledTimes(1);
  expect(scrollToEnd).toHaveBeenCalled();
  act(() => tree.unmount());
  scrollToEnd.mockRestore();
});

test('a failed history read says so with Try Again instead of an empty chat', () => {
  const onRetryHistory = jest.fn();
  const {tree, control} = setup({
    historyFailed: true,
    onRetryHistory,
    error: 'Chat history could not be loaded.',
  });
  const text = JSON.stringify(tree.toJSON());
  expect(text).toContain('Couldn’t Load Chat');
  expect(text).not.toContain('What’s on your mind?');
  expect(control('Try: Find my next step')).toBeUndefined();
  act(() => control('Try Again').props.onPress());
  expect(onRetryHistory).toHaveBeenCalledTimes(1);
  act(() => tree.unmount());
});

test('a failed first send keeps the greeting, hides prompts and says so near the composer', () => {
  const {tree, control} = setup({error: 'Message not sent.'});
  expect(JSON.stringify(tree.toJSON())).toContain('What’s on your mind?');
  expect(control('Try: Find my next step')).toBeUndefined();
  const alert = tree.root.find(
    node =>
      node.props.accessibilityRole === 'alert' && typeof node.type !== 'string',
  );
  expect(alert.findAllByType(Text).map(node => node.props.children)).toContain(
    'Message not sent.',
  );
  act(() => tree.unmount());
});

test('older replies open their actions with a long press; the newest shows its bar', () => {
  const sheet = jest.fn();
  const RN = require('react-native');
  RN.ActionSheetIOS.showActionSheetWithOptions = sheet;
  const onRetry = jest.fn();
  const {tree, control} = setup({
    onRetry,
    messages: [
      {
        id: 'h1',
        sender: 'human',
        text: 'First',
        createdAt: 1000,
        generationOutcome: null,
      },
      {
        id: 'a1',
        sender: 'ai',
        text: 'Older answer',
        createdAt: 1001,
        generationOutcome: 'completed',
      },
      {
        id: 'h2',
        sender: 'human',
        text: 'Second',
        createdAt: 1002,
        generationOutcome: null,
      },
      {
        id: 'a2',
        sender: 'ai',
        text: 'Newest answer',
        createdAt: 1003,
        generationOutcome: 'completed',
      },
    ],
  });
  // Phones show no permanent icons under older replies; the newest keeps one.
  expect(
    tree.root.findAll(
      node =>
        node.props.accessibilityLabel === 'Share or copy response' &&
        typeof node.type !== 'string',
    ).length,
  ).toBeGreaterThan(0);
  const older = tree.root
    .findAllByType(Pressable)
    .filter(node => typeof node.props.onLongPress === 'function');
  expect(older).toHaveLength(1);
  act(() => older[0].props.onLongPress());
  expect(sheet).toHaveBeenCalledTimes(1);
  expect(sheet.mock.calls[0][0].options).toEqual(['Share or Copy', 'Cancel']);
  expect(control('Response').props.accessibilityHint).toContain('Long press');
  act(() => tree.unmount());
});
