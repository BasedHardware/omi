import React from 'react';
import {Text} from 'react-native';
import ReactTestRenderer, {act} from 'react-test-renderer';
import {AppNav} from './AppNav';
import {FocusPressable} from './Pressable';

test('collapsed navigation keeps accessible destinations without hidden label layout', async () => {
  const navigate = jest.fn();
  let view!: ReactTestRenderer.ReactTestRenderer;
  await act(async () => {
    view = ReactTestRenderer.create(
      <AppNav
        compact={false}
        reduceMotion
        route="Home"
        onNavigate={navigate}
      />,
    );
  });
  try {
    const labels = () =>
      view.root.findAllByType(Text).map(node => node.props.children);
    const buttons = () => view.root.findAllByType(FocusPressable);
    expect(labels()).toEqual(['omi']);
    expect(
      buttons()
        .filter(node => node.props.accessibilityRole === 'tab')
        .map(node => node.props.accessibilityLabel),
    ).toEqual([
      'Home',
      'Conversations',
      'Memories',
      'Tasks',
      'Connectors',
      'Settings',
    ]);
    await act(async () =>
      buttons()
        .find(node => node.props.accessibilityLabel === 'Expand sidebar')!
        .props.onPress(),
    );
    expect(labels()).toContain('Settings');
    await act(async () =>
      buttons()
        .find(node => node.props.accessibilityLabel === 'Settings')!
        .props.onPress(),
    );
    expect(navigate).toHaveBeenCalledWith('Settings');
    await act(async () =>
      buttons()
        .find(node => node.props.accessibilityLabel === 'Collapse sidebar')!
        .props.onPress(),
    );
    expect(labels()).toEqual(['omi']);
  } finally {
    await act(async () => view.unmount());
  }
});

test('compact navigation retains visible destination labels', async () => {
  let view!: ReactTestRenderer.ReactTestRenderer;
  await act(async () => {
    view = ReactTestRenderer.create(
      <AppNav compact reduceMotion route="Settings" onNavigate={jest.fn()} />,
    );
  });
  try {
    expect(
      view.root.findAllByType(Text).map(node => node.props.children),
    ).toEqual([
      'Home',
      'Conversations',
      'Memories',
      'Tasks',
      'Connectors',
      'Settings',
    ]);
  } finally {
    await act(async () => view.unmount());
  }
});
