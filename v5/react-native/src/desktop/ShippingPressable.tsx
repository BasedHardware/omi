import React, {useEffect, useRef, useState} from 'react';
import {
  Animated,
  StyleSheet,
  type PressableProps,
  type StyleProp,
  type ViewStyle,
} from 'react-native';
import {FocusPressable, type PressableStyleProp} from '../ui/Pressable';
import {useReduceMotion} from '../app/useReduceMotion';
import {pressMotionDuration, runShippingTiming} from './desktopMotion';
import {useDesktopTheme} from './DesktopTheme';

const AnimatedPressable = Animated.createAnimatedComponent(FocusPressable);

export function ShippingPressable({
  active = false,
  children,
  style,
  onPressIn,
  onPressOut,
  onHoverIn,
  onHoverOut,
  ...props
}: Omit<PressableProps, 'children' | 'style'> & {
  active?: boolean;
  children?: React.ReactNode;
  style?: PressableStyleProp;
}) {
  const reduceMotion = useReduceMotion();
  const {name: themeName} = useDesktopTheme();
  const [pressed, setPressed] = useState(false);
  const [hovered, setHovered] = useState(false);
  const disabled =
    props.disabled ??
    props['aria-disabled'] ??
    props.accessibilityState?.disabled;
  const press = useRef(new Animated.Value(0)).current;
  const progress = useRef(new Animated.Value(active ? 1 : 0)).current;
  useEffect(() => {
    if (disabled) {
      setPressed(false);
    }
    const animation = runShippingTiming(
      press,
      pressed && !disabled ? 1 : 0,
      reduceMotion ? 0 : 120,
      true,
    );
    animation?.start();
    return () => animation?.stop();
  }, [disabled, press, pressed, reduceMotion]);
  useEffect(() => {
    const animation = runShippingTiming(
      progress,
      active ? 1 : hovered && !disabled ? 0.5 : 0,
      pressMotionDuration(reduceMotion),
      false,
    );
    animation?.start();
    return () => {
      animation?.stop();
    };
  }, [active, disabled, hovered, progress, reduceMotion]);
  const resolved =
    typeof style === 'function'
      ? style({
          pressed: pressed && !disabled,
          hovered: hovered && !disabled,
        })
      : (style as StyleProp<ViewStyle>);
  const flattened = StyleSheet.flatten(resolved);
  const existingTransform = flattened?.transform;
  return (
    <AnimatedPressable
      {...props}
      onPressIn={event => {
        if (!disabled) {
          setPressed(true);
        }
        onPressIn?.(event);
      }}
      onPressOut={event => {
        setPressed(false);
        onPressOut?.(event);
      }}
      onHoverIn={event => {
        setHovered(true);
        onHoverIn?.(event);
      }}
      onHoverOut={event => {
        setHovered(false);
        onHoverOut?.(event);
      }}
      style={[
        resolved,
        {
          opacity: Animated.multiply(
            flattened?.opacity ?? 1,
            press.interpolate({inputRange: [0, 1], outputRange: [1, 0.92]}),
          ),
          transform:
            reduceMotion || typeof existingTransform === 'string'
              ? existingTransform
              : [
                  ...(existingTransform ?? []),
                  {
                    scale: press.interpolate({
                      inputRange: [0, 1],
                      outputRange: [1, 0.985],
                    }),
                  },
                ],
        },
      ]}>
      <Animated.View
        pointerEvents="none"
        style={[
          styles.fill,
          {
            backgroundColor: progress.interpolate({
              inputRange: [0, 1],
              // Dark glass needs a light wash to read as hover; the light
              // theme keeps the classic dark scrim.
              outputRange:
                themeName === 'light'
                  ? ['rgba(0, 0, 0, 0)', 'rgba(0, 0, 0, 0.12)']
                  : ['rgba(255, 255, 255, 0)', 'rgba(255, 255, 255, 0.20)'],
            }),
          },
        ]}
      />
      {children}
    </AnimatedPressable>
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
});
