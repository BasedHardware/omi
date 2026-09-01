import React, {useEffect, useRef} from 'react';
import {
  Animated,
  StyleSheet,
  View,
  type StyleProp,
  type ViewStyle,
} from 'react-native';
import {useReduceMotion} from '../app/useReduceMotion';
import {desktopStageFade} from './desktopChrome';
import {
  glassMotionDuration,
  listInsertMotionDuration,
  navMotionDuration,
  runShippingTiming,
  searchExpandMotionDuration,
  stepMotionDuration,
} from './desktopMotion';

export type ShippingStageVariant = 'page' | 'hub' | 'search';

function stageOffset(variant: ShippingStageVariant): number {
  if (variant === 'search') {
    return desktopStageFade.chatRiseY;
  }
  if (variant === 'hub') {
    return desktopStageFade.hubOffsetY;
  }
  return 0;
}

function stageDuration(
  variant: ShippingStageVariant,
  reduceMotion: boolean,
): number {
  return variant === 'page'
    ? navMotionDuration(reduceMotion)
    : stepMotionDuration(reduceMotion);
}

export function ShippingStage({
  children,
  stageKey,
  style,
  variant = 'page',
}: {
  children: React.ReactNode;
  stageKey: string;
  style?: StyleProp<ViewStyle>;
  variant?: ShippingStageVariant;
}) {
  const reduceMotion = useReduceMotion();
  const opacity = useRef(new Animated.Value(1)).current;
  const translateY = useRef(new Animated.Value(0)).current;
  const mounted = useRef(false);
  useEffect(() => {
    if (!mounted.current) {
      mounted.current = true;
      return undefined;
    }
    const duration = stageDuration(variant, reduceMotion);
    const fromY = stageOffset(variant);
    if (duration === 0) {
      opacity.setValue(1);
      translateY.setValue(0);
      return undefined;
    }
    opacity.setValue(0);
    translateY.setValue(fromY);
    const animation = Animated.parallel(
      [
        runShippingTiming(opacity, 1, duration, true),
        runShippingTiming(translateY, 0, duration, true),
      ].filter((item): item is Animated.CompositeAnimation => item !== null),
    );
    animation.start();
    return () => animation.stop();
  }, [opacity, reduceMotion, stageKey, translateY, variant]);
  return (
    <Animated.View
      style={[styles.stage, style, {opacity, transform: [{translateY}]}]}>
      {children}
    </Animated.View>
  );
}

export function ShippingSearchFocus({
  children,
  expanded,
  radius = 22,
  style,
}: {
  children: React.ReactNode;
  expanded: boolean;
  radius?: number;
  style?: StyleProp<ViewStyle>;
}) {
  const reduceMotion = useReduceMotion();
  const progress = useRef(new Animated.Value(expanded ? 1 : 0)).current;
  useEffect(() => {
    const animation = runShippingTiming(
      progress,
      expanded ? 1 : 0,
      searchExpandMotionDuration(reduceMotion),
      false,
    );
    animation?.start();
    return () => {
      animation?.stop();
    };
  }, [expanded, progress, reduceMotion]);
  return (
    <View style={style}>
      {children}
      <Animated.View
        pointerEvents="none"
        style={[
          styles.searchRing,
          {
            borderColor: progress.interpolate({
              inputRange: [0, 1],
              outputRange: ['rgba(0, 0, 0, 0)', 'rgba(0, 0, 0, 0.28)'],
            }),
            borderRadius: radius,
          },
        ]}
      />
    </View>
  );
}

export function ShippingListInsert({
  children,
  itemKey,
}: {
  children: React.ReactNode;
  itemKey: string;
}) {
  const reduceMotion = useReduceMotion();
  const opacity = useRef(new Animated.Value(1)).current;
  const seen = useRef(false);
  useEffect(() => {
    if (seen.current) {
      return undefined;
    }
    seen.current = true;
    const duration = listInsertMotionDuration(reduceMotion);
    if (duration === 0) {
      opacity.setValue(1);
      return undefined;
    }
    opacity.setValue(0);
    const animation = runShippingTiming(opacity, 1, duration, true);
    animation?.start();
    return () => {
      animation?.stop();
    };
  }, [itemKey, opacity, reduceMotion]);
  return <Animated.View style={{opacity}}>{children}</Animated.View>;
}

export function ShippingGlassMount({
  children,
  style,
}: {
  children: React.ReactNode;
  style?: StyleProp<ViewStyle>;
}) {
  const reduceMotion = useReduceMotion();
  const opacity = useRef(new Animated.Value(1)).current;
  useEffect(() => {
    const duration = glassMotionDuration(reduceMotion);
    if (duration === 0) {
      opacity.setValue(1);
      return undefined;
    }
    opacity.setValue(0);
    const animation = runShippingTiming(opacity, 1, duration, true);
    animation?.start();
    return () => {
      animation?.stop();
    };
  }, [opacity, reduceMotion]);
  return <Animated.View style={[style, {opacity}]}>{children}</Animated.View>;
}

const styles = StyleSheet.create({
  searchRing: {
    borderRadius: 22,
    borderWidth: 1,
    bottom: 0,
    left: 0,
    position: 'absolute',
    right: 0,
    top: 0,
  },
  stage: {flex: 1},
});
