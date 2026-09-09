import React from 'react';
import {ActivityIndicator, Animated, StyleSheet, Text} from 'react-native';
import Renderer, {act} from 'react-test-renderer';
import {ChatMessageRow, ChatThinking} from './ChatTranscript';
import {DesktopChat} from '../desktop/DesktopChat';
import {OmiAvatar, omiMarkGeometry} from './OmiAvatar';

jest.mock('../app/useReduceMotion', () => ({useReduceMotion: () => true}));

test('retires row animation and restores a row when animation is disabled', () => {
  const stop = jest.fn();
  const animation = jest.spyOn(Animated, 'parallel').mockReturnValue({
    start: jest.fn(),
    stop,
    reset: jest.fn(),
  });
  const message = {
    id: 'message',
    sender: 'human' as const,
    text: 'Hello',
    createdAt: 1000,
    generationOutcome: null,
  };
  let tree!: Renderer.ReactTestRenderer;
  act(() => {
    tree = Renderer.create(
      <ChatMessageRow
        message={message}
        animate
        compact={false}
        reduceMotion={false}
      />,
    );
  });
  act(() => {
    tree.update(
      <ChatMessageRow
        message={message}
        animate={false}
        compact={false}
        reduceMotion={false}
      />,
    );
  });
  expect(stop).toHaveBeenCalledTimes(1);
  const style = tree.root.findByType(Animated.View).props.style.at(-1);
  expect(style.opacity.__getValue()).toBe(1);
  expect(style.transform[0].translateY.__getValue()).toBe(0);
  act(() => {
    tree.update(
      <ChatMessageRow
        message={message}
        animate
        compact={false}
        reduceMotion={false}
      />,
    );
  });
  act(() => tree.unmount());
  expect(stop).toHaveBeenCalledTimes(2);
  animation.mockRestore();
});

test.each([false, true])(
  'AI replies have bubbles and user messages are unboxed (desktop=%s)',
  desktop => {
    let tree!: Renderer.ReactTestRenderer;
    const message = {
      id: 'message',
      sender: 'human' as const,
      text: 'Message content',
      createdAt: 1000,
      generationOutcome: null,
    };
    act(() => {
      tree = Renderer.create(
        <ChatMessageRow
          message={message}
          animate={false}
          compact={!desktop}
          desktop={desktop}
          reduceMotion
        />,
      );
    });
    const bubble = () =>
      StyleSheet.flatten(
        tree.root.find(
          node =>
            node.type === Text && node.props.children === 'Message content',
        ).parent!.props.style,
      );
    expect(bubble().backgroundColor).toBe('transparent');
    expect(bubble().borderWidth).toBe(0);
    act(() =>
      tree.update(
        <ChatMessageRow
          message={{...message, sender: 'ai'}}
          animate={false}
          compact={!desktop}
          desktop={desktop}
          reduceMotion
        />,
      ),
    );
    expect(bubble().backgroundColor).not.toBe('transparent');
    act(() => tree.unmount());
  },
);

test('streaming assistant row keeps the Omi mark moving and replaces skeleton with text', () => {
  const start = jest.fn();
  const stop = jest.fn();
  const loop = jest
    .spyOn(Animated, 'loop')
    .mockReturnValue({start, stop, reset: jest.fn()});
  const pending = {
    id: 'pending:human',
    sender: 'ai' as const,
    text: '',
    createdAt: 1000,
    generationOutcome: null,
    generationId: 'generation-1',
  };
  let tree!: Renderer.ReactTestRenderer;
  try {
    act(() => {
      tree = Renderer.create(
        <ChatMessageRow
          message={pending}
          animate={false}
          compact={false}
          reduceMotion={false}
        />,
      );
    });
    expect(start).toHaveBeenCalled();
    expect(
      tree.root.findAll(
        node => node.props.accessibilityLabel === 'Waiting for response',
      ).length,
    ).toBeGreaterThan(0);
    act(() =>
      tree.update(
        <ChatMessageRow
          message={{...pending, text: 'Hello'}}
          animate={false}
          compact={false}
          reduceMotion={false}
        />,
      ),
    );
    expect(
      tree.root.findAll(
        node => node.props.accessibilityLabel === 'Waiting for response',
      ),
    ).toHaveLength(0);
    expect(tree.root.findByType(OmiAvatar).props.animate).toBe(true);
    act(() =>
      tree.update(
        <ChatMessageRow
          message={{
            ...pending,
            text: 'Hello',
            generationOutcome: 'completed',
            generationId: undefined,
          }}
          animate={false}
          compact={false}
          reduceMotion
        />,
      ),
    );
    expect(tree.root.findByType(OmiAvatar).props.animate).toBe(false);
    act(() => tree.unmount());
  } finally {
    loop.mockRestore();
  }
});

test('pending Omi mark circles beside the skeleton and both stop for reduced motion or unmount', () => {
  const start = jest.fn();
  const stop = jest.fn();
  const loop = jest
    .spyOn(Animated, 'loop')
    .mockReturnValue({start, stop, reset: jest.fn()});
  let tree!: Renderer.ReactTestRenderer;
  try {
    act(() => {
      tree = Renderer.create(<ChatThinking reduceMotion={false} desktop />);
    });
    expect(start).toHaveBeenCalledTimes(2);
    const avatar = tree.root.findByType(OmiAvatar);
    expect(avatar.props).toMatchObject({tone: 'ink', animate: true});
    expect(omiMarkGeometry.lapMs).toBe(900);
    const dots = avatar.findAllByType(Animated.View);
    expect(dots).toHaveLength(8);
    expect(StyleSheet.flatten(dots[0].props.style).opacity.__getValue()).toBe(
      1,
    );
    expect(StyleSheet.flatten(dots[4].props.style).opacity.__getValue()).toBe(
      0.5,
    );
    expect(
      tree.root.findAll(
        node => node.props.accessibilityLabel === 'Waiting for response',
      ).length,
    ).toBeGreaterThan(0);
    expect(
      tree.root.findAll(
        node => node.props.accessibilityLabel === 'Waiting for response',
      )[0]?.props.accessible,
    ).toBe(true);
    expect(tree.root.findAllByType(ActivityIndicator)).toHaveLength(0);
    act(() => tree.update(<ChatThinking reduceMotion desktop />));
    expect(stop).toHaveBeenCalledTimes(2);
    expect(
      tree.root
        .findByType(OmiAvatar)
        .findAllByType(Animated.View)
        .every(dot => StyleSheet.flatten(dot.props.style).opacity === 1),
    ).toBe(true);
    const style = StyleSheet.flatten(
      tree.root
        .findAllByType(Animated.View)
        .find(node => node.props.accessible === false)!.props.style,
    );
    expect(style.opacity.__getValue()).toBe(1);
    act(() => tree.update(<ChatThinking reduceMotion={false} />));
    expect(start).toHaveBeenCalledTimes(4);
    expect(tree.root.findByType(OmiAvatar).props.tone).toBe('ink');
    act(() => tree.unmount());
    expect(stop).toHaveBeenCalledTimes(4);
  } finally {
    loop.mockRestore();
  }
});

test('desktop pending skeleton disappears when a request fails and failure remains visible', () => {
  let tree!: Renderer.ReactTestRenderer;
  const props = {
    submission: 0,
    messages: [],
    busy: true,
    error: null,
    hasOlder: false,
    loadingOlder: false,
    onLoadOlder: jest.fn(),
    onClose: jest.fn(),
  };
  act(() => {
    tree = Renderer.create(<DesktopChat {...props} />);
  });
  expect(
    tree.root.findAll(
      node => node.props.accessibilityLabel === 'Waiting for response',
    ).length,
  ).toBeGreaterThan(0);
  expect(tree.root.findAllByType(ActivityIndicator)).toHaveLength(0);
  act(() =>
    tree.update(
      <DesktopChat
        {...props}
        busy={false}
        error="Request failed"
        messages={[
          {
            id: 'failed',
            text: '',
            sender: 'ai',
            createdAt: 1000,
            generationOutcome: 'failed',
          },
        ]}
      />,
    ),
  );
  expect(
    tree.root.findAll(
      node => node.props.accessibilityLabel === 'Waiting for response',
    ),
  ).toHaveLength(0);
  expect(
    tree.root.findAllByType(Text).map(node => node.props.children),
  ).toContain('Response failed.');
  expect(
    tree.root.findAllByType(Text).map(node => node.props.children),
  ).toContain('Request failed');
  act(() => tree.unmount());
});
