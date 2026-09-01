import React from 'react';
import {Animated, Text} from 'react-native';
import ReactTestRenderer, {act} from 'react-test-renderer';
import {ChipRail} from './ChipRail';

let mockReduceMotion = false;

jest.mock('../app/useReduceMotion', () => ({
  useReduceMotion: () => mockReduceMotion,
}));

jest.mock('../ui/GlassPanel', () => {
  const ReactModule = require('react');
  const {View} = require('react-native');
  return {
    GlassPanel: (props: Record<string, unknown>) =>
      ReactModule.createElement(View, props),
  };
});

afterEach(() => {
  mockReduceMotion = false;
});

const labels = ['All', 'Conversations', 'Memories', 'Tasks', 'Rewind'] as const;

function layoutChip(
  renderer: ReactTestRenderer.ReactTestRenderer,
  label: string,
  x: number,
) {
  const chip = renderer.root
    .findAll(node => node.props.accessibilityRole === 'button')
    .find(node =>
      node.findAllByType(Text).some(text => text.props.children === label),
    );
  act(() => {
    chip!.props.onLayout({
      nativeEvent: {layout: {x, y: 0, width: 64, height: 28}},
    });
  });
}

test('slides a glass pill behind the selected chip in 120ms ease-out', () => {
  const timing = jest.spyOn(Animated, 'timing');
  const spring = jest.spyOn(Animated, 'spring');
  const onChange = jest.fn();
  let renderer: ReactTestRenderer.ReactTestRenderer;
  act(() => {
    renderer = ReactTestRenderer.create(
      <ChipRail labels={labels} onChange={onChange} value="All" />,
    );
  });
  layoutChip(renderer!, 'All', 0);
  layoutChip(renderer!, 'Conversations', 70);
  timing.mockClear();
  act(() => {
    renderer.update(
      <ChipRail labels={labels} onChange={onChange} value="Conversations" />,
    );
  });
  const durations = timing.mock.calls.map(call => call[1]?.duration);
  expect(durations).toContain(120);
  expect(spring).not.toHaveBeenCalled();
  act(() => {
    renderer.unmount();
  });
  timing.mockRestore();
  spring.mockRestore();
});

test('reduce-motion keeps the chip pill instant', () => {
  mockReduceMotion = true;
  const timing = jest.spyOn(Animated, 'timing');
  const onChange = jest.fn();
  let renderer: ReactTestRenderer.ReactTestRenderer;
  act(() => {
    renderer = ReactTestRenderer.create(
      <ChipRail labels={labels} onChange={onChange} value="All" />,
    );
  });
  layoutChip(renderer!, 'All', 0);
  layoutChip(renderer!, 'Tasks', 210);
  timing.mockClear();
  act(() => {
    renderer.update(
      <ChipRail labels={labels} onChange={onChange} value="Tasks" />,
    );
  });
  expect(timing).not.toHaveBeenCalled();
  act(() => {
    renderer.unmount();
  });
  timing.mockRestore();
});
