import React from 'react';
import {Animated} from 'react-native';
import Renderer, {act} from 'react-test-renderer';
import {ChatMessageRow} from './ChatTranscript';

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
