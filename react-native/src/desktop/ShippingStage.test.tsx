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

test('page stage uses 80ms ease-out on route change and never springs', () => {
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
  expect(durations).toContain(80);
  expect(
    timing.mock.calls.every(call => call[1]?.useNativeDriver === false),
  ).toBe(true);
  act(() => {
    renderer.unmount();
  });
  timing.mockRestore();
  spring.mockRestore();
});

test('search stage uses the 240ms hub-to-results step', () => {
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
  expect(durations).toContain(240);
  act(() => {
    renderer.unmount();
  });
  timing.mockRestore();
});

test('keeps a visible fallback when the stage child throws', () => {
  function Boom(): React.JSX.Element {
    throw new Error('stage exploded');
  }
  const spy = jest.spyOn(console, 'error').mockImplementation(() => undefined);
  let renderer: ReactTestRenderer.ReactTestRenderer;
  act(() => {
    renderer = ReactTestRenderer.create(
      <ShippingStage stageKey="Tasks" variant="page">
        <Boom />
      </ShippingStage>,
    );
  });
  expect(
    renderer!.root
      .findAllByType(Text)
      .some(node => node.props.children === 'This page could not be shown.'),
  ).toBe(true);
  act(() => {
    renderer.unmount();
  });
  spy.mockRestore();
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
