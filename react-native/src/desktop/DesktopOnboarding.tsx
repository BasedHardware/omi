import React, {useEffect, useRef, useState} from 'react';
import {
  Animated,
  AppState,
  Linking,
  ScrollView,
  StyleSheet,
  Text,
  View,
} from 'react-native';
import Check from 'lucide-react-native/icons/check';
import ShieldCheck from 'lucide-react-native/icons/shield-check';
import Monitor from 'lucide-react-native/icons/monitor';
import Mic from 'lucide-react-native/icons/mic';
import Bell from 'lucide-react-native/icons/bell';
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
import {
  loadPermissionStatus,
  requestDesktopPermission,
  type PermissionKind,
  type PermissionState,
} from '../desktopSettingsClient';
import {Button} from '../ui/Button';
import {FocusPressable} from '../ui/Pressable';
import {OmiAvatar} from '../ui/OmiAvatar';
import {PermissionRow} from '../ui/PermissionRow';
import type {Onboarding} from '../ui/Onboarding';
import {ConnectionGallery} from './ConnectionGallery';
import {DesktopWindow} from './DesktopWindow';
import {ShippingStage} from './ShippingStage';
import {desktopTokens as token} from './tokens';

type Props = React.ComponentProps<typeof Onboarding>;
const permissions: {
  kind: PermissionKind;
  title: string;
  description: string;
  icon: typeof Monitor;
  instructions: string[];
}[] = [
  {
    kind: 'screen',
    title: 'Screen',
    description: 'Remember what you’re working on.',
    icon: Monitor,
    instructions: [
      'Open Privacy & Security → Screen Recording in System Settings.',
      'Switch on Omi. If macOS asks you to quit and reopen, reopen Omi to finish.',
    ],
  },
  {
    kind: 'microphone',
    title: 'Microphone',
    description: 'Turn conversations into memories.',
    icon: Mic,
    instructions: [
      'Choose Allow in the macOS permission prompt.',
      'Already said no? Open Privacy & Security → Microphone in System Settings and switch on Omi.',
    ],
  },
  {
    kind: 'notifications',
    title: 'Notifications',
    description: 'A nudge when something needs you.',
    icon: Bell,
    instructions: [
      'Choose Allow in the macOS notification prompt.',
      'Already said no? Open Notifications → Omi in System Settings and turn on Allow Notifications.',
    ],
  },
];
const titles: Record<DesktopOnboardingStep, string> = {
  welcome: 'A little less to remember.',
  value: "Here's what I do.",
  signIn: 'Make yourself at home.',
  permissions: 'Now the permissions.',
  harnesses: 'Meet your next collaborators.',
  data: 'Your world, connected.',
  tutorial: 'Everything has its place.',
  finish: 'Ready when you are.',
};
const stepLabels: Record<DesktopOnboardingStep, string> = {
  welcome: 'Welcome',
  value: 'Meet Omi',
  signIn: 'Your account',
  permissions: 'Permissions',
  harnesses: 'AI assistants',
  data: 'Connect data',
  tutorial: 'A quick look',
  finish: 'Get started',
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
  desktopHandoff,
}: Props) {
  const [step, setStep] = useState<DesktopOnboardingStep>('welcome');
  const [statuses, setStatuses] = useState<
    Record<PermissionKind, PermissionState>
  >({
    screen: 'unknown',
    microphone: 'unknown',
    notifications: 'unknown',
  });
  const [pending, setPending] = useState<PermissionKind | null>(null);
  const [guidance, setGuidance] = useState<PermissionKind | null>(null);
  const [localError, setLocalError] = useState<string | null>(null);
  const [greeting, setGreeting] = useState(0);
  const operation = useRef(0);
  const signedIn = useRef(setupRequired);
  const scroll = useRef<ScrollView>(null);
  const reduceMotion = useReduceMotion();

  useEffect(() => {
    if (signedIn.current && !setupRequired) {
      operation.current++;
      setStep('welcome');
      setPending(null);
      setGuidance(null);
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
    lifetime.current++;
    setPending(null);
    setGuidance(null);
    setLocalError(null);
    scroll.current?.scrollTo({y: 0, animated: false});
    let active = true;
    let checking = false;
    async function refresh() {
      if (checking) {
        return;
      }
      checking = true;
      const current = lifetime.current;
      try {
        const value = await loadPermissionStatus();
        if (active && current === lifetime.current) {
          setStatuses(value);
        }
      } catch {
        if (active && current === lifetime.current) {
          setLocalError(
            'Could not check permissions. You can continue and manage them in Settings.',
          );
        }
      } finally {
        checking = false;
      }
    }
    if (step !== 'permissions' || !setupRequired) {
      return () => {
        active = false;
        lifetime.current++;
      };
    }
    void refresh();
    // macOS may grant while Settings is frontmost. Observe return AND poll;
    // neither can advance the step or start capture on the user's behalf.
    const timer = setInterval(refresh, 1500);
    const subscription = AppState.addEventListener('change', state => {
      if (state === 'active') {
        void refresh();
      }
    });
    return () => {
      active = false;
      lifetime.current++;
      clearInterval(timer);
      subscription.remove();
    };
  }, [step, setupRequired]);

  async function request(kind: PermissionKind) {
    if (pending !== null || !setupRequired || statuses[kind] === 'granted') {
      return;
    }
    const current = ++operation.current;
    setPending(kind);
    setGuidance(kind);
    setLocalError(null);
    try {
      const result = await requestDesktopPermission(kind);
      if (operation.current === current) {
        setStatuses(previous => ({...previous, [kind]: result}));
        if (result === 'unknown') {
          setLocalError(
            'Permission controls are available in the native Mac app. You can continue here.',
          );
        }
      }
    } catch {
      if (operation.current === current) {
        setLocalError(
          'Permission request failed. Try again or continue without it.',
        );
      }
    } finally {
      if (operation.current === current) {
        // A poll begun during the OS prompt must not overwrite its newer result.
        operation.current++;
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
    if (next !== null) {
      setStep(next);
    }
  }
  const back = previousDesktopStep(step, setupRequired);
  const progress = desktopProgressSteps(setupRequired);
  const progressIndex = progress.indexOf(step);
  const welcome = step === 'welcome';
  const guide = step === 'permissions' && setupRequired ? guidance : null;
  const guideGranted = guide !== null && statuses[guide] === 'granted';
  const guidePermission = permissions.find(item => item.kind === guide);
  const allGranted = permissions.every(
    ({kind}) => statuses[kind] === 'granted',
  );
  const primaryLabel = welcome
    ? 'Get started'
    : step === 'signIn'
    ? signingIn
      ? 'Signing in…'
      : 'Sign in'
    : step === 'finish'
    ? completingSetup
      ? 'Saving…'
      : 'Agree and continue'
    : 'Continue';
  const primaryDisabled =
    step === 'signIn'
      ? signingIn
      : step === 'finish'
      ? completingSetup || !onCompleteSetup
      : false;
  const primary = () => {
    if (step === 'signIn') {
      onSignIn();
    } else if (step === 'finish') {
      onCompleteSetup?.(false);
    } else {
      advance();
    }
  };

  return (
    <View accessibilityLabel="First-run onboarding" style={styles.surface}>
      <DesktopWindow presentation={guide ? 'permission-guide' : 'onboarding'} />
      {guide ? (
        <>
          <ScrollView contentContainerStyle={styles.guide}>
            <View style={styles.guideHeading}>
              <OmiAvatar
                identity="omi"
                size={52}
                tone="ink"
                inkColor={token.color.ink}
                motion={
                  guideGranted ? 'success' : localError ? undefined : 'breathe'
                }
                motionKey={guide}
                reduceMotion={reduceMotion}
              />
              <View style={[styles.heading, styles.flex]}>
                <Text style={styles.eyebrow}>A little help from Omi</Text>
                <Text accessibilityRole="header" style={styles.guideTitle}>
                  {guideGranted
                    ? 'You’re all set.'
                    : guide === 'screen'
                    ? 'Screen Recording'
                    : guidePermission?.title}
                </Text>
              </View>
            </View>
            <ShippingStage
              stageKey={guideGranted ? 'granted' : guide}
              variant="hub"
              style={styles.stage}>
              {guideGranted ? (
                <Text style={styles.guideCopy}>
                  macOS confirmed this permission. Nothing has started
                  recording.
                </Text>
              ) : (
                guidePermission?.instructions.map((instruction, index) => (
                  <View key={instruction} style={styles.instruction}>
                    <Text style={styles.instructionNumber}>{index + 1}</Text>
                    <Text style={[styles.guideCopy, styles.flex]}>
                      {instruction}
                    </Text>
                  </View>
                ))
              )}
              <View accessibilityLiveRegion="polite" style={styles.guideStatus}>
                {guideGranted ? (
                  <Check size={15} color={token.color.ink} />
                ) : (
                  <View style={styles.waitingDot} />
                )}
                <Text style={styles.small}>
                  {guideGranted
                    ? 'Permission granted'
                    : localError
                    ? 'Not enabled yet'
                    : 'Checking macOS permission…'}
                </Text>
              </View>
              {localError ? (
                <Text accessibilityRole="alert" style={styles.error}>
                  {localError}
                </Text>
              ) : null}
            </ShippingStage>
          </ScrollView>
          <View style={styles.guideFooter}>
            <Button
              variant="ghost"
              style={styles.guideBack}
              labelStyle={styles.small}
              onPress={() => setGuidance(null)}>
              Back to setup
            </Button>
          </View>
        </>
      ) : (
        <>
          <ScrollView
            ref={scroll}
            contentContainerStyle={[
              styles.content,
              welcome && styles.welcomeContent,
            ]}>
            <View style={[styles.page, welcome && styles.welcomePage]}>
              <View style={[styles.heading, !welcome && styles.compactHeading]}>
                <FocusPressable
                  accessibilityRole="button"
                  accessibilityLabel="Say hello to Omi"
                  onPress={() => setGreeting(value => value + 1)}>
                  <OmiAvatar
                    identity="omi"
                    size={welcome ? 104 : 52}
                    tone="ink"
                    inkColor={token.color.ink}
                    motion={
                      signingIn || completingSetup
                        ? 'breathe'
                        : welcome
                        ? 'arrive'
                        : 'gather'
                    }
                    motionKey={`${step}:${greeting}`}
                    reduceMotion={reduceMotion}
                  />
                </FocusPressable>
                <View style={[styles.heading, !welcome && styles.flex]}>
                  <Text style={styles.eyebrow}>
                    {welcome
                      ? 'Welcome to Omi'
                      : `Step ${progressIndex + 1} of ${progress.length}  /  ${
                          stepLabels[step]
                        }`}
                  </Text>
                  <Text
                    accessibilityRole="header"
                    style={[styles.title, welcome && styles.welcomeTitle]}>
                    {titles[step]}
                  </Text>
                </View>
              </View>
              <ShippingStage stageKey={step} variant="hub" style={styles.stage}>
                {welcome ? (
                  <Text style={[styles.copy, styles.welcomeCopy]}>
                    A place for what you see, say, and think.{'\n'}A little more
                    room for what comes next.
                  </Text>
                ) : null}
                {step === 'value' ? (
                  <>
                    <Text style={styles.copy}>
                      Less keeping track. More being here.
                    </Text>
                    <View style={styles.featureList}>
                      {DESKTOP_VALUE_CLAIMS.map((claim, index) => (
                        <View key={claim} style={styles.feature}>
                          <Text style={styles.featureNumber}>0{index + 1}</Text>
                          <Text style={styles.featureText}>{claim}</Text>
                        </View>
                      ))}
                    </View>
                    <Text style={styles.small}>
                      Cloud AI services transcribe audio and use your messages
                      to generate replies. Signing in or granting permission
                      does not start recording.
                    </Text>
                    <View style={styles.links}>
                      <Button
                        variant="ghost"
                        labelStyle={styles.small}
                        accessibilityRole="link"
                        onPress={() => link(PRIVACY_URL)}>
                        Privacy policy
                      </Button>
                      <Button
                        variant="ghost"
                        labelStyle={styles.small}
                        accessibilityRole="link"
                        onPress={() => link(TERMS_URL)}>
                        Terms of service
                      </Button>
                    </View>
                  </>
                ) : null}
                {step === 'signIn' ? (
                  <>
                    <Text style={styles.copy}>
                      Your conversations, memories, and ideas belong together.
                      Sign in to the Omi account you call yours.
                    </Text>
                    {signingIn && desktopHandoff ? (
                      <View style={styles.codeCard}>
                        <Text style={styles.small}>
                          Finish in your browser, then enter this code on the
                          Omi sign-in page.
                        </Text>
                        <Text
                          accessibilityLabel={`Desktop sign-in code ${desktopHandoff.code}`}
                          style={styles.code}>
                          {desktopHandoff.code}
                        </Text>
                        <Button
                          variant="ghost"
                          labelStyle={styles.small}
                          accessibilityRole="link"
                          onPress={() => link(desktopHandoff.browserUrl)}>
                          Open the sign-in page again
                        </Button>
                      </View>
                    ) : null}
                    <View style={styles.note}>
                      <ShieldCheck size={22} color={token.color.inkMuted} />
                      <Text style={[styles.small, styles.flex]}>
                        Your existing memories stay with your account. Nothing
                        starts recording when you sign in.
                      </Text>
                    </View>
                    {signingIn && onCancelSignIn ? (
                      <Button
                        variant="ghost"
                        labelStyle={styles.small}
                        onPress={onCancelSignIn}>
                        Cancel sign in
                      </Button>
                    ) : null}
                  </>
                ) : null}
                {step === 'permissions' && setupRequired ? (
                  <>
                    <Text style={styles.copy}>
                      A little access, on your terms. Choose what you’d like Omi
                      to remember.
                    </Text>
                    <View style={styles.permissionList}>
                      {permissions.map(
                        (
                          {kind, title, description, icon: PermissionIcon},
                          index,
                        ) => (
                          <React.Fragment key={kind}>
                            {index > 0 ? (
                              <View style={styles.permissionDivider} />
                            ) : null}
                            <PermissionRow
                              light
                              grouped
                              title={title}
                              description={description}
                              icon={
                                <PermissionIcon
                                  size={21}
                                  color={token.color.inkMuted}
                                />
                              }
                              granted={statuses[kind] === 'granted'}
                              disabled={
                                pending !== null || statuses[kind] === 'granted'
                              }
                              status={
                                pending === kind
                                  ? 'Asking…'
                                  : statuses[kind] === 'granted'
                                  ? 'Granted'
                                  : statuses[kind] === 'denied'
                                  ? 'Open Settings'
                                  : 'Allow'
                              }
                              onPress={() => {
                                void request(kind);
                              }}
                            />
                          </React.Fragment>
                        ),
                      )}
                    </View>
                    <Text style={styles.small}>
                      {allGranted
                        ? 'All set. Continue whenever you’re ready.'
                        : 'If macOS opens System Settings, I’ll stay nearby to guide you. You can come back or skip at any time.'}
                    </Text>
                    <Text style={styles.small}>
                      Permission is not recording. Capture stays off until you
                      start it.
                    </Text>
                  </>
                ) : null}
                {step === 'harnesses' && setupRequired ? (
                  <>
                    <Text style={styles.copy}>
                      A gallery of AI assistants for your everyday work.
                    </Text>
                    <ConnectionGallery kind="agent" />
                  </>
                ) : null}
                {step === 'data' && setupRequired ? (
                  <>
                    <Text style={styles.copy}>
                      Your notes, plans, and ideas. Explore the sources coming
                      to Omi.
                    </Text>
                    <ConnectionGallery kind="context" />
                  </>
                ) : null}
                {step === 'tutorial' && setupRequired ? (
                  <>
                    <Text style={styles.copy}>
                      A quick look around your new space.
                    </Text>
                    <View style={styles.featureList}>
                      {[
                        [
                          'Home',
                          'Your conversations, memories, and tasks, brought together.',
                        ],
                        [
                          'Recall',
                          'Find a moment in your screen history after you enable capture.',
                        ],
                        ['Chat', 'Ask Omi a question about your day.'],
                      ].map(([name, detail]) => (
                        <View key={name} style={styles.feature}>
                          <Text style={styles.featureName}>{name}</Text>
                          <Text style={[styles.small, styles.flex]}>
                            {detail}
                          </Text>
                        </View>
                      ))}
                    </View>
                  </>
                ) : null}
                {step === 'finish' && setupRequired ? (
                  <>
                    <Text style={styles.copy}>
                      A calmer place for your day starts here.
                    </Text>
                    <View style={styles.note}>
                      <ShieldCheck size={22} color={token.color.inkMuted} />
                      <Text style={[styles.small, styles.flex]}>
                        No capture starts automatically. You choose what Omi can
                        remember.
                      </Text>
                    </View>
                    <Text style={styles.small}>
                      By continuing, you agree to the Terms of service and
                      acknowledge the Privacy policy described earlier.
                    </Text>
                  </>
                ) : null}
                {error || localError ? (
                  <Text accessibilityRole="alert" style={styles.error}>
                    {error || localError}
                  </Text>
                ) : null}
              </ShippingStage>
            </View>
          </ScrollView>
          <View style={styles.footer}>
            <View style={!welcome && styles.flex}>
              {back !== null && !signingIn ? (
                <Button
                  variant="ghost"
                  style={styles.back}
                  labelStyle={styles.small}
                  disabled={completingSetup}
                  onPress={() => setStep(back)}>
                  Back
                </Button>
              ) : null}
            </View>
            {step === 'permissions' && !allGranted ? (
              <Button
                accessibilityLabel="I'll do these later"
                variant="ghost"
                labelStyle={styles.small}
                onPress={advance}>
                I'll do these later
              </Button>
            ) : null}
            <Button
              accessibilityLabel={primaryLabel}
              disabled={primaryDisabled}
              onPress={primary}
              style={styles.primary}
              labelStyle={styles.primaryText}>
              {primaryLabel}
            </Button>
          </View>
          <View style={styles.bottomBar}>
            <OnboardingProgress
              index={progressIndex}
              count={progress.length}
              reduceMotion={reduceMotion}
            />
            {setupRequired && onSignOut ? (
              <Button
                variant="ghost"
                style={styles.signOut}
                labelStyle={styles.small}
                disabled={completingSetup}
                onPress={onSignOut}>
                Sign out
              </Button>
            ) : null}
          </View>
        </>
      )}
    </View>
  );
}

function OnboardingProgress({
  index,
  count,
  reduceMotion,
}: {
  index: number;
  count: number;
  reduceMotion: boolean;
}) {
  const position = useRef(new Animated.Value(Math.max(0, index) * 14)).current;
  useEffect(() => {
    const toValue = Math.max(0, index) * 14;
    if (reduceMotion) {
      position.setValue(toValue);
      return;
    }
    const animation = Animated.timing(position, {
      toValue,
      duration: 250,
      useNativeDriver: false,
      isInteraction: false,
    });
    animation.start();
    return () => animation.stop();
  }, [index, position, reduceMotion]);
  return (
    <View
      accessibilityLabel={
        index < 0 ? 'Welcome' : `Step ${index + 1} of ${count}`
      }
      style={styles.dots}>
      {Array.from({length: count}, (_, dot) => (
        <View key={dot} style={styles.dotSlot}>
          <View style={styles.dot} />
        </View>
      ))}
      <Animated.View
        style={[
          styles.dotActive,
          {opacity: index < 0 ? 0 : 1, transform: [{translateX: position}]},
        ]}
      />
    </View>
  );
}

const styles = StyleSheet.create({
  surface: {flex: 1, backgroundColor: 'transparent'},
  content: {
    flexGrow: 1,
    paddingHorizontal: 40,
    paddingTop: 52,
    paddingBottom: 24,
    alignItems: 'center',
  },
  page: {width: '100%', maxWidth: 680, gap: 16},
  heading: {gap: 12},
  compactHeading: {flexDirection: 'row', alignItems: 'center', gap: 20},
  eyebrow: {
    fontSize: 11,
    letterSpacing: 0.2,
    fontWeight: '600',
    color: token.color.inkMuted,
  },
  title: {
    fontSize: 29,
    lineHeight: 35,
    fontWeight: '600',
    letterSpacing: -0.9,
    color: token.color.ink,
  },
  stage: {flexBasis: 'auto', flexGrow: 0, flexShrink: 0, gap: 18},
  copy: {
    fontSize: 15,
    lineHeight: 23,
    color: token.color.inkMuted,
    maxWidth: 600,
  },
  small: {fontSize: 13, lineHeight: 21, color: token.color.inkMuted},
  flex: {flex: 1},
  featureList: {gap: 8},
  feature: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 20,
    paddingVertical: 14,
    borderBottomWidth: 1,
    borderColor: token.color.line,
  },
  featureNumber: {fontSize: 12, color: token.color.inkFaint},
  featureText: {fontSize: 16, lineHeight: 24, color: token.color.ink, flex: 1},
  featureName: {fontSize: 19, color: token.color.ink, width: 84},
  note: {
    flexDirection: 'row',
    gap: 14,
    alignItems: 'center',
    padding: 20,
    borderRadius: 14,
    backgroundColor: token.color.glassQuiet,
  },
  codeCard: {
    alignSelf: 'stretch',
    alignItems: 'center',
    gap: 10,
    padding: 20,
    borderRadius: 14,
    borderWidth: 1,
    borderColor: token.color.line,
    backgroundColor: token.color.glassQuiet,
  },
  code: {
    fontSize: 30,
    lineHeight: 36,
    fontWeight: '600',
    letterSpacing: 6,
    color: token.color.ink,
  },
  permissionList: {
    borderRadius: 18,
    overflow: 'hidden',
    borderWidth: 1,
    borderColor: token.color.line,
    backgroundColor: token.color.glassQuiet,
  },
  permissionDivider: {
    height: 1,
    marginLeft: 60,
    backgroundColor: token.color.line,
  },
  links: {flexDirection: 'row', flexWrap: 'wrap', gap: 12},
  footer: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    alignItems: 'center',
    gap: 12,
    paddingHorizontal: 40,
    paddingTop: 12,
    paddingBottom: 8,
    justifyContent: 'flex-end',
  },
  primary: {
    height: 40,
    paddingHorizontal: 24,
    borderRadius: 20,
    backgroundColor: token.color.ink,
  },
  primaryText: {color: token.color.white, fontSize: 14},
  back: {alignSelf: 'flex-start'},
  signOut: {marginLeft: 'auto'},
  error: {color: '#a0392e', fontSize: 14, lineHeight: 22},
  welcomeContent: {justifyContent: 'center'},
  welcomePage: {maxWidth: 600, alignItems: 'stretch', paddingVertical: 24},
  welcomeTitle: {fontSize: 40, lineHeight: 46, letterSpacing: -1.4},
  welcomeCopy: {alignSelf: 'flex-start'},
  bottomBar: {
    paddingHorizontal: 40,
    paddingBottom: 18,
    flexDirection: 'row',
    alignItems: 'center',
    minHeight: 40,
  },
  dots: {flexDirection: 'row', position: 'relative'},
  dotSlot: {width: 14, height: 6, alignItems: 'center'},
  dot: {
    height: 5,
    width: 5,
    borderRadius: 3,
    backgroundColor: token.color.lineStrong,
  },
  dotActive: {
    backgroundColor: token.color.ink,
    width: 14,
    height: 5,
    borderRadius: 3,
    position: 'absolute',
    left: 0,
    top: 0,
  },
  guide: {flexGrow: 1, padding: 28, paddingTop: 60, gap: 28},
  guideHeading: {flexDirection: 'row', gap: 14, alignItems: 'center'},
  instruction: {flexDirection: 'row', gap: 12, alignItems: 'flex-start'},
  instructionNumber: {
    fontSize: 11,
    lineHeight: 24,
    width: 24,
    textAlign: 'center',
    borderRadius: 12,
    overflow: 'hidden',
    color: token.color.inkMuted,
    backgroundColor: token.color.glassStrong,
  },
  guideFooter: {paddingHorizontal: 28, paddingBottom: 24, paddingTop: 8},
  guideTitle: {
    fontSize: 23,
    lineHeight: 29,
    fontWeight: '600',
    color: token.color.ink,
    letterSpacing: -0.7,
  },
  guideCopy: {fontSize: 14, lineHeight: 22, color: token.color.inkMuted},
  guideStatus: {flexDirection: 'row', gap: 8, alignItems: 'center'},
  waitingDot: {
    height: 5,
    width: 5,
    borderRadius: 3,
    backgroundColor: token.color.inkMuted,
  },
  guideBack: {alignSelf: 'flex-start', marginTop: 'auto'},
});
