import React, {useEffect, useMemo, useRef, useState} from 'react';
import {
  Animated,
  Easing,
  Linking,
  Platform,
  ScrollView,
  StyleSheet,
  Text,
  View,
} from 'react-native';
import {
  omiBackend,
  omiNative,
  requestBluetoothScanPermission,
} from '../omiNative';
import {
  loadAvailableLanguages,
  saveAcquisitionSource,
  savePrimaryLanguage,
  type AvailableLanguage,
} from '../app/onboardingClient';
import {
  ACQUISITION_SOURCES,
  PRIMARY_LANGUAGES,
  PRIVACY_URL,
  SESSION_UNREACHABLE_COPY,
  TERMS_URL,
} from '../app/onboardingCopy';
import {
  mobileSetupIndex,
  mobileSetupSteps,
  nextMobileSetupStep,
  previousMobileSetupStep,
  type MobileOnboardingStep,
  type MobileSetupStep,
} from '../app/onboardingFlow';
import {useReduceMotion} from '../app/useReduceMotion';
import {
  recordVoicePrintWav,
  uploadVoicePrint,
  VOICE_PRINT_MIN_SECONDS,
} from '../app/voicePrint';
import {desktopTokens} from '../desktop/tokens';
import {Button} from './Button';
import {Field} from './Field';
import {OmiAvatar} from './OmiAvatar';
import {PermissionRow} from './PermissionRow';
import {color as uiColor, tokens} from './tokens';

const DOTS_SIZE = 104;

type PermissionKind = 'notifications' | 'microphone' | 'bluetooth';
type PermissionState = 'unknown' | 'granted' | 'denied';

function openLink(url: string) {
  Linking.openURL(url).catch(() => undefined);
}

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
  const nativePhone = Platform.OS === 'ios' || Platform.OS === 'android';
  const opacity = useRef(new Animated.Value(1)).current;
  const scale = useRef(new Animated.Value(1)).current;
  const [step, setStep] = useState<MobileOnboardingStep>(
    setupRequired ? 'consent' : 'welcome',
  );
  const [name, setName] = useState('');
  const [language, setLanguage] = useState('en');
  const [languages, setLanguages] = useState<AvailableLanguage[]>(
    PRIMARY_LANGUAGES.map(item => ({code: item.code, name: item.name})),
  );
  const [source, setSource] = useState<string | null>(null);
  const [otherSource, setOtherSource] = useState('');
  const [permissions, setPermissions] = useState<
    Record<PermissionKind, PermissionState>
  >({notifications: 'unknown', microphone: 'unknown', bluetooth: 'unknown'});
  const [pendingPermission, setPendingPermission] =
    useState<PermissionKind | null>(null);
  const [localError, setLocalError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [connectAfterComplete, setConnectAfterComplete] = useState(false);
  const [recordingVoice, setRecordingVoice] = useState(false);
  const [voiceSaved, setVoiceSaved] = useState(false);
  const operation = useRef(0);
  const signedIn = useRef(setupRequired);

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

  useEffect(() => {
    if (signedIn.current && !setupRequired) {
      operation.current += 1;
      setStep('welcome');
      setLocalError(null);
      setSaving(false);
      setConnectAfterComplete(false);
      setRecordingVoice(false);
      setVoiceSaved(false);
    } else if (setupRequired && step === 'welcome') {
      setStep('consent');
    }
    signedIn.current = setupRequired;
  }, [setupRequired, step]);

  useEffect(() => {
    if (!setupRequired || step !== 'language') {
      return;
    }
    const current = ++operation.current;
    loadAvailableLanguages(omiBackend).then(value => {
      if (operation.current === current && value != null && value.length > 0) {
        setLanguages(value);
      }
    });
  }, [setupRequired, step]);

  const setupIndex = mobileSetupIndex(step);
  const busy = completingSetup || saving;
  const displayError = localError ?? error ?? null;
  const titleColor = desktop && styles.desktopTitle;
  const copyColor = desktop && styles.desktopCopy;
  const selectedLanguageName = useMemo(
    () => languages.find(item => item.code === language)?.name ?? language,
    [language, languages],
  );

  function goBack() {
    if (step === 'welcome' || signingIn) {
      return;
    }
    if (step === 'consent') {
      return;
    }
    const previous = previousMobileSetupStep(step);
    if (previous != null) {
      setLocalError(null);
      setStep(previous);
    }
  }

  async function advanceFrom(current: MobileSetupStep) {
    const next = nextMobileSetupStep(current);
    if (next == null) {
      return;
    }
    setLocalError(null);
    setStep(next);
  }

  async function persistLanguage() {
    const current = ++operation.current;
    setSaving(true);
    setLocalError(null);
    try {
      await savePrimaryLanguage(omiBackend, language);
      if (operation.current === current) {
        await advanceFrom('language');
      }
    } catch {
      if (operation.current === current) {
        setLocalError('Language could not be saved. Try again.');
      }
    } finally {
      if (operation.current === current) {
        setSaving(false);
      }
    }
  }

  async function persistSource() {
    const chosen =
      source === 'Other' ? otherSource.trim() : (source ?? '').trim();
    if (chosen.length === 0) {
      setLocalError('Choose how you found Omi to continue.');
      return;
    }
    const current = ++operation.current;
    setSaving(true);
    setLocalError(null);
    try {
      await saveAcquisitionSource(omiBackend, chosen);
      if (operation.current === current) {
        await advanceFrom('source');
      }
    } catch {
      if (operation.current === current) {
        setLocalError('Could not save how you found Omi. Try again.');
      }
    } finally {
      if (operation.current === current) {
        setSaving(false);
      }
    }
  }

  async function request(kind: PermissionKind) {
    if (pendingPermission !== null) {
      return;
    }
    const current = ++operation.current;
    setPendingPermission(kind);
    setLocalError(null);
    try {
      if (kind === 'bluetooth') {
        const granted = await requestBluetoothScanPermission();
        if (operation.current === current) {
          setPermissions(previous => ({
            ...previous,
            bluetooth: granted ? 'granted' : 'denied',
          }));
        }
        return;
      }
      if (omiNative?.requestPermissions == null) {
        if (operation.current === current) {
          setPermissions(previous => ({...previous, [kind]: 'denied'}));
        }
        return;
      }
      const result = await omiNative.requestPermissions();
      if (operation.current === current) {
        setPermissions(previous => ({
          ...previous,
          microphone: result.microphone,
          notifications: result.notifications,
        }));
      }
    } catch {
      if (operation.current === current) {
        setLocalError(
          'Permission request failed. You can continue and manage this later in Settings.',
        );
      }
    } finally {
      if (operation.current === current) {
        setPendingPermission(null);
      }
    }
  }

  function finish(connectDevice: boolean) {
    if (onCompleteSetup == null || busy) {
      return;
    }
    setConnectAfterComplete(connectDevice);
    onCompleteSetup(connectDevice);
  }

  async function enrollVoice() {
    if (recordingVoice) {
      return;
    }
    const current = ++operation.current;
    setRecordingVoice(true);
    setLocalError(null);
    try {
      const media =
        typeof navigator !== 'undefined' &&
        'mediaDevices' in navigator &&
        navigator.mediaDevices != null
          ? navigator.mediaDevices
          : null;
      const audioScope = globalThis as typeof globalThis & {
        AudioContext?: new (options?: {sampleRate: number}) => unknown;
      };
      const AudioContextCtor =
        typeof audioScope.AudioContext === 'function'
          ? (audioScope.AudioContext as NonNullable<
              typeof audioScope.AudioContext
            >)
          : null;
      const wav = await recordVoicePrintWav(
        media as Parameters<typeof recordVoicePrintWav>[0],
        AudioContextCtor as Parameters<typeof recordVoicePrintWav>[1],
        VOICE_PRINT_MIN_SECONDS,
      );
      await uploadVoicePrint(omiBackend?.uploadAudioFile, wav);
      if (operation.current === current) {
        setVoiceSaved(true);
        setStep('knowledge');
      }
    } catch (error) {
      if (operation.current === current) {
        setLocalError(
          error instanceof Error
            ? error.message
            : 'Voice print could not be saved. Try again or skip.',
        );
      }
    } finally {
      if (operation.current === current) {
        setRecordingVoice(false);
      }
    }
  }

  const action = (
    label: string,
    onPress: () => void,
    disabled = false,
    variant: 'primary' | 'ghost' = 'primary',
  ) => (
    <Button
      accessibilityLabel={label}
      disabled={disabled}
      onPress={onPress}
      size="large"
      variant={variant}
      labelStyle={desktop && styles.desktopButtonLabel}
      style={
        desktop && variant === 'primary' ? styles.desktopButton : undefined
      }>
      {label}
    </Button>
  );

  const permissionRow = (kind: PermissionKind, title: string) => {
    const granted = permissions[kind] === 'granted';
    const status =
      pendingPermission === kind
        ? 'Asking…'
        : granted
        ? 'Granted'
        : permissions[kind] === 'denied'
        ? 'Open Settings'
        : 'Allow';
    return (
      <PermissionRow
        key={kind}
        disabled={pendingPermission !== null}
        granted={granted}
        onPress={() => {
          request(kind);
        }}
        status={status}
        title={title}
      />
    );
  };

  return (
    <ScrollView
      accessibilityLabel="First-run onboarding"
      contentContainerStyle={styles.surface}
      keyboardShouldPersistTaps="handled">
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
        {setupIndex >= 0 ? (
          <Text style={[styles.meta, copyColor]}>
            Step {setupIndex + 1} of {mobileSetupSteps.length}
          </Text>
        ) : null}
        <Text
          accessibilityRole="header"
          style={[
            styles.title,
            titleColor,
            step === 'permissions' && styles.titleStart,
          ]}>
          {step === 'welcome'
            ? 'Welcome to Omi'
            : step === 'consent'
            ? 'Data & Privacy'
            : step === 'name'
            ? "What's your name?"
            : step === 'language'
            ? 'Select your primary language'
            : step === 'source'
            ? 'How did you find us?'
            : step === 'permissions'
            ? 'Grant permissions'
            : step === 'speech'
            ? 'Teach Omi your voice'
            : step === 'knowledge'
            ? 'Here is what I know about you'
            : 'You are all set!'}
        </Text>
        {step === 'welcome' ? (
          <>
            <Text style={[styles.copy, copyColor]}>
              Sign in to access your conversations and memories.
            </Text>
            {displayError == null ? null : (
              <Text
                accessibilityLabel={
                  displayError === SESSION_UNREACHABLE_COPY
                    ? 'Session unreachable'
                    : 'Sign-in error'
                }
                style={[
                  styles.error,
                  copyColor,
                  displayError === SESSION_UNREACHABLE_COPY &&
                    (desktop ? styles.desktopUnreachable : styles.unreachable),
                ]}>
                {displayError}
              </Text>
            )}
            {action(signingIn ? 'Signing in…' : 'Sign in', onSignIn, signingIn)}
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
        ) : null}
        {step === 'consent' ? (
          <>
            <Text style={[styles.copy, copyColor]}>
              By continuing, your conversations, recordings, and personal
              information will be securely stored on our servers. Your audio
              recordings and transcripts are processed by third-party AI
              services — Deepgram for transcription and OpenAI for analysis — to
              provide you with AI-powered insights and enable all app features.
            </Text>
            <Text style={[styles.copy, copyColor]}>
              Your data is protected and governed by our Privacy Policy and
              Terms of Service.
            </Text>
            <View style={styles.links}>
              <Button
                variant="ghost"
                accessibilityRole="link"
                onPress={() => openLink(PRIVACY_URL)}>
                Privacy Policy
              </Button>
              <Button
                variant="ghost"
                accessibilityRole="link"
                onPress={() => openLink(TERMS_URL)}>
                Terms of Service
              </Button>
            </View>
            {action('Agree & Continue', () => {
              setStep('name');
            })}
          </>
        ) : null}
        {step === 'name' ? (
          <>
            <Field
              accessibilityLabel="Enter your name"
              autoCapitalize="words"
              autoCorrect={false}
              label="Name"
              onChangeText={setName}
              placeholder="Enter your name"
              value={name}
            />
            {action('Continue', () => {
              if (name.trim().length === 0) {
                setLocalError('Enter your name to continue.');
                return;
              }
              setLocalError(null);
              setStep('language');
            })}
          </>
        ) : null}
        {step === 'language' ? (
          <>
            <Text style={[styles.copy, copyColor]}>
              Set your language for sharper transcriptions and a personalized
              experience. Selected: {selectedLanguageName}.
            </Text>
            <View style={styles.choices}>
              {languages.map(item => (
                <Button
                  key={item.code}
                  accessibilityLabel={item.name}
                  accessibilityState={{selected: language === item.code}}
                  onPress={() => setLanguage(item.code)}
                  variant={language === item.code ? 'primary' : 'ghost'}>
                  {item.name}
                </Button>
              ))}
            </View>
            {action(saving ? 'Saving…' : 'Continue', persistLanguage, saving)}
          </>
        ) : null}
        {step === 'source' ? (
          <>
            <View style={styles.choices}>
              {ACQUISITION_SOURCES.map(item => (
                <Button
                  key={item}
                  accessibilityLabel={item}
                  accessibilityState={{selected: source === item}}
                  onPress={() => setSource(item)}
                  variant={source === item ? 'primary' : 'ghost'}>
                  {item}
                </Button>
              ))}
            </View>
            {source === 'Other' ? (
              <Field
                accessibilityLabel="Please specify"
                label="Please specify"
                onChangeText={setOtherSource}
                placeholder="Please specify"
                value={otherSource}
              />
            ) : null}
            {action(saving ? 'Saving…' : 'Continue', persistSource, saving)}
          </>
        ) : null}
        {step === 'permissions' ? (
          <>
            <Text style={[styles.copy, styles.copyStart, copyColor]}>
              Click one when you’re ready. Nothing is asked until you do.
            </Text>
            {permissionRow(
              'notifications',
              'I would like to notify you when something needs you.',
            )}
            {permissionRow(
              'microphone',
              'I would like to use your microphone, so I can hear what you talk about.',
            )}
            {nativePhone
              ? permissionRow(
                  'bluetooth',
                  'I would like to find your Omi, so I can record from it.',
                )
              : null}
            {action("I'll do these later", () => {
              setStep('speech');
            })}
          </>
        ) : null}
        {step === 'speech' ? (
          <>
            <Text style={[styles.copy, copyColor]}>
              So Omi knows which voice is yours — talk for about 5 seconds about
              anything. A successful upload, not this screen, is enrollment.
            </Text>
            {voiceSaved ? (
              <Text style={[styles.copy, copyColor]}>Voice print saved.</Text>
            ) : null}
            {action(
              recordingVoice ? 'Listening…' : 'Start voice recording',
              enrollVoice,
              recordingVoice,
            )}
            {action(
              'Skip for now',
              () => {
                setStep('knowledge');
              },
              recordingVoice,
              'ghost',
            )}
          </>
        ) : null}
        {step === 'knowledge' ? (
          <>
            <Text style={[styles.copy, copyColor]}>
              This map updates as Omi learns from your conversations.
            </Text>
            {action('Continue', () => {
              setStep('complete');
            })}
          </>
        ) : null}
        {step === 'complete' ? (
          <>
            <Text style={[styles.copy, copyColor]}>
              Just use Omi in the background for 2 days and you'll start getting
              useful feedback after.
            </Text>
            {displayError == null || !setupRequired ? null : (
              <Text
                accessibilityLabel="Setup error"
                style={[
                  styles.error,
                  copyColor,
                  desktop ? styles.desktopUnreachable : styles.unreachable,
                ]}>
                {displayError}
              </Text>
            )}
            {!desktop && !browser
              ? action(
                  busy && connectAfterComplete
                    ? 'Saving…'
                    : 'Agree and connect Omi',
                  () => finish(true),
                  busy,
                )
              : null}
            {action(
              busy && !connectAfterComplete
                ? 'Saving…'
                : desktop || browser
                ? 'Start Using Omi'
                : 'Agree and continue without a device',
              () => finish(false),
              busy,
              desktop || browser ? 'primary' : 'ghost',
            )}
          </>
        ) : null}
        {displayError == null ||
        step === 'welcome' ||
        step === 'complete' ? null : (
          <Text
            accessibilityLabel="Setup error"
            style={[styles.error, copyColor]}>
            {displayError}
          </Text>
        )}
        {step !== 'welcome' &&
        step !== 'consent' &&
        step !== 'complete' &&
        !signingIn
          ? action('Back', goBack, busy, 'ghost')
          : null}
        {setupRequired && onSignOut
          ? action('Sign out', onSignOut, busy, 'ghost')
          : null}
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
  titleStart: {alignSelf: 'stretch', textAlign: 'left'},
  copy: {
    color: tokens.color.menuText,
    fontSize: 15,
    lineHeight: 22,
    textAlign: 'center',
  },
  copyStart: {alignSelf: 'stretch', textAlign: 'left'},
  error: {
    color: tokens.color.menuText,
    fontSize: 13,
    lineHeight: 18,
    textAlign: 'center',
  },
  unreachable: {
    color: uiColor.danger,
  },
  meta: {color: tokens.color.textMuted, fontSize: 12, textAlign: 'center'},
  choices: {
    alignSelf: 'stretch',
    gap: tokens.space.xs,
  },
  choice: {
    alignSelf: 'stretch',
    alignItems: 'center',
    borderColor: tokens.color.line,
    borderRadius: tokens.radius.md,
    borderWidth: tokens.border.width,
    gap: tokens.space.xs,
    padding: tokens.space.md,
  },
  choiceTitle: {
    color: tokens.color.text,
    fontSize: 16,
    fontWeight: '600',
  },
  desktopTitle: {color: desktopTokens.color.ink},
  desktopCopy: {color: desktopTokens.color.inkMuted},
  desktopUnreachable: {color: desktopTokens.color.red},
  desktopButton: {backgroundColor: desktopTokens.color.dark},
  desktopButtonLabel: {color: desktopTokens.color.white},
});
