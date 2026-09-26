import React, {useCallback, useEffect, useRef} from 'react';
import {Animated, Easing, StyleSheet, Text, View} from 'react-native';
import {FocusPressable} from '../ui/Pressable';
import {type DesktopTokens, useDesktopStyleSheets} from './DesktopTheme';

const CONFETTI_COLORS = ['#38e0c0', '#7aa2ff', '#ffd166', '#ff8fa3', '#ffffff'];

type ConfettiPiece = {
  color: string;
  drift: number;
  duration: number;
  height: number;
  rotation: number;
  spread: number;
  width: number;
};

// One confetti burst: paper pieces launch upward from behind the button, arc
// with a little drift and spin, and fade before they leave the frame. Runs on
// the Continue press, right before the overlay closes.
function makeConfetti(count: number): ConfettiPiece[] {
  return Array.from({length: count}, (_, index) => ({
    color: CONFETTI_COLORS[index % CONFETTI_COLORS.length],
    drift: (Math.random() - 0.5) * 320,
    duration: 900 + Math.random() * 700,
    height: 6 + Math.random() * 6,
    rotation: (Math.random() - 0.5) * 1440,
    spread: (Math.random() - 0.5) * 260,
    width: 4 + Math.random() * 4,
  }));
}

function ConfettiBurst({pieces}: {pieces: ConfettiPiece[]}) {
  const progress = useRef(new Animated.Value(0)).current;
  useEffect(() => {
    const animation = Animated.timing(progress, {
      duration: 1900,
      easing: Easing.out(Easing.quad),
      toValue: 1,
      useNativeDriver: true,
      isInteraction: false,
    });
    animation.start();
    return () => animation.stop();
  }, [progress]);
  return (
    <View pointerEvents="none" style={StyleSheet.absoluteFillObject}>
      {pieces.map((piece, index) => {
        const rise = piece.duration / 1700;
        return (
          <Animated.View
            key={index}
            style={{
              backgroundColor: piece.color,
              borderRadius: 1.5,
              height: piece.height,
              left: '50%',
              marginLeft: piece.spread / 2 - piece.width / 2,
              opacity: progress.interpolate({
                inputRange: [0, 0.6, 0.85, 1],
                outputRange: [1, 1, 0.9, 0],
              }),
              position: 'absolute',
              top: '62%',
              transform: [
                {
                  translateX: progress.interpolate({
                    inputRange: [0, 1],
                    outputRange: [0, piece.drift],
                  }),
                },
                {
                  translateY: progress.interpolate({
                    inputRange: [0, rise, 1],
                    outputRange: [0, -140 - piece.duration / 14, 320],
                  }),
                },
                {
                  rotate: progress.interpolate({
                    inputRange: [0, 1],
                    outputRange: ['0deg', `${piece.rotation}deg`],
                  }),
                },
                {scale: 0.9},
              ],
              width: piece.width,
            }}
          />
        );
      })}
    </View>
  );
}

/**
 * Confetti that outlives the post-setup overlay. Rendered by DesktopApp at
 * the top of the tree, so pieces keep falling over the app UI after the
 * overlay has faded away, then unmounts itself.
 */
export function PostSetupConfetti({onDone}: {onDone: () => void}) {
  const pieces = useRef(makeConfetti(84)).current;
  useEffect(() => {
    const timer = setTimeout(onDone, 2000);
    return () => clearTimeout(timer);
  }, [onDone]);
  return <ConfettiBurst pieces={pieces} />;
}

/**
 * One-shot post-setup confirmation. A dark, light-text overlay — deliberately
 * not a card modal. Continue starts the confetti in the parent, fades the
 * overlay out, then closes.
 */
export function PostSetupOverlay({
  onContinue,
  onClose,
}: {
  onContinue: () => void;
  onClose: () => void;
}) {
  const styles = useDesktopStyleSheets(createStyles);
  const entrance = useRef(new Animated.Value(0)).current;
  const leaving = useRef(false);

  useEffect(() => {
    const reveal = Animated.timing(entrance, {
      duration: 420,
      easing: Easing.out(Easing.cubic),
      toValue: 1,
      useNativeDriver: false,
      isInteraction: false,
    });
    reveal.start();
    return () => reveal.stop();
  }, [entrance]);

  const continuePress = useCallback(() => {
    if (leaving.current) {
      return;
    }
    leaving.current = true;
    onContinue();
    const exit = Animated.timing(entrance, {
      duration: 460,
      easing: Easing.in(Easing.quad),
      toValue: 0,
      useNativeDriver: false,
      isInteraction: false,
    });
    exit.start(({finished}) => {
      if (finished) {
        onClose();
      }
    });
  }, [entrance, onClose, onContinue]);

  return (
    <Animated.View
      accessibilityLabel="Home prove-it"
      style={[styles.overlay, {opacity: entrance}]}>
      <View style={styles.content}>
        <Text style={styles.title}>You&apos;re set.</Text>
        <Text style={styles.body}>
          Home can read conversations, memories, and tasks from your account.
        </Text>
        <FocusPressable
          accessibilityLabel="Continue"
          accessibilityRole="button"
          onPress={continuePress}
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

const createStyles = (token: DesktopTokens) =>
  StyleSheet.create({
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
