import React, {useEffect, useMemo, useRef, useState} from 'react';
import {
  Animated,
  Easing,
  I18nManager,
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
import type {OmiAuthDesktopHandoff} from '../omiNativeTypes';
import {Button} from './Button';
import {useOmiStyles, useOmiTheme} from '../design/OmiTheme';
import {markInk} from '../mobile/MobileTheme';
import {OmiButton, OmiChip} from '../design/primitives';
import type {OmiTheme} from '../design/tokens';
import {MobileGroup, MobileRow} from '../mobile/MobileList';
import {Field} from './Field';
import {OmiAvatar} from './OmiAvatar';
import {PermissionRow} from './PermissionRow';
import {color as uiColor, tokens} from './tokens';

const DOTS_SIZE = 104;

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
  // Phones and the browser read the Omi theme (System / Light / Dark).
  const theme = useOmiTheme();
  const themed = useOmiStyles(createThemedStyles);
  const reduceMotion = useReduceMotion();
  const desktop = Platform.OS === 'macos';
  const browser = Platform.OS === 'web';
  const nativePhone = Platform.OS === 'ios' || Platform.OS === 'android';
  const opacity = useRef(new Animated.Value(1)).current;
  const scale = useRef(new Animated.Value(1)).current;
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
  const titleColor = desktop ? styles.desktopTitle : themed.title;
  const copyColor = desktop ? styles.desktopCopy : themed.copy;
  const selectedLanguageName = useMemo(
    () => languages.find(item => item.code === language)?.name ?? language,
    [language, languages],
  );
  // Compact defaults: the device language first, then the primary set —
  // never the whole catalog. Searching swaps in filtered matches.
  const suggestedLanguages = useMemo(() => {
    const base: AvailableLanguage[] =
      languages.length > 0
        ? languages
        : PRIMARY_LANGUAGES.map(item => ({code: item.code, name: item.name}));
    const rest = base.filter(item => item.code !== language);
    return [{code: language, name: selectedLanguageName}, ...rest].slice(0, 6);
  }, [language, languages, selectedLanguageName]);
  const matchingLanguages = useMemo(() => {
    const query = languageQuery.trim().toLowerCase();
    if (query.length === 0) {
      return null;
    }
    return languages
      .filter(
        item =>
          item.name.toLowerCase().includes(query) ||
          item.code.toLowerCase().includes(query),
      )
      .slice(0, 8);
  }, [languageQuery, languages]);

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

  const action = (
    label: string,
    onPress: () => void,
    disabled = false,
    variant: 'primary' | 'ghost' = 'primary',
  ) =>
    desktop ? (
      <Button
        accessibilityLabel={label}
        disabled={disabled}
        onPress={onPress}
        size="large"
        variant={variant}
        labelStyle={styles.desktopButtonLabel}
        style={variant === 'primary' ? styles.desktopButton : undefined}>
        {label}
      </Button>
    ) : (
      <OmiButton
        label={label}
        disabled={disabled}
        onPress={onPress}
        variant={variant === 'primary' ? 'primary' : 'plain'}
        style={[
          themed.action,
          (nativePhone || variant === 'primary') && styles.actionStretch,
        ]}
      />
    );

  const fieldTheme = {
    containerStyle: themed.field,
    style: themed.fieldInput,
    labelStyle: themed.fieldLabel,
    placeholderTextColor: theme.color.inkTertiary,
    selectionColor: theme.color.ink,
    keyboardAppearance: theme.scheme,
  };

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
    if (!desktop) {
      return (
        <MobileRow
          key={kind}
          accessibilityLabel={[title, description, status]
            .map(text => text.replace(/[.!?]$/, ''))
            .join('. ')}
          accessibilityState={{
            disabled:
              pendingPermission !== null ||
              permissions[kind] === 'unsupported' ||
              granted,
            busy: status === 'Asking…',
          }}
          disabled={
            pendingPermission !== null ||
            permissions[kind] === 'unsupported' ||
            granted
          }
          onPress={() => {
            request(kind);
          }}
          leading={
            <View style={[themed.permission, granted && themed.granted]}>
              {granted ? <Text style={themed.grantedCheck}>✓</Text> : null}
            </View>
          }
          title={title}
          subtitle={description}
          accessory={<Text style={themed.status}>{status}</Text>}
        />
      );
    }
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
      contentContainerStyle={[styles.surface, !desktop && themed.surface]}
      style={!desktop && themed.canvas}
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
            inkColor={desktop ? desktopTokens.color.ink : markInk(theme)}
          />
        </Animated.View>
        {setupIndex >= 0 ? (
          <Text style={[styles.meta, desktop ? copyColor : themed.meta]}>
            Step {setupIndex + 1} of {itinerary.length}
          </Text>
        ) : null}
        <Text accessibilityRole="header" style={[styles.title, titleColor]}>
          {step === 'welcome'
            ? 'Welcome to Omi'
            : step === 'consent'
            ? 'Data & Privacy'
            : step === 'language'
            ? 'Select Your Primary Language'
            : step === 'source'
            ? 'How Did You Find Us?'
            : step === 'permissions'
            ? 'Grant Permissions'
            : step === 'speech'
            ? 'Teach Omi Your Voice'
            : 'You’re All Set'}
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
                    (desktop ? styles.desktopUnreachable : themed.danger),
                ]}>
                {displayError}
              </Text>
            )}
            {action(
              desktop
                ? signingIn
                  ? 'Signing in…'
                  : 'Sign in'
                : signingIn
                ? 'Signing In…'
                : 'Sign In',
              onSignIn,
              signingIn,
            )}
            {signingIn && onCancelSignIn ? (
              <Button
                accessibilityLabel="Cancel sign in"
                onPress={onCancelSignIn}
                labelStyle={desktop ? styles.desktopTitle : themed.link}
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
                labelStyle={!desktop && themed.link}
                onPress={() => openLink(PRIVACY_URL)}>
                Privacy Policy
              </Button>
              <Button
                variant="ghost"
                accessibilityRole="link"
                labelStyle={!desktop && themed.link}
                onPress={() => openLink(TERMS_URL)}>
                Terms of Service
              </Button>
            </View>
            {action('Agree & Continue', () => {
              void advanceFrom('consent');
            })}
          </>
        ) : null}
        {step === 'language' ? (
          <>
            <Text style={[styles.copy, copyColor]}>
              {language === initialLanguage
                ? `We set ${selectedLanguageName} from your device language. Continue, or search if that is not right.`
                : `Continue in ${selectedLanguageName}, or pick another language.`}
            </Text>
            <View style={styles.chips}>
              {(matchingLanguages ?? suggestedLanguages).map(item =>
                !desktop ? (
                  <OmiChip
                    key={item.code}
                    label={item.name}
                    selected={language === item.code}
                    onPress={() => setLanguage(item.code)}
                  />
                ) : (
                  <Button
                    key={item.code}
                    accessibilityLabel={item.name}
                    accessibilityState={{selected: language === item.code}}
                    onPress={() => setLanguage(item.code)}
                    variant={language === item.code ? 'primary' : 'ghost'}>
                    {item.name}
                  </Button>
                ),
              )}
            </View>
            <Field
              accessibilityLabel="Search languages"
              autoCapitalize="none"
              autoCorrect={false}
              label="Search languages"
              {...(desktop ? {} : fieldTheme)}
              onChangeText={setLanguageQuery}
              placeholder="Search languages"
              returnKeyType="search"
              value={languageQuery}
            />
            {matchingLanguages != null && matchingLanguages.length === 0 ? (
              <Text style={[styles.copy, copyColor]}>
                No language matches “{languageQuery.trim()}”.
              </Text>
            ) : null}
            {action(saving ? 'Saving…' : 'Continue', persistLanguage, saving)}
          </>
        ) : null}
        {step === 'source' ? (
          <>
            <View style={desktop ? styles.choices : styles.chips}>
              {ACQUISITION_SOURCES.map(item =>
                !desktop ? (
                  <OmiChip
                    key={item}
                    label={item}
                    selected={source === item}
                    onPress={() => setSource(item)}
                  />
                ) : (
                  <Button
                    key={item}
                    accessibilityLabel={item}
                    accessibilityState={{selected: source === item}}
                    onPress={() => setSource(item)}
                    variant={source === item ? 'primary' : 'ghost'}>
                    {item}
                  </Button>
                ),
              )}
            </View>
            {source === 'Other' ? (
              <Field
                accessibilityLabel="Please specify"
                autoCorrect={false}
                enablesReturnKeyAutomatically
                label="Please specify"
                {...(desktop ? {} : fieldTheme)}
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
            ) : null}
            {action(saving ? 'Saving…' : 'Continue', persistSource, saving)}
          </>
        ) : null}
        {step === 'permissions' ? (
          <>
            <Text style={[styles.copy, copyColor]}>
              {nativePhone
                ? 'Tap one when you’re ready. Nothing is asked until you do.'
                : 'Click one when you’re ready. Nothing is asked until you do.'}
            </Text>
            <PermissionGroup grouped={!desktop}>
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
            </PermissionGroup>
            {action(desktop ? "I'll do these later" : 'Not Now', () => {
              void advanceFrom('permissions');
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
              recordingVoice ? 'Listening…' : 'Start Voice Recording',
              enrollVoice,
              recordingVoice,
            )}
            {action(
              'Not Now',
              () => {
                setStep('complete');
              },
              recordingVoice,
              'ghost',
            )}
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
                  desktop ? styles.desktopUnreachable : themed.danger,
                ]}>
                {displayError}
              </Text>
            )}
            {!desktop && !browser
              ? action(
                  busy && connectAfterComplete ? 'Saving…' : 'Connect Your Omi',
                  () => finish(true),
                  busy,
                )
              : null}
            {action(
              busy && !connectAfterComplete
                ? 'Saving…'
                : desktop || browser
                ? 'Start Using Omi'
                : 'Continue Without a Device',
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
          ? action(desktop ? 'Sign out' : 'Sign Out', onSignOut, busy, 'ghost')
          : null}
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
    actionStretch: {alignSelf: 'stretch'},
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
    meta: {color: tokens.color.textMuted, fontSize: 12, textAlign: 'center'},
    choices: {
      alignSelf: 'stretch',
      gap: tokens.space.xs,
    },
    chips: {
      alignSelf: 'stretch',
      flexDirection: 'row',
      flexWrap: 'wrap',
      gap: tokens.space.xs,
      justifyContent: 'center',
    },
    desktopTitle: {color: desktopTokens.color.ink},
    desktopCopy: {color: desktopTokens.color.inkMuted},
    desktopUnreachable: {color: desktopTokens.color.red},
    desktopButton: {backgroundColor: desktopTokens.color.dark},
    desktopButtonLabel: {color: desktopTokens.color.white},
  });

function PermissionGroup({
  grouped,
  children,
}: {
  grouped: boolean;
  children: React.ReactNode;
}) {
  return grouped ? (
    <MobileGroup inset={52} style={groupStyles.stretch}>
      {children}
    </MobileGroup>
  ) : (
    <>{children}</>
  );
}

const groupStyles = StyleSheet.create({stretch: {alignSelf: 'stretch'}});

const createThemedStyles = (t: OmiTheme) => ({
  canvas: {backgroundColor: t.color.canvas},
  surface: {paddingHorizontal: t.layout.pageGutter.mobile + t.space.sm},
  title: {...t.type.display, color: t.color.ink},
  copy: {...t.type.subhead, color: t.color.inkSecondary},
  meta: {...t.type.footnote, color: t.color.inkTertiary},
  danger: {color: t.color.danger},
  link: {color: t.color.inkSecondary},
  action: {marginTop: t.space.xs},
  field: {
    backgroundColor: t.color.surface,
    borderColor: t.color.hairline,
    borderRadius: t.radius.pill,
    minHeight: t.size.control,
    paddingHorizontal: t.space.lg,
  },
  fieldInput: {...t.type.body, color: t.color.ink},
  fieldLabel: {
    ...t.type.footnote,
    fontWeight: '600' as const,
    color: t.color.inkSecondary,
  },
  permission: {
    width: 22,
    height: 22,
    borderRadius: 11,
    borderWidth: 1.5,
    borderColor: t.color.inkTertiary,
    alignItems: 'center' as const,
    justifyContent: 'center' as const,
  },
  granted: {backgroundColor: t.color.ink, borderColor: t.color.ink},
  grantedCheck: {
    color: t.color.onInk,
    fontSize: 12,
    fontWeight: '700' as const,
  },
  status: {...t.type.footnote, color: t.color.inkSecondary},
});
