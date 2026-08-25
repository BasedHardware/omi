import React from 'react';
import {Text, View} from 'react-native';
import {FocusPressable} from './Pressable';
import {styles} from './styles';

export function HomeRecovery({
  copy,
  onSignIn,
  onRetry,
  signingIn,
  title,
}: {
  copy: string;
  onSignIn?: () => void;
  onRetry: () => void;
  signingIn?: boolean;
  title: string;
}) {
  return (
    <View
      accessibilityLabel="Home saved-data recovery"
      style={styles.macHomeRecovery}>
      <Text accessibilityRole="header" style={styles.macHomeRecoveryTitle}>
        {title}
      </Text>
      <Text style={styles.macHomeRecoveryCopy}>{copy}</Text>
      {onSignIn !== undefined && (
        <FocusPressable
          accessibilityLabel="Sign in"
          accessibilityRole="button"
          disabled={signingIn}
          onPress={onSignIn}
          style={({pressed}) => [
            styles.macHomeRecoverySignIn,
            pressed && styles.pressed,
          ]}>
          <Text style={styles.macHomeRecoverySignInText}>
            {signingIn ? 'Signing in…' : 'Sign in'}
          </Text>
        </FocusPressable>
      )}
      <FocusPressable
        accessibilityLabel="Retry saved data"
        accessibilityRole="button"
        onPress={onRetry}
        style={({pressed}) => [
          styles.macHomeRecoveryRetry,
          pressed && styles.pressed,
        ]}>
        <Text style={styles.macHomeRecoveryRetryText}>Retry</Text>
      </FocusPressable>
    </View>
  );
}
