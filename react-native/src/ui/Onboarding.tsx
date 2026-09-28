import React, {useEffect, useMemo, useRef, useState} from 'react';
import {
  Animated,
  Easing,
  I18nManager,
  Keyboard,
  Linking,
  NativeModules,
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
  mobileItinerary,
  mobileSetupIndex,
  nextMobileSetupStep,
  normalizeDeviceLanguage,
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
import {
  type DesktopTokens,
  useDesktopTheme,
  useDesktopStyleSheets,
} from '../desktop/DesktopTheme';
import {PostSetupConfetti} from '../desktop/PostSetupOverlay';
import type {OmiAuthDesktopHandoff} from '../omiNativeTypes';
import {Button} from './Button';
import {Field} from './Field';
import {MaterialIcon} from './MaterialIcon';
import {OmiAvatar} from './OmiAvatar';
import {PermissionRow} from './PermissionRow';
import {color as uiColor, tokens} from './tokens';

// Header logo: small top-left mark; the step content is the visual hero.
const DOTS_SIZE = 40;

/** Short progress captions shown under the segmented step line. */
const STEP_TITLES: Record<MobileOnboardingStep, string> = {
  welcome: 'Welcome',
  consent: 'Privacy',
  language: 'Language',
  source: 'About you',
  permissions: 'Permissions',
  speech: 'Voice',
  complete: 'Done',
};

/** Collects the OS locale string on each platform; '' when unavailable. */
function deviceLocaleSource(): string {
  try {
    if (Platform.OS === 'web') {
      return typeof navigator !== 'undefined' && navigator.language
        ? navigator.language
        : '';
    }
    const settings = (
      NativeModules.SettingsManager as
        | {settings?: Record<string, unknown>}
        | undefined
    )?.settings;
    const appleLanguages = settings?.AppleLanguages;
    const apple =
      Array.isArray(appleLanguages) && typeof appleLanguages[0] === 'string'
        ? appleLanguages[0]
        : typeof settings?.AppleLocale === 'string'
        ? (settings.AppleLocale as string)
        : '';
    const i18nLocale = (I18nManager as {localeIdentifier?: unknown})
      .localeIdentifier;
    const raw =
      Platform.OS === 'android'
        ? typeof i18nLocale === 'string'
          ? i18nLocale
          : ''
        : apple || (typeof i18nLocale === 'string' ? i18nLocale : '');
    return typeof raw === 'string' ? raw : '';
  } catch {
    return '';
  }
}

type PermissionKind = 'notifications' | 'microphone' | 'bluetooth';
type PermissionState = 'unknown' | 'granted' | 'denied' | 'unsupported';

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
  // Desktop-only: the desktop-auth handoff code surfaced while signing in.
  // Accepted here so the mobile and desktop surfaces stay prop-compatible;
  // the phone flow authenticates in-app and never shows a code.
  desktopHandoff: _desktopHandoff,
}: {
  error?: string | null;
  onSignIn: () => void;
  onCancelSignIn?: () => void;
  signingIn: boolean;
  setupRequired?: boolean;
  /** Desktop: onboarding finished before; show Welcome-back sign-in only. */
  returning?: boolean;
  completingSetup?: boolean;
  onCompleteSetup?: (connectDevice: boolean) => void;
  onSignOut?: () => void;
  desktopHandoff?: OmiAuthDesktopHandoff | null;
}) {
  const styles = useDesktopStyleSheets(createStyles);
  const {tokens: desktopTokens} = useDesktopTheme();
  const reduceMotion = useReduceMotion();
  const desktop = Platform.OS === 'macos';
  const browser = Platform.OS === 'web';
  const nativePhone = Platform.OS === 'ios' || Platform.OS === 'android';
  const opacity = useRef(new Animated.Value(1)).current;
  const scale = useRef(new Animated.Value(1)).current;
  // Step change: the new step's title + body rise in with a short fade.
  const stepOpacity = useRef(new Animated.Value(1)).current;
  const stepShift = useRef(new Animated.Value(0)).current;
  const stepAnimatedOnce = useRef(false);
  // The logo rides the progress line: it slides to the step's position.
  const logoX = useRef(new Animated.Value(0)).current;
  const [trackWidth, setTrackWidth] = useState(0);
  const logoPlaced = useRef(false);
  const [step, setStep] = useState<MobileOnboardingStep>(
    setupRequired ? 'consent' : 'welcome',
  );
  const [initialLanguage] = useState(() =>
    normalizeDeviceLanguage(deviceLocaleSource()),
  );
  const [language, setLanguage] = useState(initialLanguage);
  const [languageQuery, setLanguageQuery] = useState('');
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
  // Native phones have no getUserMedia: their setup skips the speech step,
  // and the step counter follows the same itinerary.
  const itinerary = useMemo(() => mobileItinerary(nativePhone), [nativePhone]);

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
    // Skip the very first paint — the dots intro already covers it.
    if (!stepAnimatedOnce.current) {
      stepAnimatedOnce.current = true;
      return;
    }
    if (reduceMotion) {
      stepOpacity.setValue(1);
      stepShift.setValue(0);
      return;
    }
    stepOpacity.setValue(0);
    stepShift.setValue(16);
    const transition = Animated.parallel([
      Animated.timing(stepOpacity, {
        duration: 320,
        easing: Easing.out(Easing.cubic),
        toValue: 1,
        useNativeDriver: false,
      }),
      Animated.timing(stepShift, {
        duration: 320,
        easing: Easing.out(Easing.cubic),
        toValue: 0,
        useNativeDriver: false,
      }),
    ]);
    transition.start();
    return () => transition.stop();
  }, [reduceMotion, step, stepOpacity, stepShift]);

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

  const setupIndex = mobileSetupIndex(step, itinerary);
  const busy = completingSetup || saving;
  const displayError = localError ?? error ?? null;
  const titleColor = desktop && styles.desktopTitle;
  const copyColor = desktop && styles.desktopCopy;
  const selectedLanguageName = useMemo(
    () => languages.find(item => item.code === language)?.name ?? language,
    [language, languages],
  );
  // Search-first autocomplete: nothing until the user types, then at most
  // five ranked matches as pills (exact → prefix → substring, catalog order
  // preserved within each rank). The device-derived selection is the default.
  const languageMatches = useMemo(() => {
    const query = languageQuery.trim().toLowerCase();
    if (query.length === 0) {
      return [];
    }
    const rank = (item: AvailableLanguage) => {
      const name = item.name.toLowerCase();
      const code = item.code.toLowerCase();
      if (name === query || code === query) {
        return 0;
      }
      if (name.startsWith(query) || code.startsWith(query)) {
        return 1;
      }
      return name.includes(query) || code.includes(query) ? 2 : 3;
    };
    return languages
      .map(item => ({item, rank: rank(item)}))
      .filter(entry => entry.rank < 3)
      .sort((a, b) => a.rank - b.rank)
      .slice(0, 5)
      .map(entry => entry.item);
  }, [languageQuery, languages]);

  // The logo slides along the progress line to the current step's slot.
  useEffect(() => {
    if (trackWidth <= DOTS_SIZE) {
      return;
    }
    const slots = itinerary.length;
    const fraction =
      setupIndex >= 0 ? (setupIndex + 0.5) / slots : 1 / (2 * slots);
    const target = Math.max(
      0,
      Math.min(fraction * trackWidth - DOTS_SIZE / 2, trackWidth - DOTS_SIZE),
    );
    if (reduceMotion || !logoPlaced.current) {
      // First placement and reduced motion snap; step changes travel.
      logoX.setValue(target);
      logoPlaced.current = true;
      return;
    }
    const travel = Animated.spring(logoX, {
      toValue: target,
      speed: 18,
      bounciness: 6,
      useNativeDriver: false,
    });
    travel.start();
    return () => travel.stop();
  }, [itinerary.length, logoX, reduceMotion, setupIndex, trackWidth]);

  function goBack() {
    if (step === 'welcome' || signingIn) {
      return;
    }
    if (step === 'consent') {
      return;
    }
    const previous = previousMobileSetupStep(step, itinerary);
    if (previous != null) {
      setLocalError(null);
      setStep(previous);
    }
  }

  async function advanceFrom(current: MobileSetupStep) {
    const next = nextMobileSetupStep(current, itinerary);
    if (next == null) {
      return;
    }
    setLocalError(null);
    setStep(next);
  }

  // Choosing a pill is a commit: take the language, clear the query, and
  // collapse the results back to the resting search-only state.
  function pickLanguage(code: string) {
    setLanguage(code);
    setLanguageQuery('');
    Keyboard.dismiss();
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
    // iOS/Android never re-prompt after a denial — the row's status says
    // "Open Settings", so that is exactly what a denied tap must do.
    if (permissions[kind] === 'denied') {
      Linking.openSettings().catch(() => undefined);
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
        setStep('complete');
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

  const ghost = (label: string, onPress: () => void, disabled = false) => (
    <Button
      accessibilityLabel={label}
      disabled={disabled}
      labelStyle={desktop && styles.desktopTitle}
      onPress={onPress}
      variant="ghost">
      {label}
    </Button>
  );

  // The anchored bottom bar carries each step's primary action (Continue and
  // friends); secondary choices stay in the step body as ghost buttons.
  const primary = (() => {
    switch (step) {
      case 'welcome':
        return {
          label: signingIn ? 'Signing in…' : 'Sign in',
          onPress: onSignIn,
          disabled: signingIn,
        };
      case 'consent':
        return {
          label: 'Agree & Continue',
          onPress: () => {
            void advanceFrom('consent');
          },
          disabled: false,
        };
      case 'language':
        return {
          label: saving ? 'Saving…' : 'Continue',
          onPress: () => {
            void persistLanguage();
          },
          disabled: saving,
        };
      case 'source':
        return {
          label: saving ? 'Saving…' : 'Continue',
          onPress: () => {
            void persistSource();
          },
          disabled: saving,
        };
      case 'permissions':
        return {
          label: "I'll do these later",
          onPress: () => {
            void advanceFrom('permissions');
          },
          disabled: false,
        };
      case 'speech':
        return {
          label: recordingVoice ? 'Listening…' : 'Start voice recording',
          onPress: () => {
            void enrollVoice();
          },
          disabled: recordingVoice,
        };
      default:
        return nativePhone
          ? {
              label:
                busy && connectAfterComplete ? 'Saving…' : 'Connect your Omi',
              onPress: () => {
                finish(true);
              },
              disabled: busy,
            }
          : {
              label: busy ? 'Saving…' : 'Start Using Omi',
              onPress: () => {
                finish(false);
              },
              disabled: busy,
            };
    }
  })();
  const canGoBack =
    step !== 'welcome' &&
    step !== 'consent' &&
    step !== 'complete' &&
    !signingIn;

  const permissionRow = (
    kind: PermissionKind,
    title: string,
    description: string,
  ) => {
    const granted = permissions[kind] === 'granted';
    const status =
      pendingPermission === kind
        ? 'Asking…'
        : granted
        ? 'Granted'
        : permissions[kind] === 'unsupported'
        ? 'Unavailable'
        : permissions[kind] === 'denied'
        ? 'Open Settings'
        : 'Allow';
    return (
      <PermissionRow
        key={kind}
        disabled={
          pendingPermission !== null ||
          permissions[kind] === 'unsupported' ||
          granted
        }
        granted={granted}
        onPress={() => {
          request(kind);
        }}
        status={status}
        title={title}
        description={description}
      />
    );
  };

  return (
    <ScrollView
      accessibilityLabel="First-run onboarding"
      contentContainerStyle={styles.surface}
      keyboardShouldPersistTaps="handled">
      <View style={styles.column}>
        <View accessibilityLabel="Onboarding header" style={styles.topBlock}>
          <View
            style={styles.progressTrack}
            onLayout={event => {
              setTrackWidth(event.nativeEvent.layout.width);
            }}>
            <View style={styles.progressRow}>
              {itinerary.map((_, index) => (
                <View
                  key={index}
                  style={[
                    styles.progressSegment,
                    index <= setupIndex && styles.progressSegmentFill,
                  ]}
                />
              ))}
            </View>
            <Animated.View
              accessibilityLabel="Omi"
              style={[
                styles.dots,
                {opacity, transform: [{scale}, {translateX: logoX}]},
              ]}>
              <OmiAvatar
                animate={
                  !reduceMotion && (step === 'welcome' || step === 'complete')
                }
                identity="omi"
                reduceMotion={reduceMotion}
                size={DOTS_SIZE}
                tone="ink"
                inkColor={desktop ? desktopTokens.color.ink : undefined}
              />
            </Animated.View>
          </View>
          <View
            style={[
              styles.captionRow,
              !(setupRequired && onSignOut) && styles.captionRowCenter,
            ]}>
            <Text
              accessibilityLabel={
                setupIndex >= 0
                  ? `Step ${setupIndex + 1} of ${itinerary.length}`
                  : undefined
              }
              accessibilityLiveRegion="polite"
              numberOfLines={1}
              style={[styles.progressCaption, copyColor]}>
              {setupIndex >= 0
                ? `${STEP_TITLES[step]} · Step ${setupIndex + 1} of ${
                    itinerary.length
                  }`
                : STEP_TITLES[step]}
            </Text>
            {setupRequired && onSignOut ? (
              <Button
                accessibilityLabel="Sign out"
                disabled={busy}
                labelStyle={desktop && styles.desktopTitle}
                onPress={onSignOut}
                size="compact"
                variant="ghost">
                Sign out
              </Button>
            ) : null}
          </View>
        </View>
        <Animated.View
          style={[
            styles.titleAnim,
            {opacity: stepOpacity, transform: [{translateY: stepShift}]},
          ]}>
          <Text accessibilityRole="header" style={[styles.title, titleColor]}>
            {step === 'welcome'
              ? 'Welcome to Omi'
              : step === 'consent'
              ? 'Data & Privacy'
              : step === 'language'
              ? 'Select your primary language'
              : step === 'source'
              ? 'How did you find us?'
              : step === 'permissions'
              ? 'Grant permissions'
              : step === 'speech'
              ? 'Teach Omi your voice'
              : 'You are all set!'}
          </Text>
        </Animated.View>
        <Animated.View
          style={[
            styles.stepAnim,
            {opacity: stepOpacity, transform: [{translateY: stepShift}]},
          ]}>
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
                      (desktop
                        ? styles.desktopUnreachable
                        : styles.unreachable),
                  ]}>
                  {displayError}
                </Text>
              )}
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
                services — Deepgram for transcription and OpenAI for analysis —
                to provide you with AI-powered insights and enable all app
                features.
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
            </>
          ) : null}
          {step === 'language' ? (
            <>
              <Text
                accessibilityLiveRegion="polite"
                style={[styles.copy, copyColor]}>
                {language === initialLanguage
                  ? `Using ${selectedLanguageName} from your device. Search to change it.`
                  : `Using ${selectedLanguageName}. Search to change it.`}
              </Text>
              <View style={styles.stretch}>
                <Field
                  accessibilityLabel="Search languages"
                  autoCapitalize="none"
                  autoCorrect={false}
                  label="Search languages"
                  onChangeText={setLanguageQuery}
                  onSubmitEditing={() => {
                    const first = languageMatches[0];
                    if (first != null) {
                      pickLanguage(first.code);
                    }
                  }}
                  placeholder="Type a language or code"
                  placeholderTextColor={tokens.color.textMuted}
                  returnKeyType="search"
                  value={languageQuery}
                />
              </View>
              <View style={styles.chips}>
                {languageMatches.map(item => (
                  <Button
                    key={item.code}
                    accessibilityLabel={item.name}
                    accessibilityState={{selected: language === item.code}}
                    hitSlop={{bottom: 4, top: 4}}
                    onPress={() => {
                      pickLanguage(item.code);
                    }}
                    style={styles.pill}
                    variant={language === item.code ? 'primary' : 'secondary'}>
                    {item.name}
                  </Button>
                ))}
              </View>
              {languageQuery.trim().length > 0 &&
              languageMatches.length === 0 ? (
                <Text
                  accessibilityLiveRegion="polite"
                  style={[styles.copy, copyColor]}>
                  No language matches “{languageQuery.trim()}”.
                </Text>
              ) : null}
              <View style={styles.selectedRow}>
                <Text style={[styles.selectedCaption, copyColor]}>
                  Selected
                </Text>
                <View
                  accessibilityLabel="Selected language"
                  style={[styles.selectedChip, desktop && styles.desktopChip]}>
                  <Text
                    style={[
                      styles.selectedChipLabel,
                      desktop && styles.desktopChipLabel,
                    ]}>
                    {selectedLanguageName}
                  </Text>
                </View>
              </View>
            </>
          ) : null}
          {step === 'source' ? (
            <>
              <View style={[styles.chips, styles.sourceChips]}>
                {ACQUISITION_SOURCES.map(item => (
                  <Button
                    key={item}
                    accessibilityLabel={item}
                    accessibilityState={{selected: source === item}}
                    hitSlop={{bottom: 4, top: 4}}
                    onPress={() => setSource(item)}
                    style={styles.pill}
                    variant={source === item ? 'primary' : 'secondary'}>
                    {item}
                  </Button>
                ))}
              </View>
              {source === 'Other' ? (
                <View style={styles.stretch}>
                  <Field
                    accessibilityLabel="Please specify"
                    autoCorrect={false}
                    enablesReturnKeyAutomatically
                    label="Please specify"
                    onChangeText={setOtherSource}
                    onSubmitEditing={() => {
                      if (otherSource.trim().length > 0) {
                        void persistSource();
                      }
                    }}
                    placeholder="Where did you hear about us?"
                    returnKeyType="done"
                    value={otherSource}
                  />
                </View>
              ) : null}
            </>
          ) : null}
          {step === 'permissions' ? (
            <>
              <Text style={[styles.copy, copyColor]}>
                {nativePhone
                  ? 'Tap one when you’re ready. Nothing is asked until you do.'
                  : 'Click one when you’re ready. Nothing is asked until you do.'}
              </Text>
              {permissionRow(
                'notifications',
                'Notifications',
                'Notify you when something needs you.',
              )}
              {permissionRow(
                'microphone',
                'Microphone',
                'Hear what you talk about, so Omi can help.',
              )}
              {nativePhone
                ? permissionRow(
                    'bluetooth',
                    'Bluetooth',
                    'Find your Omi, so it can record for you.',
                  )
                : null}
            </>
          ) : null}
          {step === 'speech' ? (
            <>
              <Text style={[styles.copy, copyColor]}>
                So Omi knows which voice is yours — talk for about 5 seconds
                about anything. A successful upload, not this screen, is
                enrollment.
              </Text>
              {voiceSaved ? (
                <Text style={[styles.copy, copyColor]}>Voice print saved.</Text>
              ) : null}
              {ghost(
                'Skip for now',
                () => {
                  setStep('complete');
                },
                recordingVoice,
              )}
            </>
          ) : null}
          {step === 'complete' ? (
            <>
              <PostSetupConfetti onDone={() => undefined} />
              <Text style={[styles.copy, copyColor]}>
                Just use Omi in the background for 2 days and you'll start
                getting useful feedback after.
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
                ? ghost(
                    busy ? 'Saving…' : 'Continue without a device',
                    () => {
                      finish(false);
                    },
                    busy,
                  )
                : null}
            </>
          ) : null}
        </Animated.View>
        {displayError == null ||
        step === 'welcome' ||
        step === 'complete' ? null : (
          <Text
            accessibilityLabel="Setup error"
            style={[styles.error, copyColor]}>
            {displayError}
          </Text>
        )}
        <View style={styles.bar}>
          {canGoBack ? (
            <Button
              accessibilityLabel="Back"
              disabled={busy}
              onPress={goBack}
              size="icon"
              variant="secondary"
              style={styles.backCircle}>
              <MaterialIcon
                name="arrow_back"
                size={20}
                color={desktop ? desktopTokens.color.ink : tokens.color.text}
              />
            </Button>
          ) : null}
          <Button
            accessibilityLabel={primary.label}
            disabled={primary.disabled}
            labelStyle={desktop && styles.desktopButtonLabel}
            onPress={primary.onPress}
            size="large"
            style={[styles.barPrimary, desktop && styles.desktopButton]}>
            {primary.label}
          </Button>
        </View>
      </View>
    </ScrollView>
  );
}

const createStyles = (desktopTokens: DesktopTokens) =>
  StyleSheet.create({
    surface: {
      alignItems: 'center',
      alignSelf: 'stretch',
      flexGrow: 1,
      justifyContent: 'flex-start',
      paddingHorizontal: tokens.space.xxl,
      paddingVertical: tokens.space.xl,
    },
    links: {flexDirection: 'row', flexWrap: 'wrap', justifyContent: 'center'},
    column: {
      alignItems: 'center',
      flexGrow: 1,
      gap: tokens.space.sm,
      maxWidth: tokens.size.content,
      width: '100%',
    },
    topBlock: {
      alignSelf: 'stretch',
      gap: tokens.space.xs,
    },
    progressTrack: {
      alignSelf: 'stretch',
      height: DOTS_SIZE,
      justifyContent: 'center',
    },
    captionRow: {
      alignItems: 'center',
      alignSelf: 'stretch',
      flexDirection: 'row',
      gap: tokens.space.sm,
      justifyContent: 'space-between',
    },
    captionRowCenter: {justifyContent: 'center'},
    dots: {
      left: 0,
      position: 'absolute',
      top: 0,
    },
    titleAnim: {
      alignItems: 'center',
      alignSelf: 'stretch',
    },
    stepAnim: {
      alignItems: 'center',
      alignSelf: 'stretch',
      flex: tokens.layout.grow,
      gap: tokens.space.sm,
      justifyContent: 'center',
    },
    progressRow: {
      alignSelf: 'stretch',
      flexDirection: 'row',
      gap: tokens.space.xs,
      height: tokens.space.xs,
    },
    progressCaption: {
      color: tokens.color.menuText,
      fontSize: 13,
      letterSpacing: 0.2,
      lineHeight: 16,
    },
    progressSegment: {
      backgroundColor: tokens.color.lineStrong,
      borderRadius: tokens.radius.pill,
      flex: tokens.layout.grow,
    },
    progressSegmentFill: {backgroundColor: tokens.color.text},
    bar: {
      alignItems: 'center',
      alignSelf: 'stretch',
      flexDirection: 'row',
      gap: tokens.space.md,
    },
    barPrimary: {flex: tokens.layout.grow},
    backCircle: {borderRadius: tokens.radius.pill},
    selectedRow: {
      alignItems: 'center',
      alignSelf: 'stretch',
      flexDirection: 'row',
      flexWrap: 'wrap',
      gap: tokens.space.sm,
      justifyContent: 'center',
    },
    selectedCaption: {
      color: tokens.color.menuText,
      fontSize: 13,
      lineHeight: 18,
    },
    selectedChip: {
      backgroundColor: tokens.color.primary,
      borderRadius: tokens.radius.pill,
      paddingHorizontal: tokens.space.lg,
      paddingVertical: tokens.space.xs,
    },
    selectedChipLabel: {
      color: tokens.color.textInverse,
      ...tokens.type.label,
    },
    title: {
      color: tokens.color.text,
      fontSize: 32,
      fontWeight: '700',
      letterSpacing: -1,
      lineHeight: 38,
      marginBottom: tokens.space.xs,
      textAlign: 'center',
    },
    stretch: {alignSelf: 'stretch'},
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
    unreachable: {
      color: uiColor.danger,
    },
    chips: {
      alignSelf: 'stretch',
      flexDirection: 'row',
      flexWrap: 'wrap',
      gap: tokens.space.sm,
      justifyContent: 'center',
    },
    sourceChips: {justifyContent: 'flex-start'},
    pill: {
      borderRadius: tokens.radius.pill,
      paddingHorizontal: tokens.space.lg,
    },
    desktopTitle: {color: desktopTokens.color.ink},
    desktopCopy: {color: desktopTokens.color.inkMuted},
    desktopUnreachable: {color: desktopTokens.color.red},
    desktopButton: {backgroundColor: desktopTokens.color.dark},
    desktopButtonLabel: {color: desktopTokens.color.white},
    desktopChip: {backgroundColor: desktopTokens.color.dark},
    desktopChipLabel: {color: desktopTokens.color.white},
  });
