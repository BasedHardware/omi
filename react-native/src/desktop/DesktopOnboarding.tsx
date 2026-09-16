import React, {useEffect, useRef, useState} from 'react';
import {
  Animated,
  Linking,
  ScrollView,
  StyleSheet,
  Text,
  View,
} from 'react-native';
import {useReduceMotion} from '../app/useReduceMotion';
import {
  DESKTOP_VALUE_CLAIMS,
  PRIVACY_URL,
  TERMS_URL,
} from '../app/onboardingCopy';
import {
  desktopProgressSteps,
  nextDesktopStep,
  previousDesktopStep,
  type DesktopOnboardingStep,
} from '../app/onboardingFlow';
import {runShippingTiming, stepMotionDuration} from './desktopMotion';
import {
  loadPermissionStatus,
  requestDesktopPermission,
  type PermissionKind,
  type PermissionState,
} from '../desktopSettingsClient';
import {
  HARNESS_GROUPS,
  ONBOARDING_HARNESSES,
  type HarnessState,
} from '../app/onboardingHarnesses';
import {Button} from '../ui/Button';
import {OmiAvatar} from '../ui/OmiAvatar';
import {PermissionRow} from '../ui/PermissionRow';
import type {Onboarding} from '../ui/Onboarding';
import {desktopTokens as token} from './tokens';

type Props = React.ComponentProps<typeof Onboarding>;
const permissions: {kind: PermissionKind; title: string}[] = [
  {
    kind: 'screen',
    title: "I would like to see your screen, so I know what you're working on.",
  },
  {
    kind: 'microphone',
    title:
      'I would like to use your microphone, so I can hear what you talk about.',
  },
  {
    kind: 'notifications',
    title: 'I would like to notify you when something needs you.',
  },
];

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
  const [step, setStep] = useState<DesktopOnboardingStep>('welcome');
  const [statuses, setStatuses] = useState<
    Record<PermissionKind, PermissionState>
  >({screen: 'unknown', microphone: 'unknown', notifications: 'unknown'});
  const [pending, setPending] = useState<PermissionKind | null>(null);
  const [localError, setLocalError] = useState<string | null>(null);
  const [harnessStates, setHarnessStates] = useState<
    Record<string, HarnessState>
  >({});
  const operation = useRef(0);
  const signedIn = useRef(setupRequired);
  const reduceMotion = useReduceMotion();
  const stepOpacity = useRef(new Animated.Value(1)).current;
  const stepY = useRef(new Animated.Value(0)).current;
  const firstStep = useRef(true);

  useEffect(() => {
    if (firstStep.current) {
      firstStep.current = false;
      return;
    }
    const duration = stepMotionDuration(reduceMotion);
    if (duration === 0) {
      stepOpacity.setValue(1);
      stepY.setValue(0);
      return;
    }
    stepOpacity.setValue(0.92);
    stepY.setValue(8);
    const animation = Animated.parallel(
      [
        runShippingTiming(stepOpacity, 1, duration, false),
        runShippingTiming(stepY, 0, duration, false),
      ].filter((item): item is Animated.CompositeAnimation => item !== null),
    );
    animation.start();
    return () => animation.stop();
  }, [reduceMotion, step, stepOpacity, stepY]);

  useEffect(() => {
    if (signedIn.current && !setupRequired) {
      operation.current++;
      setStep('welcome');
      setPending(null);
      setLocalError(null);
      setHarnessStates({});
      setStatuses({
        screen: 'unknown',
        microphone: 'unknown',
        notifications: 'unknown',
      });
    } else if (setupRequired && step === 'signIn') {
      const next = nextDesktopStep('signIn', true);
      if (next != null) {
        setStep(next);
      }
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

  function advance() {
    const next = nextDesktopStep(step, setupRequired);
    if (next != null) {
      setLocalError(null);
      setStep(next);
    }
  }

  function goBack() {
    const previous = previousDesktopStep(step, setupRequired);
    if (previous != null) {
      setLocalError(null);
      setStep(previous);
    }
  }

  const progress = desktopProgressSteps(setupRequired);
  const progressIndex = progress.indexOf(step);
  const title = {
    welcome: 'Welcome to Omi',
    value: "Here's what I do.",
    signIn: 'Which account is this?',
    permissions: 'Now the permissions.',
    harnesses: 'Connect harnesses',
    tutorial: 'A quick look around',
    finish: 'Ready when you are',
  }[step];
  const listCard = step === 'permissions' || step === 'harnesses';
  const action = (label: string, onPress: () => void, disabled = false) => (
    <Button
      accessibilityLabel={label}
      disabled={disabled}
      onPress={onPress}
      style={[styles.button, listCard && styles.buttonList]}
      labelStyle={styles.buttonLabel}>
      {label}
    </Button>
  );

  return (
    <ScrollView
      accessibilityLabel="First-run onboarding"
      contentContainerStyle={[styles.surface, listCard && styles.surfaceList]}>
      <View style={[styles.card, listCard && styles.cardList]}>
        {listCard ? (
          <View style={styles.speaker}>
            <OmiAvatar
              identity="omi"
              size={72}
              tone="ink"
              inkColor={token.color.ink}
              animate={!reduceMotion}
              reduceMotion={reduceMotion}
            />
            <View style={styles.speakerCopy}>
              {progressIndex >= 0 ? (
                <Text style={styles.meta}>
                  Step {progressIndex + 1} of {progress.length}
                </Text>
              ) : null}
              <Text
                accessibilityRole="header"
                style={[styles.title, styles.titleList]}>
                {title}
              </Text>
            </View>
          </View>
        ) : (
          <>
            <OmiAvatar
              identity="omi"
              size={80}
              tone="ink"
              inkColor={token.color.ink}
              animate={!reduceMotion}
              reduceMotion={reduceMotion}
            />
            {progressIndex >= 0 ? (
              <Text style={styles.meta}>
                Step {progressIndex + 1} of {progress.length}
              </Text>
            ) : null}
            <Text accessibilityRole="header" style={styles.title}>
              {title}
            </Text>
          </>
        )}
        <Animated.View
          style={[
            styles.step,
            listCard && styles.stepList,
            {opacity: stepOpacity, transform: [{translateY: stepY}]},
          ]}>
          {step === 'welcome' ? (
            <>
              <Text style={styles.copy}>
                I keep you caught up on what you see and say.
              </Text>
              {action('Get started', () => setStep('value'))}
            </>
          ) : null}
          {step === 'value' ? (
            <>
              <Text style={styles.copy}>
                Three things I take in, and one place they go.
              </Text>
              {DESKTOP_VALUE_CLAIMS.map(claim => (
                <Text key={claim} style={styles.copy}>
                  {claim}
                </Text>
              ))}
              <Text style={styles.copy}>
                Cloud AI services transcribe audio and use your messages to
                generate replies. Signing in or granting permission does not
                start recording.
              </Text>
              <View style={styles.links}>
                <Button
                  variant="ghost"
                  labelStyle={styles.copy}
                  accessibilityRole="link"
                  onPress={() => link(PRIVACY_URL)}>
                  Privacy policy
                </Button>
                <Button
                  variant="ghost"
                  labelStyle={styles.copy}
                  accessibilityRole="link"
                  onPress={() => link(TERMS_URL)}>
                  Terms of service
                </Button>
              </View>
              {action('Continue', advance)}
            </>
          ) : null}
          {step === 'signIn' ? (
            <>
              <Text style={styles.copy}>
                It all lands in your Omi account. Sign in to the account where
                your conversations and memories belong.
              </Text>
              {action(
                signingIn ? 'Signing in…' : 'Sign in',
                onSignIn,
                signingIn,
              )}
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
              <Text style={styles.aside}>
                Click one when you’re ready. Nothing is asked until you do.
              </Text>
              {permissions.map(({kind, title: permissionTitle}) => {
                const granted = statuses[kind] === 'granted';
                const status =
                  pending === kind
                    ? 'Asking…'
                    : granted
                    ? 'Granted'
                    : statuses[kind] === 'denied'
                    ? 'Open Settings'
                    : 'Allow';
                return (
                  <PermissionRow
                    key={kind}
                    disabled={pending !== null}
                    granted={granted}
                    light
                    onPress={() => {
                      request(kind);
                    }}
                    status={status}
                    title={permissionTitle}
                  />
                );
              })}
              {action("I'll do these later", advance)}
            </>
          ) : null}
          {step === 'harnesses' && setupRequired ? (
            <>
              <Text style={styles.aside}>
                Optional. Connect the surfaces Omi can read and the agents that
                can act for you.
              </Text>
              {HARNESS_GROUPS.map(group => (
                <View key={group.kind} style={styles.harnessGroup}>
                  <Text style={styles.harnessGroupTitle}>{group.title}</Text>
                  {ONBOARDING_HARNESSES.filter(
                    harness => harness.kind === group.kind,
                  ).map((harness, index, rows) => {
                    const state = harnessStates[harness.id] ?? 'idle';
                    return (
                      <View
                        key={harness.id}
                        style={[
                          styles.harness,
                          index < rows.length - 1 && styles.harnessRule,
                        ]}>
                        <View style={styles.harnessMark}>
                          <Text style={styles.harnessMarkLabel}>
                            {harness.mark}
                          </Text>
                        </View>
                        <View style={styles.harnessCopy}>
                          <Text style={styles.permissionTitle}>
                            {harness.name}
                          </Text>
                          <Text style={styles.harnessDetail}>
                            {harness.detail}
                          </Text>
                        </View>
                        {state === 'on' ? (
                          <Text style={styles.harnessOn}>✓ on</Text>
                        ) : (
                          <Button
                            accessibilityLabel={`Connect ${harness.name}`}
                            disabled={state === 'connecting'}
                            onPress={() => {
                              setHarnessStates(previous => ({
                                ...previous,
                                [harness.id]: 'connecting',
                              }));
                              setTimeout(() => {
                                setHarnessStates(previous => ({
                                  ...previous,
                                  [harness.id]: 'on',
                                }));
                              }, 240);
                            }}
                            variant="ghost"
                            labelStyle={styles.harnessConnect}>
                            {state === 'connecting' ? '…' : 'Connect'}
                          </Button>
                        )}
                      </View>
                    );
                  })}
                </View>
              ))}
              {action('Continue', advance)}
            </>
          ) : null}
          {step === 'tutorial' && setupRequired ? (
            <>
              <Text style={styles.copy}>
                A few minutes. You’ll open Home, review conversations and tasks,
                travel back through Recall, and finish with Chat answering a
                question about your day.
              </Text>
              {action('Show me', advance)}
              {action('Not now', advance)}
            </>
          ) : null}
          {step === 'finish' && setupRequired ? (
            <>
              <Text style={styles.copy}>
                I live here. Home can read conversations, memories, and tasks
                from your account. By continuing, you agree to the Terms of
                service and acknowledge the Privacy policy described earlier. No
                capture starts automatically.
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
          {previousDesktopStep(step, setupRequired) != null && !signingIn ? (
            <Button variant="ghost" labelStyle={styles.copy} onPress={goBack}>
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
        </Animated.View>
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
  surfaceList: {
    alignItems: 'stretch',
    justifyContent: 'flex-start',
    paddingHorizontal: 36,
    paddingVertical: 34,
  },
  card: {width: '100%', maxWidth: 488, alignItems: 'center', gap: 18},
  cardList: {maxWidth: 560, alignItems: 'stretch', gap: 16},
  speaker: {
    alignItems: 'center',
    flexDirection: 'row',
    gap: 16,
  },
  speakerCopy: {flex: 1, gap: 4},
  step: {width: '100%', alignItems: 'center', gap: 18},
  stepList: {alignItems: 'stretch', gap: 8},
  title: {
    fontSize: 30,
    letterSpacing: -0.81,
    lineHeight: 36,
    fontWeight: '600',
    color: token.color.ink,
    textAlign: 'center',
  },
  titleList: {fontSize: 27, textAlign: 'left'},
  copy: {
    fontSize: 17,
    letterSpacing: -0.17,
    lineHeight: 26,
    color: token.color.inkMuted,
    textAlign: 'center',
  },
  aside: {
    color: token.color.inkMuted,
    fontSize: 17,
    letterSpacing: -0.17,
    lineHeight: 26,
    marginBottom: 6,
    textAlign: 'left',
  },
  meta: {fontSize: 12, color: token.color.inkMuted},
  links: {flexDirection: 'row', flexWrap: 'wrap', justifyContent: 'center'},
  permissionTitle: {
    color: token.color.ink,
    fontSize: 15,
    fontWeight: '500',
    letterSpacing: -0.15,
  },
  harnessGroup: {
    alignSelf: 'stretch',
    backgroundColor: 'rgba(0,0,0,0.045)',
    borderColor: 'rgba(0,0,0,0.08)',
    borderRadius: 16,
    borderWidth: 1,
    overflow: 'hidden',
    paddingHorizontal: 14,
  },
  harnessGroupTitle: {
    color: token.color.ink,
    fontSize: 13,
    fontWeight: '600',
    letterSpacing: 0.2,
    paddingTop: 10,
    paddingBottom: 4,
  },
  harness: {
    alignItems: 'center',
    flexDirection: 'row',
    gap: 12,
    paddingVertical: 8,
  },
  harnessRule: {
    borderBottomColor: 'rgba(0,0,0,0.08)',
    borderBottomWidth: StyleSheet.hairlineWidth,
  },
  harnessMark: {
    alignItems: 'center',
    backgroundColor: token.color.ink,
    borderRadius: 7,
    height: 26,
    justifyContent: 'center',
    width: 26,
  },
  harnessMarkLabel: {
    color: token.color.white,
    fontSize: 9,
    fontWeight: '700',
  },
  harnessCopy: {flex: 1, gap: 1},
  harnessDetail: {
    color: token.color.inkMuted,
    fontSize: 12,
    lineHeight: 16,
  },
  harnessOn: {color: token.color.inkMuted, fontSize: 12},
  harnessConnect: {color: token.color.ink, fontSize: 13, fontWeight: '600'},
  button: {backgroundColor: token.color.dark},
  buttonList: {alignSelf: 'flex-start'},
  buttonLabel: {color: token.color.white},
});
