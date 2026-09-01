import React, {useEffect, useRef} from 'react';
import {
  Animated,
  StyleSheet,
  type PressableProps,
  type StyleProp,
  type ViewStyle,
} from 'react-native';
import {FocusPressable} from '../ui/Pressable';
import {useReduceMotion} from '../app/useReduceMotion';
import {pressMotionDuration, runShippingTiming} from './desktopMotion';

export function ShippingPressable({
  active = false,
  children,
  style,
  ...props
}: Omit<PressableProps, 'children'> & {
  active?: boolean;
  children?: React.ReactNode;
}) {
  const reduceMotion = useReduceMotion();
  const progress = useRef(new Animated.Value(active ? 1 : 0)).current;
  useEffect(() => {
    const animation = runShippingTiming(
      progress,
      active ? 1 : 0,
      pressMotionDuration(reduceMotion),
      false,
    );
    animation?.start();
    return () => {
      animation?.stop();
    };
  }, [active, progress, reduceMotion]);
  return (
    <FocusPressable
      {...props}
      style={state => {
        const resolved =
          typeof style === 'function'
            ? style(state)
            : (style as StyleProp<ViewStyle>);
        return [resolved, state.pressed ? styles.pressed : null];
      }}>
      <Animated.View
        pointerEvents="none"
        style={[
          styles.fill,
          {
            backgroundColor: progress.interpolate({
              inputRange: [0, 1],
              outputRange: ['rgba(0, 0, 0, 0)', 'rgba(0, 0, 0, 0.085)'],
            }),
          },
        ]}
      />
      {children}
    </FocusPressable>
  );
}

const styles = StyleSheet.create({
  fill: {
    borderRadius: 18,
    bottom: 0,
    left: 0,
    position: 'absolute',
    right: 0,
    top: 0,
  },
  pressed: {opacity: 0.78},
});
