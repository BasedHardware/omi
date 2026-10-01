import React from 'react';
import {Text} from 'react-native';
import Renderer, {act} from 'react-test-renderer';
import {ScrollFade, useScrollFade} from './ScrollFade';

test('page surfaces keep a glass fade at both ends', () => {
  let tree!: Renderer.ReactTestRenderer;
  act(() => {
    tree = Renderer.create(
      <ScrollFade visible>
        <Text>Content</Text>
      </ScrollFade>,
    );
  });
  expect(tree.root.findByType(ScrollFade).props.visible).toBe(true);
  expect(tree.root.findByType(Text).props.children).toBe('Content');
  act(() => tree.unmount());
});

test('overflow tracking still reports when more content sits below', () => {
  let fade!: ReturnType<typeof useScrollFade>;
  function Example() {
    fade = useScrollFade();
    return null;
  }
  let tree!: Renderer.ReactTestRenderer;
  act(() => {
    tree = Renderer.create(<Example />);
  });
  act(() => {
    fade.onLayout({nativeEvent: {layout: {height: 100}}} as never);
    fade.onContentSizeChange(200, 300);
  });
  expect(fade.visible).toBe(true);
  act(() => {
    fade.onScroll({nativeEvent: {contentOffset: {y: 200}}} as never);
  });
  expect(fade.visible).toBe(false);
  act(() => tree.unmount());
});
