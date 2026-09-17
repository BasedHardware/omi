import React from 'react';
import Renderer, {act} from 'react-test-renderer';
import {ScrollView, TextInput} from 'react-native';
import {MobileChat} from './MobileChat';
import {Composer} from '../ui/Composer';
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
    composer: (
      <Composer
        compact
        activeGenerationId={overrides.busy ? 'generation' : null}
        chatBusy={overrides.busy ?? false}
        composerFocused={false}
        composerMaxWidth={390}
        composerRef={{current: null}}
        draft="A draft"
        onDraftChange={jest.fn()}
        onFocusChange={jest.fn()}
        onSend={onSend}
        onStop={onStop}
      />
    ),
    ...overrides,
  };
  let tree!: Renderer.ReactTestRenderer;
  act(() => {
    tree = Renderer.create(<MobileChat {...props} />);
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
    scroll.findAll(node => node.props.accessibilityLabel === 'Back to Home'),
  ).toHaveLength(0);
  expect(scroll.findAllByType(TextInput)).toHaveLength(0);
  act(() => control('Back to Home').props.onPress());
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
