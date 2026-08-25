import React from 'react';
import {StyleSheet, Text, View} from 'react-native';
import {Button} from './Button';
import {tokens} from './tokens';

export function Onboarding({
  onSignIn,
  signingIn,
}: {
  onSignIn: () => void;
  signingIn: boolean;
}) {
  return (
    <View accessibilityLabel="First-run onboarding" style={styles.surface}>
      <View style={styles.content}>
        <Text accessibilityRole="header" style={styles.title}>
          Welcome to Omi
        </Text>
        <Text style={styles.copy}>
          Sign in to bring your saved conversations and memories into one calm
          workspace.
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
    padding: tokens.space.xxxl,
  },
  content: {
    alignItems: 'center',
    gap: tokens.space.lg,
    maxWidth: tokens.size.content,
    width: '100%',
  },
  title: {
    color: tokens.color.text,
    fontSize: 36,
    fontWeight: '700',
    letterSpacing: -1,
    lineHeight: 42,
    textAlign: 'center',
  },
  copy: {
    color: tokens.color.menuText,
    fontSize: 16,
    lineHeight: 24,
    textAlign: 'center',
  },
  signIn: {marginTop: tokens.space.sm, paddingHorizontal: 28},
});
