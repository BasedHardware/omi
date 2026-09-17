import React from 'react';
import Renderer, {act} from 'react-test-renderer';
import {TextInput} from 'react-native';
import {MobileOmnibar} from './MobileOmnibar';

test('search submits without cancelling an active reply; Ask stops it and retains the same input', () => {
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
  expect(onSubmit).toHaveBeenCalledTimes(1);
  expect(onStop).not.toHaveBeenCalled();
  act(() => tree.update(<MobileOmnibar {...props} mode="Ask" value="" />));
  expect(tree.root.findByType(TextInput)).toBe(input);
  act(() =>
    tree.root
      .findAllByProps({accessibilityLabel: 'Stop response'})[0]
      .props.onPress(),
  );
  expect(onStop).toHaveBeenCalledTimes(1);
  expect(onSubmit).toHaveBeenCalledTimes(1);
  act(() =>
    tree.update(
      <MobileOmnibar {...props} mode="Ask" canStop={false} value="   " />,
    ),
  );
  act(() => tree.root.findByType(TextInput).props.onSubmitEditing());
  expect(onSubmit).toHaveBeenCalledTimes(1);
  act(() => tree.unmount());
});
