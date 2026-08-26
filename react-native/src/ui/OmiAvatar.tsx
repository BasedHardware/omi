import React, {useEffect, useRef} from 'react';
import {Animated, Easing, View} from 'react-native';
import {styles} from './styles';

const AVATAR_BASE = 40;
const MARK_DOT_COUNT = 8;
const MARK_PHASE_SAMPLES = Array.from({length: 33}, (_, step) => step / 32);

export const OMI_MARK_INK = '#ffffff';

export const omiMarkGeometry = {
  canvas: 260,
  centre: 129.5,
  dotRadius: 17.2,
  axisRadius: 86.71,
  diagonalRadius: 91.92,
  lapMs: 900,
  idleBrightness: 0.5,
  pulseWidth: 0.18,
} as const;

export function omiDotColor(identity: string, index: number): string {
  let hash = 2166136261;
  for (let cursor = 0; cursor < identity.length; cursor += 1) {
    hash ^= identity.charCodeAt(cursor);
    hash = Math.imul(hash, 16777619);
  }
  const hue = (hash + index * 43) >>> 0;
  return `hsl(${hue % 360}, 84%, 66%)`;
}

const omiDotPoses = [
  {ring: {left: 17.5, top: 3.5}, smile: {left: 10, top: 12}},
  {ring: {left: 27.5, top: 7.5}, smile: {left: 26, top: 12}},
  {ring: {left: 31.5, top: 17.5}, smile: {left: 28, top: 23}},
  {ring: {left: 27.5, top: 27.5}, smile: {left: 25, top: 27}},
  {ring: {left: 17.5, top: 31.5}, smile: {left: 21, top: 30}},
  {ring: {left: 7.5, top: 27.5}, smile: {left: 15, top: 30}},
  {ring: {left: 3.5, top: 17.5}, smile: {left: 11, top: 27}},
  {ring: {left: 7.5, top: 7.5}, smile: {left: 8, top: 23}},
] as const;

export function omiMarkDotCenter(index: number): {x: number; y: number} {
  const theta = index * (Math.PI / 4);
  const radius =
    index % 2 === 0
      ? omiMarkGeometry.axisRadius
      : omiMarkGeometry.diagonalRadius;
  return {
    x: omiMarkGeometry.centre + radius * Math.sin(theta),
    y: omiMarkGeometry.centre - radius * Math.cos(theta),
  };
}

export function omiMarkBrightness(index: number, phase: number | null): number {
  if (phase == null) {
    return 1;
  }
  const peak = index / MARK_DOT_COUNT;
  let distance = Math.abs(phase - peak);
  if (distance > 0.5) {
    distance = 1 - distance;
  }
  const bump = Math.max(0, 1 - distance / omiMarkGeometry.pulseWidth);
  return (
    omiMarkGeometry.idleBrightness + (1 - omiMarkGeometry.idleBrightness) * bump
  );
}

function markDotOpacity(phase: Animated.Value, index: number) {
  return phase.interpolate({
    inputRange: MARK_PHASE_SAMPLES,
    outputRange: MARK_PHASE_SAMPLES.map(sample =>
      omiMarkBrightness(index, sample),
    ),
  });
}

function OmiAvatar({
  animate = false,
  identity = 'omi',
  reduceMotion = false,
  size = AVATAR_BASE,
  tone = 'identity',
}: {
  animate?: boolean;
  identity?: string;
  reduceMotion?: boolean;
  size?: number;
  tone?: 'identity' | 'ink';
}) {
  const smileProgress = useRef(new Animated.Value(0)).current;
  const cometPhase = useRef(new Animated.Value(0)).current;
  const unit = size / AVATAR_BASE;
  const mark = tone === 'ink';

  useEffect(() => {
    smileProgress.setValue(0);
    cometPhase.setValue(0);
    if (!animate || reduceMotion) {
      return;
    }
    if (mark) {
      const pulse = Animated.loop(
        Animated.timing(cometPhase, {
          duration: omiMarkGeometry.lapMs,
          easing: Easing.linear,
          toValue: 1,
          useNativeDriver: false,
        }),
      );
      pulse.start();
      return () => pulse.stop();
    }
    const animation = Animated.loop(
      Animated.sequence([
        Animated.timing(smileProgress, {
          duration: 520,
          easing: Easing.out(Easing.cubic),
          toValue: 1,
          useNativeDriver: true,
        }),
        Animated.timing(smileProgress, {
          duration: 900,
          easing: Easing.out(Easing.cubic),
          toValue: 0,
          useNativeDriver: true,
        }),
      ]),
    );
    animation.start();
    return () => animation.stop();
  }, [animate, cometPhase, mark, reduceMotion, smileProgress]);

  if (mark) {
    const markScale = size / omiMarkGeometry.canvas;
    const markDiameter = omiMarkGeometry.dotRadius * 2 * markScale;
    const pulsing = animate && !reduceMotion;
    return (
      <View
        accessibilityElementsHidden
        importantForAccessibility="no-hide-descendants"
        style={{height: size, position: 'relative', width: size}}>
        {Array.from({length: MARK_DOT_COUNT}, (_, index) => {
          const center = omiMarkDotCenter(index);
          return (
            <Animated.View
              key={index}
              style={{
                backgroundColor: OMI_MARK_INK,
                borderRadius: markDiameter / 2,
                height: markDiameter,
                left: center.x * markScale - markDiameter / 2,
                opacity: pulsing ? markDotOpacity(cometPhase, index) : 1,
                position: 'absolute',
                top: center.y * markScale - markDiameter / 2,
                width: markDiameter,
              }}
            />
          );
        })}
      </View>
    );
  }

  return (
    <View
      accessibilityElementsHidden
      importantForAccessibility="no-hide-descendants"
      style={
        size === AVATAR_BASE
          ? styles.chatAvatar
          : [styles.chatAvatar, {height: size, width: size}]
      }>
      {omiDotPoses.map(({ring, smile}, index) => {
        const translateX = smileProgress.interpolate({
          inputRange: [0, 1],
          outputRange: [0, (smile.left - ring.left) * unit],
        });
        const translateY = smileProgress.interpolate({
          inputRange: [0, 1],
          outputRange: [0, (smile.top - ring.top) * unit],
        });
        return (
          <Animated.View
            key={index}
            style={[
              styles.chatAvatarDot,
              size === AVATAR_BASE
                ? null
                : {
                    borderRadius: 3 * unit,
                    height: 5 * unit,
                    width: 5 * unit,
                  },
              {backgroundColor: omiDotColor(identity, index)},
              size === AVATAR_BASE
                ? ring
                : {left: ring.left * unit, top: ring.top * unit},
              {transform: [{translateX}, {translateY}]},
            ]}
          />
        );
      })}
    </View>
  );
}

export {OmiAvatar};
