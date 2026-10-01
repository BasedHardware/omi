import React from 'react';
import Renderer, {act} from 'react-test-renderer';
import {StyleSheet, TextInput} from 'react-native';
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

test('one growing field: Return adds a line on the chat page and submits on Home', () => {
  const props = {
    mode: 'Ask' as const,
    value: 'Draft',
    onChange: jest.fn(),
    onModeChange: jest.fn(),
    onSubmit: jest.fn(),
    onStop: jest.fn(),
    busy: false,
    canStop: false,
    inputRef: {current: null},
  };
  let tree!: Renderer.ReactTestRenderer;
  act(() => {
    tree = Renderer.create(<MobileOmnibar {...props} />);
  });
  const input = tree.root.findByType(TextInput);
  expect(input.props.multiline).toBe(true);
  expect(input.props.submitBehavior).toBe('submit');
  act(() => tree.update(<MobileOmnibar {...props} chatPage />));
  // Same instance: sending from Home keeps focus and the keyboard.
  expect(tree.root.findByType(TextInput)).toBe(input);
  expect(input.props.submitBehavior).toBe('newline');
  const lineHeight = 22;
  act(() =>
    input.props.onContentSizeChange({
      nativeEvent: {contentSize: {height: lineHeight * 3 + 22}},
    }),
  );
  const grown = StyleSheet.flatten(input.props.style).height;
  expect(grown).toBeGreaterThan(44);
  act(() =>
    input.props.onContentSizeChange({
      nativeEvent: {contentSize: {height: 5000}},
    }),
  );
  const capped = StyleSheet.flatten(input.props.style).height;
  expect(capped).toBeLessThan(5000);
  expect(input.props.scrollEnabled).toBe(true);
  act(() => tree.update(<MobileOmnibar {...props} chatPage value="" />));
  expect(StyleSheet.flatten(input.props.style).height).toBe(44);
  act(() => tree.unmount());
});
