import React, {useEffect, useMemo, useRef} from 'react';
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

export type OmiMarkMotion = 'arrive' | 'gather' | 'breathe' | 'success';
const motionDuration: Record<OmiMarkMotion, number> = {
  arrive: 900,
  gather: 900,
  breathe: 8000,
  success: 900,
};

/** Adapted from main's omiOrb.ts: canonical ring, 2.2-unit breath and 34-unit
 * success scatter. One-shot gestures return exactly to rest; no pretend meter. */
export function omiMarkMotionPose(
  motion: OmiMarkMotion,
  index: number,
  phase: number,
) {
  const center = omiMarkDotCenter(index);
  const dx = center.x - omiMarkGeometry.centre;
  const dy = center.y - omiMarkGeometry.centre;
  const radius = Math.hypot(dx, dy);
  let spread = 1;
  let scale = 1;
  let opacity = 1;
  if (motion === 'arrive') {
    const t = Math.max(0, Math.min(1, (phase - index * 0.045) / 0.685));
    const placed = 1 - Math.pow(1 - t, 3);
    spread = 0.3 + 0.7 * placed;
    scale = 0.6 + 0.4 * placed;
    opacity = 0.15 + 0.85 * placed;
  } else if (motion === 'gather') {
    const envelope = Math.sin(Math.PI * phase);
    // Inward first, then an overshoot before returning to the ring.
    spread = 1 - 0.6 * Math.sin(2 * Math.PI * phase) * envelope;
    scale = 1 + 0.12 * envelope;
  } else if (motion === 'success') {
    const burst = Math.sin(Math.PI * phase);
    spread = 1 + (34 * burst) / radius;
    scale = 1 + 0.16 * burst;
  } else {
    const breath = 0.5 - 0.5 * Math.cos(2 * Math.PI * (phase + index / 24));
    spread = 1 + (2.2 * breath) / radius;
    scale = 1 + 0.056 * breath;
    opacity = 0.75 + 0.25 * breath;
  }
  return {x: dx * (spread - 1), y: dy * (spread - 1), scale, opacity};
}

function OmiAvatar({
  animate = false,
  identity = 'omi',
  reduceMotion = false,
  size = AVATAR_BASE,
  tone = 'identity',
  inkColor = OMI_MARK_INK,
  motion,
  motionKey,
}: {
  animate?: boolean;
  identity?: string;
  reduceMotion?: boolean;
  size?: number;
  tone?: 'identity' | 'ink';
  inkColor?: string;
  motion?: OmiMarkMotion;
  motionKey?: string;
}) {
  const smileProgress = useRef(new Animated.Value(0)).current;
  const cometPhase = useRef(new Animated.Value(0)).current;
  const gesture = useRef(
    new Animated.Value(motion && !reduceMotion ? 0 : 1),
  ).current;
  const unit = size / AVATAR_BASE;
  const mark = tone === 'ink';
  const poses = useMemo(
    () =>
      motion
        ? Array.from({length: MARK_DOT_COUNT}, (_, index) =>
            MARK_PHASE_SAMPLES.map(phase =>
              omiMarkMotionPose(motion, index, phase),
            ),
          )
        : null,
    [motion],
  );

  useEffect(() => {
    if (!mark || !motion || reduceMotion) {
      gesture.setValue(1);
      return;
    }
    gesture.setValue(0);
    const timing = Animated.timing(gesture, {
      toValue: 1,
      duration: motionDuration[motion],
      easing: Easing.linear,
      useNativeDriver: false,
      isInteraction: false,
    });
    const animation = motion === 'breathe' ? Animated.loop(timing) : timing;
    animation.start();
    return () => animation.stop();
  }, [gesture, mark, motion, motionKey, reduceMotion]);

  useEffect(() => {
    smileProgress.setValue(0);
    cometPhase.setValue(0);
    if (!animate || reduceMotion || (mark && motion)) {
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
  }, [animate, cometPhase, mark, motion, reduceMotion, smileProgress]);

  if (mark) {
    const markScale = size / omiMarkGeometry.canvas;
    const markDiameter = omiMarkGeometry.dotRadius * 2 * markScale;
    const pulsing = animate && !reduceMotion && !motion;
    return (
      <View
        testID="omi-dot-mark"
        accessibilityElementsHidden
        importantForAccessibility="no-hide-descendants"
        style={{height: size, position: 'relative', width: size}}>
        {Array.from({length: MARK_DOT_COUNT}, (_, index) => {
          const center = omiMarkDotCenter(index);
          const path = !reduceMotion ? poses?.[index] : null;
          const value = (key: 'x' | 'y' | 'scale' | 'opacity') =>
            gesture.interpolate({
              inputRange: MARK_PHASE_SAMPLES,
              outputRange: path!.map(
                pose =>
                  pose[key] * (key === 'x' || key === 'y' ? markScale : 1),
              ),
            });
          return (
            <Animated.View
              key={index}
              style={{
                backgroundColor: inkColor,
                borderRadius: markDiameter / 2,
                height: markDiameter,
                left: center.x * markScale - markDiameter / 2,
                opacity: path
                  ? value('opacity')
                  : pulsing
                  ? markDotOpacity(cometPhase, index)
                  : 1,
                position: 'absolute',
                top: center.y * markScale - markDiameter / 2,
                width: markDiameter,
                transform: path
                  ? [
                      {translateX: value('x')},
                      {translateY: value('y')},
                      {scale: value('scale')},
                    ]
                  : undefined,
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
