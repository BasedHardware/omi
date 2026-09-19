import React from 'react';
import Renderer, {act} from 'react-test-renderer';
import {ScrollView, TextInput, View} from 'react-native';
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
    scroll.findAll(node => node.props.accessibilityLabel === 'Close chat'),
  ).toHaveLength(0);
  expect(scroll.findAllByType(TextInput)).toHaveLength(0);
  act(() => control('Close chat').props.onPress());
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
    if (state.error)
      expect(
        tree.root.findAll(node => node.props.accessibilityRole === 'alert')
          .length,
      ).toBeGreaterThan(0);
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
  expect(tree.root.findAllByType(ChatThinking)).toHaveLength(0);
  expect(control('Waiting for response').props.accessibilityState.busy).toBe(
    true,
  );
  expect(control('Load older messages').props.disabled).toBe(true);
  act(() => control('Stop response').props.onPress());
  expect(onStop).toHaveBeenCalledTimes(1);
  expect(onSend).not.toHaveBeenCalled();
  act(() => tree.unmount());
});

test('compact responses show only the latest result with one close control', () => {
  const onRemember = jest.fn();
  const {tree, control} = setup({
    presentation: 'compact',
    hasOlder: true,
    onRemember,
    messages: [
      {
        id: 'human-1',
        sender: 'human',
        text: 'Help me turn these ideas into a plan.',
        createdAt: 900,
        generationOutcome: null,
      },
      {
        id: 'assistant-1',
        sender: 'ai',
        text: 'The launch review is Friday afternoon.',
        createdAt: 1000,
        generationOutcome: 'completed',
      },
    ],
  });
  expect(control('Expand response')).toBeUndefined();
  expect(control('Load older messages')).toBeUndefined();
  expect(control('Close chat')).toBeDefined();
  expect(
    tree.root.findAll(
      node =>
        String(node.type) === 'Text' &&
        node.props.children === 'Help me turn these ideas into a plan.',
    ),
  ).toHaveLength(0);
  act(() => control('Remember response').props.onPress());
  expect(onRemember).toHaveBeenCalledWith(
    expect.objectContaining({id: 'assistant-1'}),
  );
  act(() => tree.unmount());
});

test('long overlay keeps loaded history visible and exposes older-page loading', () => {
  const {tree, control, props} = setup({
    presentation: 'overlay',
    hasOlder: true,
    messages: [
      {
        id: 'human-old',
        sender: 'human',
        text: 'Earlier question',
        createdAt: 1,
        generationOutcome: null,
      },
      {
        id: 'assistant-old',
        sender: 'ai',
        text: 'Earlier answer',
        createdAt: 2,
        generationOutcome: 'completed',
      },
      {
        id: 'assistant-latest',
        sender: 'ai',
        text: 'Latest answer that is deliberately long enough to use the full overlay.',
        createdAt: 3,
        generationOutcome: 'completed',
      },
    ],
  });
  const text = JSON.stringify(tree.toJSON());
  expect(text).toContain('Earlier question');
  expect(text).toContain('Earlier answer');
  act(() => control('Load older messages').props.onPress());
  expect(props.onLoadOlder).toHaveBeenCalledTimes(1);
  act(() => tree.unmount());
});
