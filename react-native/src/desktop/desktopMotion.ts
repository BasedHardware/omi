import {Animated, Easing} from 'react-native';
import {desktopMotion} from './desktopChrome';

export function desktopEaseOut() {
  return Easing.out(Easing.cubic);
}

export function desktopEaseInOut() {
  return Easing.inOut(Easing.cubic);
}

export function motionDuration(ms: number, reduceMotion: boolean): number {
  return reduceMotion ? 0 : ms;
}

export function navMotionDuration(reduceMotion: boolean): number {
  return motionDuration(desktopMotion.navMs, reduceMotion);
}

export function pressMotionDuration(reduceMotion: boolean): number {
  return motionDuration(desktopMotion.pressMs, reduceMotion);
}

export function stepMotionDuration(reduceMotion: boolean): number {
  return motionDuration(desktopMotion.stepMs, reduceMotion);
}

export function overlayMotionDuration(reduceMotion: boolean): number {
  return motionDuration(desktopMotion.overlayMs, reduceMotion);
}

export function searchExpandMotionDuration(reduceMotion: boolean): number {
  return motionDuration(desktopMotion.searchExpandMs, reduceMotion);
}

export function chipMotionDuration(reduceMotion: boolean): number {
  return motionDuration(desktopMotion.chipMs, reduceMotion);
}

export function listInsertMotionDuration(reduceMotion: boolean): number {
  return motionDuration(desktopMotion.listInsertMs, reduceMotion);
}

export function glassMotionDuration(reduceMotion: boolean): number {
  return motionDuration(desktopMotion.glassMs, reduceMotion);
}

export function runShippingTiming(
  value: Animated.Value,
  toValue: number,
  duration: number,
  useNativeDriver: boolean,
): Animated.CompositeAnimation | null {
  if (duration === 0) {
    value.setValue(toValue);
    return null;
  }
  return Animated.timing(value, {
    duration,
    easing: desktopEaseOut(),
    toValue,
    useNativeDriver,
  });
}
