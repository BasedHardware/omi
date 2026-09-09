import React from 'react';
import {Alert, Image, Linking, StyleSheet, Text} from 'react-native';
import Renderer, {act} from 'react-test-renderer';
import {ChatMessageContent} from './ChatMessageContent';

function render(text: string) {
  let tree!: Renderer.ReactTestRenderer;
  act(() => {
    tree = Renderer.create(
      <ChatMessageContent text={text} style={{color: '#ddd', fontSize: 15}} />,
    );
  });
  return tree;
}

test('renders actual native markdown with selectable emphasis, lists and code', () => {
  const tree = render(
    '## Heading\n\n**Bold** and *italic*\n\n- First\n- Second\n\n```js\nconst answer = 42;\n```',
  );
  const texts = tree.root.findAllByType(Text);
  const bold = texts.find(node => node.props.children === 'Bold');
  expect(StyleSheet.flatten(bold?.props.style)).toMatchObject({
    fontWeight: '700',
    color: '#ddd',
  });
  expect(
    texts.some(
      node => node.props.children === 'Heading' && node.props.selectable,
    ),
  ).toBe(true);
  expect(
    texts.some(
      node =>
        node.props.children === 'const answer = 42;' && node.props.selectable,
    ),
  ).toBe(true);
  expect(JSON.stringify(tree.toJSON())).toContain('First');
  expect(JSON.stringify(tree.toJSON())).not.toContain('**Bold**');
  act(() => tree.unmount());
});

test('never fetches markdown images and opens only explicit safe web links', async () => {
  const open = jest.spyOn(Linking, 'openURL').mockResolvedValue(undefined);
  const tree = render(
    '![Private image](https://example.com/tracker.png)\n\n[Good](https://example.com) [Bad](file:///private/file) [Credential](https://user:pass@example.com)\n\n[![Linked image](https://example.com/image.png)](javascript:alert(1))',
  );
  expect(tree.root.findAllByType(Image)).toHaveLength(0);
  expect(open).not.toHaveBeenCalled();
  const links = tree.root
    .findAllByType(Text)
    .filter(node => node.props.accessibilityRole === 'link');
  expect(links).toHaveLength(1);
  await act(async () => {
    links[0].props.onPress();
  });
  expect(open).toHaveBeenCalledWith('https://example.com');
  act(() => tree.unmount());
  open.mockRestore();
});

test('does not depend on browser URL getters and preserves raw HTML as text', () => {
  const original = globalThis.URL;
  Object.defineProperty(globalThis, 'URL', {
    configurable: true,
    value: class {
      constructor() {
        throw new Error('Browser URL unavailable');
      }
    },
  });
  try {
    const tree = render(
      '[Website](https://example.com)\n\n<script>untrusted()</script>',
    );
    expect(
      tree.root
        .findAllByType(Text)
        .filter(node => node.props.accessibilityRole === 'link'),
    ).toHaveLength(1);
    expect(JSON.stringify(tree.toJSON())).toContain(
      '<script>untrusted()</script>',
    );
    act(() => tree.unmount());
  } finally {
    Object.defineProperty(globalThis, 'URL', {
      configurable: true,
      value: original,
    });
  }
});

test('reports a rejected explicit link open without displaying the URL', async () => {
  const open = jest
    .spyOn(Linking, 'openURL')
    .mockRejectedValue(new Error('private transport detail'));
  const alert = jest.spyOn(Alert, 'alert').mockImplementation(() => {});
  const tree = render('[Website](https://example.com)');
  await act(async () => {
    tree.root
      .findAllByType(Text)
      .find(node => node.props.accessibilityRole === 'link')
      ?.props.onPress();
  });
  expect(alert).toHaveBeenCalledWith(
    'Could not open link',
    'Please try again.',
  );
  act(() => tree.unmount());
  open.mockRestore();
  alert.mockRestore();
});
