import React, {useEffect, useRef} from 'react';
import {Animated, Easing, StyleSheet, View} from 'react-native';
import {OmiAvatar} from './OmiAvatar';
import {useReduceMotion} from '../app/useReduceMotion';

const HALO_RING_COUNT = 3;
const HALO_LOOP_MS = 2600;
const HALO_STAGGER_MS = HALO_LOOP_MS / HALO_RING_COUNT;
/** Rings grow to this multiple of the mark size as they fade out. */
const HALO_SPREAD = 2.4;

/**
 * The Omi mark with soft breathing halo rings radiating behind it — the shared
 * loading state for the desktop shell. Reduce-motion renders the resting mark.
 */
export function OmiLoadingMark({
  size = 64,
  inkColor = '#ffffff',
}: {
  size?: number;
  inkColor?: string;
}) {
  const reduceMotion = useReduceMotion();
  const phases = useRef(
    Array.from({length: HALO_RING_COUNT}, () => new Animated.Value(0)),
  ).current;

  useEffect(() => {
    if (reduceMotion) {
      return;
    }
    const animation = Animated.stagger(
      HALO_STAGGER_MS,
      phases.map(phase =>
        Animated.loop(
          Animated.timing(phase, {
            toValue: 1,
            duration: HALO_LOOP_MS,
            easing: Easing.out(Easing.ease),
            useNativeDriver: true,
          }),
        ),
      ),
    );
    animation.start();
    return () => {
      animation.stop();
      phases.forEach(phase => phase.setValue(0));
    };
  }, [phases, reduceMotion]);

  const ringEdge = size * HALO_SPREAD;
  const ringOffset = -(ringEdge - size) / 2;

  return (
    <View
      accessibilityLabel="Loading"
      pointerEvents="none"
      style={styles.stage}>
      {!reduceMotion
        ? phases.map((phase, index) => (
            <Animated.View
              key={index}
              pointerEvents="none"
              style={[
                styles.ring,
                {
                  borderColor: inkColor,
                  borderRadius: ringEdge / 2,
                  height: ringEdge,
                  left: ringOffset,
                  top: ringOffset,
                  width: ringEdge,
                  opacity: phase.interpolate({
                    inputRange: [0, 1],
                    outputRange: [0.3, 0],
                  }),
                  transform: [
                    {
                      scale: phase.interpolate({
                        inputRange: [0, 1],
                        outputRange: [size / ringEdge, 1.05],
                      }),
                    },
                  ],
                },
              ]}
            />
          ))
        : null}
      <OmiAvatar
        animate
        identity="omi"
        inkColor={inkColor}
        size={size}
        tone="ink"
      />
    </View>
  );
}

const styles = StyleSheet.create({
  stage: {
    alignItems: 'center',
    justifyContent: 'center',
  },
  ring: {
    borderWidth: 1.5,
    position: 'absolute',
  },
});
