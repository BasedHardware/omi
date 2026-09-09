import React from 'react';
import Renderer, {act} from 'react-test-renderer';
import {Animated, Pressable, StyleSheet, View} from 'react-native';
import {FocusPressable} from '../ui/Pressable';
import {ShippingPressable} from './ShippingPressable';
let mockReduceMotion = false;
jest.mock('../app/useReduceMotion', () => ({
  useReduceMotion: () => mockReduceMotion,
}));
const animations: {stop: jest.Mock}[] = [];
let timing: jest.SpyInstance;
const mounted: Renderer.ReactTestRenderer[] = [];
beforeEach(() => {
  mockReduceMotion = false;
  animations.length = 0;
  timing = jest
    .spyOn(Animated, 'timing')
    .mockImplementation((value, config) => {
      const animation = {
        start: jest.fn(() =>
          (value as Animated.Value).setValue(config.toValue as number),
        ),
        stop: jest.fn(),
        reset: jest.fn(),
      };
      animations.push(animation);
      return animation;
    });
});
afterEach(() => {
  act(() => mounted.splice(0).forEach(view => view.unmount()));
  timing.mockRestore();
});
function render(props: React.ComponentProps<typeof ShippingPressable> = {}) {
  let view!: Renderer.ReactTestRenderer;
  act(() => {
    view = Renderer.create(<ShippingPressable {...props} />);
  });
  mounted.push(view);
  return view;
}
function control(view: Renderer.ReactTestRenderer) {
  return view.root.findByType(FocusPressable);
}
function values(view: Renderer.ReactTestRenderer) {
  const style = control(view).props.style;
  expect(typeof style).not.toBe('function');
  const flat = StyleSheet.flatten(style);
  return {
    opacity: flat.opacity?.__getValue?.() ?? flat.opacity,
    transform: flat.transform?.map((item: {scale?: number | Animated.Value}) =>
      item.scale && typeof item.scale === 'object'
        ? {
            scale: (
              item.scale as unknown as {__getValue(): number}
            ).__getValue(),
          }
        : item,
    ),
  };
}

test('press animates actual control style, composes handlers/styles, and stops on release/unmount', () => {
  const onPressIn = jest.fn(),
    onPressOut = jest.fn();
  const style = jest.fn(({pressed}: {pressed: boolean}) => ({
    opacity: 0.5,
    padding: pressed ? 9 : 8,
    transform: [{translateX: 2}],
  }));
  const view = render({onPressIn, onPressOut, style});
  act(() => control(view).props.onPressIn({nativeEvent: {}}));
  expect(onPressIn).toHaveBeenCalledTimes(1);
  expect(values(view).opacity).toBeCloseTo(0.46);
  expect(values(view).transform).toEqual([{translateX: 2}, {scale: 0.985}]);
  expect(style).toHaveBeenLastCalledWith({pressed: true});
  expect(timing).toHaveBeenCalledWith(
    expect.anything(),
    expect.objectContaining({duration: 120, toValue: 1, useNativeDriver: true}),
  );
  const pressAnimation = animations[animations.length - 1]!;
  act(() => control(view).props.onPressOut({nativeEvent: {}}));
  expect(onPressOut).toHaveBeenCalledTimes(1);
  expect(pressAnimation.stop).toHaveBeenCalled();
  expect(values(view).transform).toEqual([{translateX: 2}, {scale: 1}]);
  const remaining = animations[animations.length - 1]!;
  act(() => view.unmount());
  expect(remaining.stop).toHaveBeenCalled();
});

test('reduced motion never scales, and disabled controls remain unpressed', () => {
  mockReduceMotion = true;
  const view = render();
  act(() => control(view).props.onPressIn({}));
  expect(values(view).transform).toBeUndefined();
  expect(values(view).opacity).toBeCloseTo(0.92);
  expect(timing).not.toHaveBeenCalled();
  act(() => view.update(<ShippingPressable disabled />));
  expect(values(view).opacity).toBe(1);
  act(() => control(view).props.onPressIn({}));
  expect(values(view).opacity).toBe(1);
  expect(view.root.findByType(Pressable).props.disabled).toBe(true);
});

test('hover uses existing neutral fill and active selection remains stronger', () => {
  const onHoverIn = jest.fn(),
    onHoverOut = jest.fn();
  const view = render({onHoverIn, onHoverOut});
  act(() => control(view).props.onHoverIn({}));
  expect(onHoverIn).toHaveBeenCalledTimes(1);
  expect(timing).toHaveBeenLastCalledWith(
    expect.anything(),
    expect.objectContaining({toValue: 0.5, useNativeDriver: false}),
  );
  act(() => view.update(<ShippingPressable active onHoverOut={onHoverOut} />));
  expect(timing).toHaveBeenLastCalledWith(
    expect.anything(),
    expect.objectContaining({toValue: 1}),
  );
  act(() => control(view).props.onHoverOut({}));
  expect(onHoverOut).toHaveBeenCalledTimes(1);
  expect(timing).toHaveBeenLastCalledWith(
    expect.anything(),
    expect.objectContaining({toValue: 1}),
  );
});

test('shared focus primitive forwards the native ref and preserves focus callbacks/disabled state', () => {
  const ref = React.createRef<React.ElementRef<typeof Pressable>>();
  const onFocus = jest.fn(),
    onBlur = jest.fn();
  const native = {focus: jest.fn()};
  let view!: Renderer.ReactTestRenderer;
  act(() => {
    view = Renderer.create(
      <FocusPressable
        ref={ref}
        onFocus={onFocus}
        onBlur={onBlur}
        accessibilityState={{disabled: true}}
      />,
      {createNodeMock: element => (element.type === View ? native : null)},
    );
  });
  mounted.push(view);
  expect(
    ref.current !== null && ref.current === view.root.findByType(View).instance,
  ).toBe(true);
  const pressable = view.root.findByType(Pressable);
  act(() => pressable.props.onFocus({}));
  expect(onFocus).toHaveBeenCalledTimes(1);
  expect(
    StyleSheet.flatten(pressable.props.style({pressed: false})).borderWidth,
  ).toBeGreaterThan(0);
  act(() => pressable.props.onBlur({}));
  expect(onBlur).toHaveBeenCalledTimes(1);
  expect(pressable.props.disabled).toBe(true);
});
