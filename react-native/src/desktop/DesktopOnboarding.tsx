import React, {useEffect, useRef, useState} from 'react';
import {Linking, ScrollView, StyleSheet, Text, View} from 'react-native';
import {
  loadPermissionStatus,
  requestDesktopPermission,
  type PermissionKind,
  type PermissionState,
} from '../desktopSettingsClient';
import {Button} from '../ui/Button';
import {OmiAvatar} from '../ui/OmiAvatar';
import type {Onboarding} from '../ui/Onboarding';
import {desktopTokens as token} from './tokens';

type Step =
  | 'welcome'
  | 'value'
  | 'signIn'
  | 'permissions'
  | 'tutorial'
  | 'finish';
type Props = React.ComponentProps<typeof Onboarding>;
const permissions: {kind: PermissionKind; title: string; copy: string}[] = [
  {
    kind: 'screen',
    title: 'Screen recording',
    copy: 'For Recall when you explicitly start capture. A restart may be needed after granting access.',
  },
  {
    kind: 'microphone',
    title: 'Microphone',
    copy: 'Allow microphone access when you want to use an audio feature.',
  },
  {
    kind: 'notifications',
    title: 'Notifications',
    copy: 'Allow Omi to show notifications.',
  },
];
const permissionCopy: Record<PermissionState, string> = {
  unknown: 'Not confirmed',
  granted: 'Allowed',
  denied: 'Not allowed',
};

export function DesktopOnboarding({
  error,
  onSignIn,
  onCancelSignIn,
  signingIn,
  setupRequired = false,
  completingSetup = false,
  onCompleteSetup,
  onSignOut,
}: Props) {
  const [step, setStep] = useState<Step>('welcome');
  const [statuses, setStatuses] = useState<
    Record<PermissionKind, PermissionState>
  >({screen: 'unknown', microphone: 'unknown', notifications: 'unknown'});
  const [pending, setPending] = useState<PermissionKind | null>(null);
  const [localError, setLocalError] = useState<string | null>(null);
  const operation = useRef(0);
  const signedIn = useRef(setupRequired);
  useEffect(() => {
    if (signedIn.current && !setupRequired) {
      operation.current++;
      setStep('welcome');
      setPending(null);
      setLocalError(null);
      setStatuses({
        screen: 'unknown',
        microphone: 'unknown',
        notifications: 'unknown',
      });
    } else if (setupRequired && step === 'signIn') {
      setStep('permissions');
    }
    signedIn.current = setupRequired;
  }, [setupRequired, step]);
  useEffect(() => {
    const lifetime = operation;
    const current = ++lifetime.current;
    setPending(null);
    setLocalError(null);
    if (step === 'permissions' && setupRequired) {
      loadPermissionStatus()
        .then(value => {
          if (operation.current === current) {
            setStatuses(value);
          }
        })
        .catch(() => {
          if (operation.current === current) {
            setLocalError(
              'Could not check permissions. You can continue and manage them in Settings.',
            );
          }
        });
    }
    return () => {
      lifetime.current++;
    };
  }, [step, setupRequired]);
  async function request(kind: PermissionKind) {
    if (pending !== null || !setupRequired) {
      return;
    }
    const current = ++operation.current;
    setPending(kind);
    setLocalError(null);
    try {
      const result = await requestDesktopPermission(kind);
      if (operation.current === current) {
        setStatuses(previous => ({...previous, [kind]: result}));
      }
    } catch {
      if (operation.current === current) {
        setLocalError(
          'Permission request failed. Try again or continue without it.',
        );
      }
    } finally {
      if (operation.current === current) {
        setPending(null);
      }
    }
  }
  function link(url: string) {
    const current = operation.current;
    Linking.openURL(url).catch(() => {
      if (operation.current === current) {
        setLocalError('Could not open the link. Please try again.');
      }
    });
  }
  const steps: Step[] = [
    'value',
    'signIn',
    'permissions',
    'tutorial',
    'finish',
  ];
  const index = steps.indexOf(step);
  const title = {
    welcome: 'Welcome to Omi',
    value: 'Your context, with you in control',
    signIn: 'Make it yours',
    permissions: 'Choose what Omi can access',
    tutorial: 'A quick look around',
    finish: 'Ready when you are',
  }[step];
  const action = (label: string, onPress: () => void, disabled = false) => (
    <Button
      accessibilityLabel={label}
      disabled={disabled}
      onPress={onPress}
      style={styles.button}
      labelStyle={styles.buttonLabel}>
      {label}
    </Button>
  );
  return (
    <ScrollView
      accessibilityLabel="First-run onboarding"
      contentContainerStyle={styles.surface}>
      <View style={styles.card}>
        <OmiAvatar
          identity="omi"
          size={80}
          tone="ink"
          inkColor={token.color.ink}
          animate={false}
          reduceMotion
        />
        {index >= 0 ? (
          <Text style={styles.meta}>
            Step {index + 1} of {steps.length}
          </Text>
        ) : null}
        <Text accessibilityRole="header" style={styles.title}>
          {title}
        </Text>
        {step === 'welcome' ? (
          <>
            <Text style={styles.copy}>
              Find your conversations, manage your tasks, and revisit what you
              chose to capture.
            </Text>
            {action('Get started', () => setStep('value'))}
          </>
        ) : null}
        {step === 'value' ? (
          <>
            <Text style={styles.copy}>
              Omi saves conversations and recordings to your account. Cloud AI
              services transcribe audio and use your messages to generate
              replies.
            </Text>
            <Text style={styles.copy}>
              Recall can save screen images and local text recognition on this
              Mac when you start capture. Signing in or granting permission does
              not start recording.
            </Text>
            <View style={styles.links}>
              <Button
                variant="ghost"
                labelStyle={styles.copy}
                accessibilityRole="link"
                onPress={() => link('https://www.omi.me/pages/privacy')}>
                Privacy policy
              </Button>
              <Button
                variant="ghost"
                labelStyle={styles.copy}
                accessibilityRole="link"
                onPress={() =>
                  link('https://www.omi.me/pages/terms-of-service')
                }>
                Terms of service
              </Button>
            </View>
            {action('Continue', () =>
              setStep(setupRequired ? 'permissions' : 'signIn'),
            )}
          </>
        ) : null}
        {step === 'signIn' ? (
          <>
            <Text style={styles.copy}>
              Sign in to the account where your conversations and memories
              belong.
            </Text>
            {action(signingIn ? 'Signing in…' : 'Sign in', onSignIn, signingIn)}
            {signingIn && onCancelSignIn ? (
              <Button
                variant="ghost"
                labelStyle={styles.copy}
                accessibilityLabel="Cancel sign in"
                onPress={onCancelSignIn}>
                Cancel sign in
              </Button>
            ) : null}
          </>
        ) : null}
        {step === 'permissions' && setupRequired ? (
          <>
            <Text style={styles.copy}>
              Each permission is optional. Nothing starts recording here; you
              can change access later in Settings.
            </Text>
            {permissions.map(({kind, title: permissionTitle, copy}) => (
              <View key={kind} style={styles.permission}>
                <Text style={styles.permissionTitle}>{permissionTitle}</Text>
                <Text style={styles.copy}>{copy}</Text>
                <Text style={styles.meta}>
                  {pending === kind
                    ? 'Waiting for macOS…'
                    : permissionCopy[statuses[kind]]}
                </Text>
                <Button
                  variant="ghost"
                  labelStyle={styles.copy}
                  accessibilityLabel={`Allow ${permissionTitle.toLowerCase()}`}
                  disabled={pending !== null || statuses[kind] === 'granted'}
                  onPress={() => {
                    request(kind);
                  }}>
                  Allow {permissionTitle.toLowerCase()}
                </Button>
              </View>
            ))}
            {action('Continue without more permissions', () =>
              setStep('tutorial'),
            )}
          </>
        ) : null}
        {step === 'tutorial' && setupRequired ? (
          <>
            <Text style={styles.copy}>
              Home brings together recent conversations and tasks. Use
              Conversations to review recordings, Tasks to manage follow-ups,
              and Recall to browse screen history. The capture toggle beside
              Settings starts or stops screen capture.
            </Text>
            <Text style={styles.copy}>
              Connect an Omi device from Settings when you want to record.
              Settings keeps your account and permissions in reach.
            </Text>
            {action('Continue', () => setStep('finish'))}
          </>
        ) : null}
        {step === 'finish' && setupRequired ? (
          <>
            <Text style={styles.copy}>
              By continuing, you agree to the Terms of service and acknowledge
              the Privacy policy described earlier. No capture starts
              automatically.
            </Text>
            {action(
              completingSetup ? 'Saving…' : 'Agree and continue',
              () => onCompleteSetup?.(false),
              completingSetup || !onCompleteSetup,
            )}
          </>
        ) : null}
        {error || localError ? (
          <Text accessibilityRole="alert" style={styles.copy}>
            {error || localError}
          </Text>
        ) : null}
        {step === 'value' || (step === 'signIn' && !signingIn) ? (
          <Button
            variant="ghost"
            labelStyle={styles.copy}
            onPress={() => setStep(step === 'value' ? 'welcome' : 'value')}>
            Back
          </Button>
        ) : null}
        {setupRequired && onSignOut ? (
          <Button
            variant="ghost"
            labelStyle={styles.copy}
            disabled={completingSetup}
            onPress={onSignOut}>
            Sign out
          </Button>
        ) : null}
      </View>
    </ScrollView>
  );
}
const styles = StyleSheet.create({
  surface: {
    flexGrow: 1,
    alignItems: 'center',
    justifyContent: 'center',
    padding: 32,
  },
  card: {width: '100%', maxWidth: 560, alignItems: 'center', gap: 18},
  title: {
    fontSize: 30,
    lineHeight: 36,
    fontWeight: '600',
    color: token.color.ink,
    textAlign: 'center',
  },
  copy: {
    fontSize: 15,
    lineHeight: 22,
    color: token.color.inkMuted,
    textAlign: 'center',
  },
  meta: {fontSize: 12, color: token.color.inkMuted},
  links: {flexDirection: 'row', flexWrap: 'wrap', justifyContent: 'center'},
  permission: {
    alignSelf: 'stretch',
    alignItems: 'center',
    padding: 16,
    gap: 8,
    borderWidth: 1,
    borderColor: token.color.lineStrong,
    borderRadius: token.radius.control,
  },
  permissionTitle: {fontSize: 16, fontWeight: '600', color: token.color.ink},
  button: {backgroundColor: token.color.dark},
  buttonLabel: {color: token.color.white},
});
