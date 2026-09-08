import React, {useEffect, useRef} from 'react';
import {
  Animated,
  Easing,
  Platform,
  ScrollView,
  Linking,
  StyleSheet,
  Text,
  View,
} from 'react-native';
import {useReduceMotion} from '../app/useReduceMotion';
import {desktopTokens} from '../desktop/tokens';
import {Button} from './Button';
import {OmiAvatar} from './OmiAvatar';
import {tokens} from './tokens';

const DOTS_SIZE = 104;

export function Onboarding({
  error,
  onSignIn,
  onCancelSignIn,
  signingIn,
  setupRequired = false,
  completingSetup = false,
  onCompleteSetup,
  onSignOut,
}: {
  error?: string | null;
  onSignIn: () => void;
  onCancelSignIn?: () => void;
  signingIn: boolean;
  setupRequired?: boolean;
  completingSetup?: boolean;
  onCompleteSetup?: (connectDevice: boolean) => void;
  onSignOut?: () => void;
}) {
  const reduceMotion = useReduceMotion();
  const desktop = Platform.OS === 'macos';
  const browser = Platform.OS === 'web';
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
    <ScrollView
      accessibilityLabel="First-run onboarding"
      contentContainerStyle={styles.surface}>
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
            inkColor={desktop ? desktopTokens.color.ink : undefined}
          />
        </Animated.View>
        <Text
          accessibilityRole="header"
          style={[styles.title, desktop && styles.desktopTitle]}>
          {setupRequired ? 'Before you start' : 'Welcome to Omi'}
        </Text>
        <Text style={[styles.copy, desktop && styles.desktopCopy]}>
          {setupRequired
            ? 'Omi saves your conversations, memories, and tasks to your Omi account, and you can read them back on Home. Cloud AI services transcribe audio and use your messages to generate replies.'
            : 'Sign in to access your conversations and memories.'}
        </Text>
        {error == null ? null : (
          <Text
            accessibilityLabel={setupRequired ? 'Setup error' : 'Sign-in error'}
            style={[styles.error, desktop && styles.desktopCopy]}>
            {error}
          </Text>
        )}
        {setupRequired ? (
          <>
            <Text style={[styles.copy, desktop && styles.desktopCopy]}>
              {browser
                ? 'Continue to Omi. Recording from an Omi device requires the native app.'
                : 'Connect an Omi when you are ready to record, or continue with chat. You can connect a device later from Home.'}
            </Text>
            <View style={styles.links}>
              <Button
                variant="ghost"
                accessibilityRole="link"
                onPress={() => {
                  Linking.openURL('https://www.omi.me/pages/privacy').catch(
                    () => undefined,
                  );
                }}>
                Privacy policy
              </Button>
              <Button
                variant="ghost"
                accessibilityRole="link"
                onPress={() => {
                  Linking.openURL(
                    'https://www.omi.me/pages/terms-of-service',
                  ).catch(() => undefined);
                }}>
                Terms of service
              </Button>
            </View>
            {!desktop && !browser && (
              <Button
                accessibilityLabel="Agree and connect Omi"
                disabled={completingSetup}
                onPress={() => onCompleteSetup?.(true)}
                size="large">
                {completingSetup ? 'Saving…' : 'Agree and connect Omi'}
              </Button>
            )}
            <Button
              accessibilityLabel={
                desktop || browser
                  ? 'Agree and continue'
                  : 'Agree and continue without a device'
              }
              disabled={completingSetup}
              onPress={() => onCompleteSetup?.(false)}
              variant={desktop || browser ? 'primary' : 'ghost'}>
              {completingSetup
                ? 'Saving…'
                : desktop || browser
                ? 'Agree and continue'
                : 'Agree and continue without a device'}
            </Button>
            {onSignOut && (
              <Button variant="ghost" onPress={onSignOut}>
                Sign out
              </Button>
            )}
          </>
        ) : (
          <>
            <Button
              accessibilityLabel="Sign in"
              accessibilityRole="button"
              disabled={signingIn}
              onPress={onSignIn}
              size="large"
              labelStyle={desktop && styles.desktopButtonLabel}
              style={[styles.signIn, desktop && styles.desktopButton]}>
              {signingIn ? 'Signing in…' : 'Sign in'}
            </Button>
            {signingIn && onCancelSignIn ? (
              <Button
                accessibilityLabel="Cancel sign in"
                onPress={onCancelSignIn}
                labelStyle={desktop && styles.desktopTitle}
                variant="ghost">
                Cancel
              </Button>
            ) : null}
          </>
        )}
      </View>
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  surface: {
    alignItems: 'center',
    alignSelf: 'stretch',
    flexGrow: 1,
    justifyContent: 'center',
    paddingHorizontal: tokens.space.xxl,
    paddingVertical: tokens.space.xl,
  },
  links: {flexDirection: 'row', flexWrap: 'wrap', justifyContent: 'center'},
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
  error: {
    color: tokens.color.menuText,
    fontSize: 13,
    lineHeight: 18,
    textAlign: 'center',
  },
  signIn: {marginTop: tokens.space.sm, paddingHorizontal: 28},
  desktopTitle: {color: desktopTokens.color.ink},
  desktopCopy: {color: desktopTokens.color.inkMuted},
  desktopButton: {backgroundColor: desktopTokens.color.dark},
  desktopButtonLabel: {color: desktopTokens.color.white},
});
