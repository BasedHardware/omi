import React, {useCallback, useEffect, useRef} from 'react';
import {Animated, Easing, StyleSheet, Text, View} from 'react-native';
import {FocusPressable} from '../ui/Pressable';
import {useReduceMotion} from '../app/useReduceMotion';
import {type DesktopTokens, useDesktopStyleSheets} from './DesktopTheme';

const CONFETTI_COLORS = ['#38e0c0', '#7aa2ff', '#ffd166', '#ff8fa3', '#ffffff'];

type ConfettiPiece = {
  color: string;
  /** Seconds the piece stays in flight. */
  duration: number;
  height: number;
  /** Absolute px offsets from the piece origin, sampled over flight. */
  path: {x: number; y: number}[];
  rotation: number;
  wobblePhase: number;
  wobbleWidth: number;
  width: number;
};

// Trajectory sampling density for the Animated interpolations.
const PATH_SAMPLES = 30;

/**
 * canvas-confetti's own integration model, run at its 60fps timestep: each
 * frame the velocity is multiplied by `decay` (0.9 default), `gravity`
 * (0.1 default, +y) is added, then the position advances by the velocity.
 * startVelocity (45 default) is in px-per-frame, which is why the library's
 * bursts read as a fast pop that decays into a gentle drift — the exact feel
 * this component ports, since the DOM-only library itself cannot run here.
 */
const CONFETTI_FPS = 60;

function sampleCanvasConfettiPath(
  origin: {vx: number; vy: number},
  gravityPerFrame: number,
  decayPerFrame: number,
): {path: {x: number; y: number}[]; duration: number} {
  const state = {vx: origin.vx, vy: origin.vy, x: 0, y: 0};
  const path = [{x: 0, y: 0}];
  // The library removes a particle once it falls past the canvas edge below
  // its bottom-corner origin; ~80px past the start is that moment here.
  let frames = 0;
  while (frames < CONFETTI_FPS * 4 && (frames < 12 || state.y < 80)) {
    state.vx *= decayPerFrame;
    state.vy = state.vy * decayPerFrame + gravityPerFrame;
    state.x += state.vx;
    state.y += state.vy;
    frames += 1;
    path.push({x: state.x, y: state.y});
  }
  return {path, duration: frames / CONFETTI_FPS};
}

/** One cannon of the library's "school pride" preset, parameterized. */
function cannonPiece(
  angleDegrees: number,
  spreadDegrees: number,
): ConfettiPiece {
  // confetti({ particleCount: 60, angle, spread, origin: bottom corner })
  // randomizes the launch angle inside the spread and the speed around
  // startVelocity; gravity 0.1 and decay 0.9 are the library defaults.
  const angle =
    ((angleDegrees + (Math.random() - 0.5) * spreadDegrees) * Math.PI) / 180;
  const speedPerFrame = 45 * (0.75 + Math.random() * 0.5);
  const {path, duration} = sampleCanvasConfettiPath(
    {
      vx: Math.cos(angle) * speedPerFrame,
      vy: -Math.sin(angle) * speedPerFrame,
    },
    0.1,
    0.9,
  );
  return {
    color: CONFETTI_COLORS[Math.floor(Math.random() * CONFETTI_COLORS.length)],
    duration,
    height: 8 + Math.random() * 5,
    path,
    rotation: (Math.random() - 0.5) * 1080,
    wobblePhase: Math.random() * Math.PI * 2,
    wobbleWidth: 14 + Math.random() * 18,
    width: 5 + Math.random() * 3,
  };
}

const PROGRESS_SAMPLES = Array.from(
  {length: PATH_SAMPLES},
  (_, index) => index / (PATH_SAMPLES - 1),
);

function ConfettiPieceView({
  left,
  piece,
  top,
}: {
  left: number | `${number}%`;
  piece: ConfettiPiece;
  top: number | `${number}%`;
}) {
  const progress = useRef(new Animated.Value(0)).current;
  useEffect(() => {
    const animation = Animated.timing(progress, {
      duration: piece.duration * 1000,
      easing: t => t,
      toValue: 1,
      useNativeDriver: true,
      isInteraction: false,
    });
    animation.start();
    return () => animation.stop();
  }, [progress, piece.duration]);
  const xs = piece.path.map(point => point.x);
  const ys = piece.path.map(point => point.y);
  // Paper flip: the piece rotates about its long axis, so its projected
  // height oscillates — the effect that makes canvas confetti read as paper.
  const flips = PROGRESS_SAMPLES.map(
    sample =>
      0.25 +
      0.75 * Math.abs(Math.sin(Math.PI * 3 * sample + piece.wobblePhase)),
  );
  const wobble = PROGRESS_SAMPLES.map(
    sample => Math.sin(Math.PI * 4 * sample + piece.wobblePhase) * 6,
  );
  const opacity = progress.interpolate({
    inputRange: [0, 0.72, 1],
    outputRange: [1, 1, 0],
  });
  return (
    <Animated.View
      pointerEvents="none"
      style={{
        backgroundColor: piece.color,
        borderRadius: 1.5,
        height: piece.height,
        left,
        opacity,
        position: 'absolute',
        top,
        transform: [
          {
            translateX: progress.interpolate({
              inputRange: PROGRESS_SAMPLES,
              outputRange: xs.map((x, index) => x + wobble[index]),
            }),
          },
          {
            translateY: progress.interpolate({
              inputRange: PROGRESS_SAMPLES,
              outputRange: ys,
            }),
          },
          {
            rotate: progress.interpolate({
              inputRange: [0, 1],
              outputRange: ['0deg', `${piece.rotation}deg`],
            }),
          },
          {
            scaleY: progress.interpolate({
              inputRange: PROGRESS_SAMPLES,
              outputRange: flips,
            }),
          },
        ],
        width: piece.width,
      }}
    />
  );
}

/**
 * Confetti that outlives the post-setup overlay: the two bottom-corner
 * cannons of canvas-confetti's "school pride" preset. Renders nothing under
 * reduce motion.
 */
export function PostSetupConfetti({onDone}: {onDone: () => void}) {
  const reduceMotion = useReduceMotion();
  const pieces = useRef(
    [] as (ConfettiPiece & {left: `${number}%`; top: `${number}%`})[],
  ).current;
  if (pieces.length === 0) {
    // school pride: 60 particles, angle 60 and 120, spread 60, from the
    // bottom corners.
    for (let index = 0; index < 60; index += 1) {
      pieces.push({...cannonPiece(60, 60), left: '2%', top: '96%'});
    }
    for (let index = 0; index < 60; index += 1) {
      pieces.push({...cannonPiece(120, 60), left: '98%', top: '96%'});
    }
  }
  const longestFlight = pieces.reduce(
    (longest, piece) => Math.max(longest, piece.duration),
    0,
  );
  useEffect(() => {
    const timer = setTimeout(
      onDone,
      reduceMotion ? 200 : Math.ceil((longestFlight + 0.3) * 1000),
    );
    return () => clearTimeout(timer);
  }, [longestFlight, onDone, reduceMotion]);
  if (reduceMotion) {
    return null;
  }
  return (
    <View pointerEvents="none" style={StyleSheet.absoluteFillObject}>
      {pieces.map((piece, index) => (
        <ConfettiPieceView
          key={index}
          left={piece.left}
          piece={piece}
          top={piece.top}
        />
      ))}
    </View>
  );
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
