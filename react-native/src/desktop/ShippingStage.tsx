import React, {useEffect, useRef} from 'react';
import {
  Animated,
  StyleSheet,
  Text,
  View,
  type StyleProp,
  type ViewStyle,
} from 'react-native';
import {useReduceMotion} from '../app/useReduceMotion';
import {desktopStageFade} from './desktopChrome';
import {desktopTokens as token} from './tokens';
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

class ShippingStageGuard extends React.Component<
  {children: React.ReactNode},
  {failed: boolean}
> {
  state = {failed: false};

  static getDerivedStateFromError(): {failed: boolean} {
    return {failed: true};
  }

  render(): React.ReactNode {
    if (this.state.failed) {
      return (
        <View
          accessibilityLabel="Desktop stage unavailable"
          style={styles.stageFallback}>
          <Text style={styles.stageFallbackCopy}>
            This page could not be shown.
          </Text>
        </View>
      );
    }
    return this.props.children;
  }
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
        runShippingTiming(opacity, 1, duration, false),
        runShippingTiming(translateY, 0, duration, false),
      ].filter((item): item is Animated.CompositeAnimation => item !== null),
    );
    animation.start();
    return () => animation.stop();
  }, [opacity, reduceMotion, stageKey, translateY, variant]);
  return (
    <Animated.View
      style={[styles.stage, style, {opacity, transform: [{translateY}]}]}>
      <ShippingStageGuard key={stageKey}>{children}</ShippingStageGuard>
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
  stageFallback: {alignItems: 'center', flex: 1, justifyContent: 'center'},
  stageFallbackCopy: {color: token.color.inkMuted, textAlign: 'center'},
});
