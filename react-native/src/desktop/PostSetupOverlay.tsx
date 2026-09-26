import React, {useEffect, useRef} from 'react';
import {Animated, Easing, StyleSheet, Text, View} from 'react-native';
import {FocusPressable} from '../ui/Pressable';
import {desktopTokens as token} from './tokens';

type AuraBlob = {
  color: string;
  diameter: number;
  left: number;
  top: number;
  drift: {x: number; y: number};
  breath: number;
  duration: number;
  delay: number;
};

// Ambient aura behind the confirmation: three slow, out-of-phase glow blobs.
// Nothing bounces or spins — a calm halo, not a slot machine.
const AURA_BLOBS: AuraBlob[] = [
  {
    color: 'rgba(56, 224, 192, 0.20)',
    diameter: 340,
    left: -60,
    top: -40,
    drift: {x: 26, y: 18},
    breath: 0.16,
    duration: 7000,
    delay: 0,
  },
  {
    color: 'rgba(122, 162, 255, 0.16)',
    diameter: 300,
    left: 520,
    top: 120,
    drift: {x: -22, y: 26},
    breath: 0.12,
    duration: 9500,
    delay: 600,
  },
  {
    color: 'rgba(255, 209, 102, 0.12)',
    diameter: 260,
    left: 210,
    top: 430,
    drift: {x: 18, y: -20},
    breath: 0.14,
    duration: 11500,
    delay: 1200,
  },
];

function AuraBlobView({blob, phase}: {blob: AuraBlob; phase: Animated.Value}) {
  const progress = phase.interpolate({
    inputRange: [0, 0.5, 1],
    outputRange: [0, 1, 0],
  });
  return (
    <Animated.View
      pointerEvents="none"
      style={{
        backgroundColor: blob.color,
        borderRadius: blob.diameter / 2,
        height: blob.diameter,
        left: blob.left,
        position: 'absolute',
        top: blob.top,
        width: blob.diameter,
        opacity: progress.interpolate({
          inputRange: [0, 1],
          outputRange: [0.55, 1],
        }),
        transform: [
          {
            translateX: progress.interpolate({
              inputRange: [0, 1],
              outputRange: [0, blob.drift.x],
            }),
          },
          {
            translateY: progress.interpolate({
              inputRange: [0, 1],
              outputRange: [0, blob.drift.y],
            }),
          },
          {
            scale: progress.interpolate({
              inputRange: [0, 1],
              outputRange: [1, 1 + blob.breath],
            }),
          },
        ],
      }}
    />
  );
}

/**
 * One-shot post-setup confirmation. A dark, light-text overlay with a slow
 * ambient aura — deliberately not a card modal. Closes on the button under
 * the copy.
 */
export function PostSetupOverlay({onClose}: {onClose: () => void}) {
  const phase = useRef(new Animated.Value(0)).current;
  const entrance = useRef(new Animated.Value(0)).current;

  useEffect(() => {
    const aura = Animated.loop(
      Animated.timing(phase, {
        duration: 12000,
        easing: Easing.inOut(Easing.sin),
        toValue: 1,
        useNativeDriver: false,
        isInteraction: false,
      }),
    );
    aura.start();
    const reveal = Animated.timing(entrance, {
      duration: 420,
      easing: Easing.out(Easing.cubic),
      toValue: 1,
      useNativeDriver: false,
      isInteraction: false,
    });
    reveal.start();
    return () => {
      aura.stop();
      reveal.stop();
    };
  }, [entrance, phase]);

  return (
    <Animated.View
      accessibilityLabel="Home prove-it"
      style={[styles.overlay, {opacity: entrance}]}>
      <View pointerEvents="none" style={StyleSheet.absoluteFill}>
        {AURA_BLOBS.map((blob, index) => (
          <AuraBlobView blob={blob} key={index} phase={phase} />
        ))}
      </View>
      <View style={styles.content}>
        <Text style={styles.title}>You&apos;re set.</Text>
        <Text style={styles.body}>
          Home can read conversations, memories, and tasks from your account.
        </Text>
        <FocusPressable
          accessibilityLabel="Continue"
          accessibilityRole="button"
          onPress={onClose}
          style={({pressed}) => [
            styles.button,
            pressed && styles.buttonPressed,
          ]}>
          <Text style={styles.buttonText}>Continue</Text>
        </FocusPressable>
      </View>
    </Animated.View>
  );
}

const styles = StyleSheet.create({
  overlay: {
    ...StyleSheet.absoluteFillObject,
    alignItems: 'center',
    backgroundColor: 'rgba(14, 16, 12, 0.9)',
    justifyContent: 'center',
    overflow: 'hidden',
  },
  content: {
    alignItems: 'center',
    gap: token.space.lg,
    maxWidth: 440,
    paddingHorizontal: token.space.xl,
  },
  title: {
    color: '#ffffff',
    fontFamily: token.font,
    fontSize: 30,
    fontWeight: '700',
    letterSpacing: -0.4,
    textAlign: 'center',
  },
  body: {
    color: 'rgba(255, 255, 255, 0.78)',
    fontFamily: token.font,
    fontSize: 15,
    lineHeight: 22,
    textAlign: 'center',
  },
  button: {
    borderColor: 'rgba(255, 255, 255, 0.28)',
    borderRadius: 999,
    borderWidth: 1,
    backgroundColor: 'rgba(255, 255, 255, 0.08)',
    marginTop: token.space.sm,
    paddingHorizontal: 26,
    paddingVertical: 10,
  },
  buttonPressed: {
    backgroundColor: 'rgba(255, 255, 255, 0.18)',
  },
  buttonText: {
    color: '#ffffff',
    fontFamily: token.font,
    fontSize: token.type.body,
    fontWeight: '600',
  },
});
