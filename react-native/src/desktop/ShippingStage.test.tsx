import React from 'react';
import {Animated, Text} from 'react-native';
import ReactTestRenderer, {act} from 'react-test-renderer';
import {ShippingListInsert, ShippingStage} from './ShippingStage';

let mockReduceMotion = false;

jest.mock('../app/useReduceMotion', () => ({
  useReduceMotion: () => mockReduceMotion,
}));

afterEach(() => {
  mockReduceMotion = false;
});

test('page stage uses 250ms smooth-out on route change and never springs', () => {
  const timing = jest.spyOn(Animated, 'timing');
  const spring = jest.spyOn(Animated, 'spring');
  let renderer: ReactTestRenderer.ReactTestRenderer;
  act(() => {
    renderer = ReactTestRenderer.create(
      <ShippingStage stageKey="Home" variant="page">
        <Text>Home</Text>
      </ShippingStage>,
    );
  });
  expect(timing).not.toHaveBeenCalled();
  act(() => {
    renderer.update(
      <ShippingStage stageKey="Library" variant="page">
        <Text>Library</Text>
      </ShippingStage>,
    );
  });
  expect(spring).not.toHaveBeenCalled();
  expect(timing).toHaveBeenCalled();
  const durations = timing.mock.calls.map(call => call[1]?.duration);
  expect(durations).toContain(250);
  act(() => {
    renderer.unmount();
  });
  timing.mockRestore();
  spring.mockRestore();
});

test('search stage uses the 250ms hub-to-results step', () => {
  const timing = jest.spyOn(Animated, 'timing');
  let renderer: ReactTestRenderer.ReactTestRenderer;
  act(() => {
    renderer = ReactTestRenderer.create(
      <ShippingStage stageKey="chat" variant="hub">
        <Text>Chat</Text>
      </ShippingStage>,
    );
  });
  act(() => {
    renderer.update(
      <ShippingStage stageKey="search" variant="search">
        <Text>Results</Text>
      </ShippingStage>,
    );
  });
  const durations = timing.mock.calls.map(call => call[1]?.duration);
  expect(durations).toContain(250);
  act(() => {
    renderer.unmount();
  });
  timing.mockRestore();
});

test('reduce-motion keeps stage and list insert instant', () => {
  mockReduceMotion = true;
  const timing = jest.spyOn(Animated, 'timing');
  const spring = jest.spyOn(Animated, 'spring');
  let renderer: ReactTestRenderer.ReactTestRenderer;
  act(() => {
    renderer = ReactTestRenderer.create(
      <ShippingStage stageKey="Home" variant="page">
        <ShippingListInsert itemKey="row-1">
          <Text>Row</Text>
        </ShippingListInsert>
      </ShippingStage>,
    );
  });
  act(() => {
    renderer.update(
      <ShippingStage stageKey="Library" variant="page">
        <ShippingListInsert itemKey="row-2">
          <Text>Row</Text>
        </ShippingListInsert>
      </ShippingStage>,
    );
  });
  expect(timing).not.toHaveBeenCalled();
  expect(spring).not.toHaveBeenCalled();
  act(() => {
    renderer.unmount();
  });
  timing.mockRestore();
  spring.mockRestore();
});
