import React from 'react';
import {ActivityIndicator, Animated, StyleSheet, Text} from 'react-native';
import Renderer, {act} from 'react-test-renderer';
import {ChatMessageRow, ChatThinking} from './ChatTranscript';
import {DesktopChat} from '../desktop/DesktopChat';

jest.mock('../app/useReduceMotion', () => ({useReduceMotion: () => true}));

jest.mock('./OmiAvatar', () => ({OmiAvatar: () => null}));

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

test('pending skeleton stops its animation and stays visible with reduced motion', () => {
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
    expect(start).toHaveBeenCalledTimes(1);
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
    expect(stop).toHaveBeenCalledTimes(1);
    const style = StyleSheet.flatten(
      tree.root.findByType(Animated.View).props.style,
    );
    expect(style.opacity.__getValue()).toBe(1);
    act(() => tree.unmount());
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
