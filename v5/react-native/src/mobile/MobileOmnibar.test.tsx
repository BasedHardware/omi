import React from 'react';
import Renderer, {act} from 'react-test-renderer';
import {TextInput} from 'react-native';
import {MobileOmnibar} from './MobileOmnibar';

test('stop is offered in every mode; Search submits when nothing can be stopped', () => {
  const onSubmit = jest.fn(),
    onStop = jest.fn(),
    onChange = jest.fn();
  const props = {
    value: 'A query',
    onSubmit,
    onStop,
    onChange,
    onModeChange: jest.fn(),
    busy: true,
    canStop: true,
    inputRef: {current: null},
  };
  let tree!: Renderer.ReactTestRenderer;
  act(() => {
    tree = Renderer.create(<MobileOmnibar {...props} mode="Search" />);
  });
  const input = tree.root.findByType(TextInput);
  act(() => input.props.onSubmitEditing());
  expect(onStop).toHaveBeenCalledTimes(1);
  expect(onSubmit).not.toHaveBeenCalled();
  act(() =>
    tree.update(
      <MobileOmnibar {...props} mode="Search" canStop={false} value="" />,
    ),
  );
  act(() => input.props.onSubmitEditing());
  expect(onStop).toHaveBeenCalledTimes(1);
  expect(onSubmit).not.toHaveBeenCalled();
  act(() =>
    tree.update(
      <MobileOmnibar {...props} mode="Search" canStop={false} value="Draft" />,
    ),
  );
  act(() => tree.root.findByType(TextInput).props.onSubmitEditing());
  expect(onSubmit).toHaveBeenCalledTimes(1);
  act(() =>
    tree.update(<MobileOmnibar {...props} mode="Ask" canStop value="" />),
  );
  expect(tree.root.findByType(TextInput)).toBe(input);
  act(() =>
    tree.root
      .findAllByProps({accessibilityLabel: 'Stop response'})[0]
      .props.onPress(),
  );
  act(() => tree.unmount());
});

test('the pushed Chat page keeps one Ask composer without a Search switch', () => {
  let tree!: Renderer.ReactTestRenderer;
  act(() => {
    tree = Renderer.create(
      <MobileOmnibar
        mode="Ask"
        chatPage
        value="Follow up"
        onChange={jest.fn()}
        onModeChange={jest.fn()}
        onSubmit={jest.fn()}
        onStop={jest.fn()}
        busy={false}
        canStop={false}
        inputRef={{current: null}}
      />,
    );
  });
  expect(
    tree.root.findAll(node => node.props.accessibilityLabel === 'Search mode'),
  ).toHaveLength(0);
  expect(tree.root.findByType(TextInput).props.accessibilityLabel).toBe(
    'Ask Omi',
  );
  act(() => tree.unmount());
});
