import React, {useEffect, useRef} from 'react';
import {Animated, Easing, StyleSheet, Text, View} from 'react-native';
import {useReduceMotion} from '../app/useReduceMotion';
import {Button} from './Button';
import {OmiAvatar} from './OmiAvatar';
import {tokens} from './tokens';

const DOTS_SIZE = 104;

export function Onboarding({
  onSignIn,
  signingIn,
}: {
  onSignIn: () => void;
  signingIn: boolean;
}) {
  const reduceMotion = useReduceMotion();
  const opacity = useRef(new Animated.Value(1)).current;
  const scale = useRef(new Animated.Value(1)).current;

  useEffect(() => {
    if (reduceMotion) {
      opacity.setValue(1);
      scale.setValue(1);
      return;
    }

    // Stay visible if the JS driver does not tick on first Fabric paint.
    opacity.setValue(0.88);
    scale.setValue(0.94);
    // JS driver: native driver can leave first-paint opacity at 0 on Fabric.
    const intro = Animated.parallel([
      Animated.timing(opacity, {
        duration: 480,
        easing: Easing.out(Easing.cubic),
        toValue: 1,
        useNativeDriver: false,
      }),
      Animated.timing(scale, {
        duration: 480,
        easing: Easing.out(Easing.cubic),
        toValue: 1,
        useNativeDriver: false,
      }),
    ]);
    intro.start();
    return () => intro.stop();
  }, [opacity, reduceMotion, scale]);

  return (
    <View accessibilityLabel="First-run onboarding" style={styles.surface}>
      <View style={styles.column}>
        <Animated.View
          accessibilityLabel="Omi"
          style={[styles.dots, {opacity, transform: [{scale}]}]}>
          <OmiAvatar
            animate={!reduceMotion}
            identity="omi"
            reduceMotion={reduceMotion}
            size={DOTS_SIZE}
            tone="ink"
          />
        </Animated.View>
        <Text accessibilityRole="header" style={styles.title}>
          Welcome to Omi
        </Text>
        <Text style={styles.copy}>
          Sign in to access your conversations and memories.
        </Text>
        <Button
          accessibilityLabel="Sign in"
          accessibilityRole="button"
          disabled={signingIn}
          onPress={onSignIn}
          size="large"
          style={styles.signIn}>
          {signingIn ? 'Signing in…' : 'Sign in'}
        </Button>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  surface: {
    alignItems: 'center',
    alignSelf: 'stretch',
    flex: 1,
    justifyContent: 'center',
    paddingHorizontal: tokens.space.xxl,
    paddingVertical: tokens.space.xl,
  },
  column: {
    alignItems: 'center',
    gap: tokens.space.sm,
    maxWidth: tokens.size.content,
    width: '100%',
  },
  dots: {
    marginBottom: tokens.space.none,
  },
  title: {
    color: tokens.color.text,
    fontSize: 32,
    fontWeight: '700',
    letterSpacing: -1,
    lineHeight: 38,
    textAlign: 'center',
  },
  copy: {
    color: tokens.color.menuText,
    fontSize: 15,
    lineHeight: 22,
    textAlign: 'center',
  },
  signIn: {marginTop: tokens.space.sm, paddingHorizontal: 28},
});
