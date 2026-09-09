import React from 'react';
import {Text} from 'react-native';
import Renderer, {act} from 'react-test-renderer';
import {ScrollFade, useScrollFade} from './ScrollFade';

test('fades overflow and restores content at the end or after resize', () => {
  let fade!: ReturnType<typeof useScrollFade>;
  function Example() {
    fade = useScrollFade();
    return (
      <ScrollFade visible={fade.visible}>
        <Text>Content</Text>
      </ScrollFade>
    );
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
  expect(tree.root.findByType(Text).props.children).toBe('Content');
  act(() => {
    fade.onScroll({nativeEvent: {contentOffset: {y: 200}}} as never);
  });
  expect(fade.visible).toBe(false);
  act(() => {
    fade.onScroll({nativeEvent: {contentOffset: {y: 0}}} as never);
  });
  expect(fade.visible).toBe(true);
  act(() => {
    fade.onLayout({nativeEvent: {layout: {height: 400}}} as never);
  });
  expect(fade.visible).toBe(false);
  act(() => tree.unmount());
});
