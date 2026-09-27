import React from 'react';
import {Text} from 'react-native';
import ReactTestRenderer, {act} from 'react-test-renderer';
import {AppNav} from './AppNav';
import {FocusPressable} from './Pressable';

// MaterialIcon glyphs render as Text with the icon font; labels don't.
const labelTexts = (view: ReactTestRenderer.ReactTestRenderer) =>
  view.root
    .findAllByType(Text)
    .filter(node => {
      const styles = Array.isArray(node.props.style)
        ? (node.props.style as unknown[])
        : [node.props.style];
      const fontFamily = styles.find(
        s =>
          typeof s === 'object' &&
          s !== null &&
          'fontFamily' in s &&
          (s as {fontFamily?: string}).fontFamily ===
            'Material Symbols Rounded',
      );
      return !fontFamily;
    })
    .map(node => node.props.children);

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
    const buttons = () => view.root.findAllByType(FocusPressable);
    expect(labelTexts(view)).toEqual(['omi']);
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
    expect(labelTexts(view)).toContain('Settings');
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
    expect(labelTexts(view)).toEqual(['omi']);
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
    expect(labelTexts(view)).toEqual([
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
