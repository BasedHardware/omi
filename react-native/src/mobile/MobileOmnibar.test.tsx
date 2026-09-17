import React from 'react';
import Renderer, {act} from 'react-test-renderer';
import {Text, TextInput} from 'react-native';
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

test('Ask keeps Live beside Send; Search hides it', () => {
  const live = <Text>Live control</Text>;
  let tree!: Renderer.ReactTestRenderer;
  act(() => {
    tree = Renderer.create(
      <MobileOmnibar
        mode="Ask"
        value=""
        onChange={jest.fn()}
        onSubmit={jest.fn()}
        onStop={jest.fn()}
        onModeChange={jest.fn()}
        busy={false}
        canStop={false}
        inputRef={{current: null}}
        liveControl={live}
      />,
    );
  });
  expect(JSON.stringify(tree.toJSON())).toContain('Live control');
  act(() =>
    tree.update(
      <MobileOmnibar
        mode="Search"
        value=""
        onChange={jest.fn()}
        onSubmit={jest.fn()}
        onStop={jest.fn()}
        onModeChange={jest.fn()}
        busy={false}
        canStop={false}
        inputRef={{current: null}}
        liveControl={live}
      />,
    ),
  );
  expect(JSON.stringify(tree.toJSON())).not.toContain('Live control');
  act(() => tree.unmount());
});

test('Search is the default-style inline icon and the transparent dock has no mode row', () => {
  let tree!: Renderer.ReactTestRenderer;
  act(() => {
    tree = Renderer.create(
      <MobileOmnibar
        mode="Search"
        value=""
        onChange={jest.fn()}
        onSubmit={jest.fn()}
        onStop={jest.fn()}
        onModeChange={jest.fn()}
        busy={false}
        canStop={false}
        inputRef={{current: null}}
      />,
    );
  });
  const dock = tree.root.findByProps({
    accessibilityLabel: 'Ask and search dock',
  });
  expect(dock.props.style.backgroundColor).toBe('transparent');
  expect(
    tree.root.findByProps({accessibilityLabel: 'Search mode'}).props
      .accessibilityState.selected,
  ).toBe(true);
  expect(
    tree.root.findByProps({accessibilityLabel: 'Ask mode'}).findAllByType(Text),
  ).toHaveLength(0);
  expect(tree.root.findByType(TextInput).props.accessibilityLabel).toBe(
    'Search loaded data',
  );
  act(() => tree.unmount());
});
