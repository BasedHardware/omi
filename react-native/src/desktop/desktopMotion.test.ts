import {Animated} from 'react-native';
import {desktopMotion} from './desktopChrome';
import {
  glassMotionDuration,
  listInsertMotionDuration,
  motionDuration,
  runShippingTiming,
} from './desktopMotion';

test('chrome motion snaps under reduce-motion and never uses a spring', () => {
  const timing = jest.spyOn(Animated, 'timing');
  const spring = jest.spyOn(Animated, 'spring');
  const value = new Animated.Value(0);
  expect(runShippingTiming(value, 1, 0, true)).toBeNull();
  expect(timing).not.toHaveBeenCalled();
  expect(spring).not.toHaveBeenCalled();
  const animation = runShippingTiming(value, 1, desktopMotion.navMs, true);
  expect(animation).not.toBeNull();
  expect(timing).toHaveBeenCalledTimes(1);
  expect(timing.mock.calls[0]?.[1]).toMatchObject({
    duration: 80,
    toValue: 1,
    useNativeDriver: true,
  });
  expect(spring).not.toHaveBeenCalled();
  timing.mockRestore();
  spring.mockRestore();
});

test('list insert and glass stay instant even when motion is allowed', () => {
  expect(listInsertMotionDuration(false)).toBe(0);
  expect(glassMotionDuration(false)).toBe(0);
  expect(motionDuration(desktopMotion.listInsertMs, false)).toBe(0);
  expect(motionDuration(desktopMotion.glassMs, false)).toBe(0);
});
