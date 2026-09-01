import React, {useCallback, useEffect, useRef, useState} from 'react';
import {Animated, StyleSheet, Text, View} from 'react-native';
import {useReduceMotion} from '../app/useReduceMotion';
import {FocusPressable} from '../ui/Pressable';
import {GlassPanel} from '../ui/GlassPanel';
import {chipMotionDuration, runShippingTiming} from './desktopMotion';
import {desktopTokens as token} from './tokens';

type ChipLayout = {height: number; width: number; x: number; y: number};

export function ChipRail<Label extends string>({
  labels,
  onChange,
  value,
}: {
  labels: readonly Label[];
  onChange: (label: Label) => void;
  value: Label;
}) {
  const reduceMotion = useReduceMotion();
  const layouts = useRef(new Map<string, ChipLayout>());
  const left = useRef(new Animated.Value(0)).current;
  const top = useRef(new Animated.Value(0)).current;
  const width = useRef(new Animated.Value(0)).current;
  const height = useRef(new Animated.Value(28)).current;
  const [ready, setReady] = useState(false);

  const moveTo = useCallback(
    (label: string) => {
      const layout = layouts.current.get(label);
      if (layout === undefined) {
        return;
      }
      setReady(true);
      const duration = chipMotionDuration(reduceMotion);
      const animations = [
        runShippingTiming(left, layout.x, duration, false),
        runShippingTiming(top, layout.y, duration, false),
        runShippingTiming(width, layout.width, duration, false),
        runShippingTiming(height, layout.height, duration, false),
      ].filter((item): item is Animated.CompositeAnimation => item !== null);
      if (animations.length === 0) {
        return;
      }
      Animated.parallel(animations).start();
    },
    [height, left, reduceMotion, top, width],
  );

  useEffect(() => {
    moveTo(value);
  }, [moveTo, value]);

  return (
    <View style={styles.rail}>
      <Animated.View
        pointerEvents="none"
        style={[
          styles.pill,
          ready ? styles.pillReady : styles.pillHidden,
          {height, left, top, width},
        ]}>
        <GlassPanel
          glassCornerRadius={token.radius.chip}
          pointerEvents="none"
          style={StyleSheet.absoluteFill}
        />
      </Animated.View>
      {labels.map(label => (
        <FocusPressable
          accessibilityRole="button"
          accessibilityState={{selected: value === label}}
          key={label}
          onLayout={event => {
            layouts.current.set(label, event.nativeEvent.layout);
            if (label === value) {
              moveTo(label);
            }
          }}
          onPress={() => onChange(label)}
          style={styles.chip}>
          <Text
            style={[styles.chipText, value === label && styles.chipTextActive]}>
            {label}
          </Text>
        </FocusPressable>
      ))}
    </View>
  );
}

const styles = StyleSheet.create({
  rail: {flexDirection: 'row', flexWrap: 'wrap', gap: 6},
  pill: {
    borderRadius: token.radius.chip,
    overflow: 'hidden',
    position: 'absolute',
  },
  pillHidden: {opacity: 0},
  pillReady: {opacity: 1},
  chip: {
    alignItems: 'center',
    borderRadius: token.radius.chip,
    flexDirection: 'row',
    gap: 6,
    height: 28,
    paddingHorizontal: 12,
  },
  chipText: {
    color: token.color.inkMuted,
    fontFamily: token.font,
    fontSize: token.type.caption,
    fontWeight: '600',
  },
  chipTextActive: {color: token.color.onGlass},
});
