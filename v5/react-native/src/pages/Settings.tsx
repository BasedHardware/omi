import React, {useCallback, useEffect, useRef, useState} from 'react';
import {Linking, Platform, ScrollView, Text, View} from 'react-native';
import {
  cloudSessionUnavailableCopy,
  loadAccountSettings,
  loadServiceSettings,
  optInTrainingData,
  setPrivateCloudSync,
  setStoreRecordingPermission,
  type AccountSettingsSnapshot,
  type ServiceSettingsSnapshot,
} from '../desktopCloudClient';
import {
  desktopBackendConfigurationCopy,
  desktopBackendServiceCopy,
  desktopBackendUnauthorizedCopy,
  desktopReadErrorCopy,
} from '../desktopReadClient';
import {omiAuth, omiBackend} from '../omiNative';
import {MaterialIcon, type MaterialIconName} from '../ui/MaterialIcon';
import {useOmiStyles, useOmiTheme} from '../design/OmiTheme';
import {OmiButton, OmiPageState} from '../design/primitives';
import type {OmiTheme} from '../design/tokens';
import {
  MobileGroup,
  MobileInlineState,
  MobileRow,
  MobileSectionHeader,
  MobileSegmented,
} from '../mobile/MobileList';
import {
  mobileAppearanceOptions,
  useMobileAppearanceControl,
} from '../mobile/MobileTheme';
import {parseSoftwarePlane, type SoftwarePlane} from '../v5BackendOrigin';
import {
  loadDesktopPreferences,
  setDesktopPreference,
  type LiveVoiceProvider,
} from '../desktopSettingsClient';

const sections = ['Account', 'Privacy', 'Developer'] as const;
type SettingsSection = (typeof sections)[number];

function SettingRow({
  action,
  actionLabel,
  actionText,
  busy = false,
  copy,
  title,
}: {
  action?: () => void;
  /** Screen-reader name of the action; it contains the visible text. */
  actionLabel?: string;
  /** Short Title Case button text (defaults to the action label). */
  actionText?: string;
  busy?: boolean;
  copy: string;
  title: string;
}) {
  const local = useOmiStyles(createStyles);
  return (
    <MobileRow
      title={title}
      subtitle={copy}
      trailing={
        action !== undefined && actionLabel !== undefined ? (
          <View style={local.rowAction}>
            <OmiButton
              accessibilityLabel={actionLabel}
              busy={busy}
              compact
              label={actionText ?? actionLabel}
              onPress={action}
            />
          </View>
        ) : undefined
      }
    />
  );
}

/** A row that opens something elsewhere (the system Settings, a web page). */
function LinkRow({
  accessibilityLabel,
  icon,
  onPress,
  subtitle,
  title,
}: {
  accessibilityLabel: string;
  icon: MaterialIconName;
  onPress: () => void;
  subtitle?: string;
  title: string;
}) {
  const theme = useOmiTheme();
  return (
    <MobileRow
      accessibilityLabel={accessibilityLabel}
      onPress={onPress}
      title={title}
      subtitle={subtitle}
      accessory={
        <MaterialIcon
          name={icon}
          color={theme.color.inkTertiary}
          size={theme.size.iconSmall}
        />
      }
    />
  );
}

function ChoiceRow<T extends string>({
  busy,
  copy,
  onSelect,
  options,
  optionLabel,
  title,
  value,
}: {
  busy: boolean;
  copy: string;
  onSelect: (value: T) => void;
  options: ReadonlyArray<{value: T; label: string}>;
  optionLabel: (option: {value: T; label: string}) => string;
  title: string;
  value: T;
}) {
  const local = useOmiStyles(createStyles);
  return (
    <View>
      <MobileRow title={title} subtitle={copy} />
      <View style={local.choice}>
        <MobileSegmented
          role="button"
          disabled={busy}
          options={options}
          optionLabel={optionLabel}
          value={value}
          onChange={onSelect}
        />
      </View>
    </View>
  );
}

function BackendPlaneRow({
  busy,
  onSelect,
  plane,
  stampedOrigin,
}: {
  busy: boolean;
  onSelect: (plane: SoftwarePlane) => void;
  plane: SoftwarePlane;
  stampedOrigin: string | null;
}) {
  const copy =
    plane === 'new'
      ? stampedOrigin != null
        ? 'New sends v5 chat, capture, conversations, memories, and tasks to the stamped origin. Account, apps, privacy, and native Settings still use production api.omi.me.'
        : 'New is selected, but no valid stamped v5 origin is configured.'
      : 'Old backend uses your existing Omi account and api.omi.me.';
  return (
    <ChoiceRow<SoftwarePlane>
      busy={busy}
      copy={copy}
      onSelect={onSelect}
      options={[
        {value: 'old', label: 'Old Backend'},
        {value: 'new', label: 'New Backend'},
      ]}
      optionLabel={option =>
        option.value === 'new' ? 'Use New backend' : 'Use Old backend'
      }
      title="Backend"
      value={plane}
    />
  );
}

function LiveVoiceRow({
  busy,
  onSelect,
  provider,
}: {
  busy: boolean;
  onSelect: (provider: LiveVoiceProvider) => void;
  provider: LiveVoiceProvider;
}) {
  const copy =
    provider === 'gemini_live'
      ? 'Uses models/gemini-3.1-flash-live-preview over Gemini Live. Fails closed if GEMINI_API_KEY is missing on the server.'
      : 'Uses gpt-live-1 over OpenAI WebRTC. Fails closed if OPENAI_API_KEY is missing on the server.';
  return (
    <ChoiceRow<LiveVoiceProvider>
      busy={busy}
      copy={copy}
      onSelect={onSelect}
      options={[
        {value: 'gpt_live', label: 'GPT Live 1'},
        {value: 'gemini_live', label: 'Gemini Live'},
      ]}
      optionLabel={option => `Use ${option.label}`}
      title="Live voice"
      value={provider}
    />
  );
}

export function SettingsPage({
  onSignIn,
  onSignOut,
  onOpenApps,
  onWorkspaceReload,
  chatBusy = false,
  signingIn = false,
}: {
  onSignIn?: () => Promise<void>;
  onSignOut?: () => Promise<void>;
  onOpenApps?: () => void;
  onWorkspaceReload?: () => void;
  chatBusy?: boolean;
  signingIn?: boolean;
}) {
  const browser = Platform.OS === 'web';
  const theme = useOmiTheme();
  const local = useOmiStyles(createStyles);
  const appearance = useMobileAppearanceControl();
  const [serviceSettings, setServiceSettings] =
    useState<ServiceSettingsSnapshot | null>(null);
  const [section, setSection] = useState<SettingsSection>('Account');
  const [phase, setPhase] = useState<
    'loading' | 'signed-out' | 'ready' | 'error'
  >('loading');
  const [error, setError] = useState<string | null>(null);
  const [snapshot, setSnapshot] = useState<AccountSettingsSnapshot | null>(
    null,
  );
  const [pending, setPending] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const [softwarePlane, setSoftwarePlane] = useState<SoftwarePlane | null>(
    null,
  );
  const [stampedV5Origin, setStampedV5Origin] = useState<string | null>(null);
  const [liveVoiceProvider, setLiveVoiceProvider] =
    useState<LiveVoiceProvider>('gpt_live');
  const loadGeneration = useRef(0);
  const mounted = useRef(false);

  const reloadSoftwarePlane = useCallback(async () => {
    const backend = omiBackend;
    try {
      const prefs = await loadDesktopPreferences();
      setLiveVoiceProvider(prefs.liveVoiceProvider);
    } catch {
      setLiveVoiceProvider('gpt_live');
    }
    if (
      backend?.getSoftwarePlane === undefined ||
      backend.setSoftwarePlane === undefined
    ) {
      setSoftwarePlane(null);
      setStampedV5Origin(null);
      return;
    }
    const [plane, origin] = await Promise.all([
      backend.getSoftwarePlane(),
      backend.stampedV5BackendOrigin === undefined
        ? Promise.resolve(null)
        : backend.stampedV5BackendOrigin(),
    ]);
    setSoftwarePlane(parseSoftwarePlane(plane));
    setStampedV5Origin(
      typeof origin === 'string' && origin.length > 0 ? origin : null,
    );
  }, []);

  const reload = useCallback(async () => {
    if (!mounted.current) {
      return;
    }
    const generation = ++loadGeneration.current;
    const current = () =>
      mounted.current && generation === loadGeneration.current;
    setPhase('loading');
    const backend = omiBackend;
    const auth = omiAuth;
    setActionError(null);
    if (backend === undefined || backend === null) {
      setSnapshot(null);
      setError(cloudSessionUnavailableCopy(backend));
      setPhase('error');
      return;
    }
    if (browser) {
      try {
        const settings = await loadServiceSettings(backend);
        if (!current()) {
          return;
        }
        setServiceSettings(settings);
        setError(null);
        setPhase('ready');
      } catch (reason) {
        if (!current()) {
          return;
        }
        setServiceSettings(null);
        const code =
          reason !== null && typeof reason === 'object' && 'code' in reason
            ? String((reason as {code?: unknown}).code)
            : '';
        setError(
          code === 'service_unavailable'
            ? 'Account profile is unavailable until an owner-backed producer exists. Retry later.'
            : null,
        );
        setPhase('error');
      }
      return;
    }
    if (auth !== undefined && auth !== null) {
      let hasSession: boolean;
      try {
        hasSession = await auth.hasCloudSession();
        if (!current()) {
          return;
        }
      } catch {
        if (!current()) {
          return;
        }
        // A probe that cannot settle (session refresh transport failed) must
        // stay retryable instead of stranding the page on Loading forever.
        setSnapshot(null);
        setError(desktopBackendServiceCopy);
        setPhase('error');
        return;
      }
      if (!hasSession) {
        setSnapshot(null);
        setError(desktopBackendUnauthorizedCopy);
        setPhase('signed-out');
        return;
      }
    }
    try {
      const account = await loadAccountSettings(backend);
      if (!current()) {
        return;
      }
      setSnapshot(account);
      setError(null);
      setPhase('ready');
    } catch (reason) {
      if (!current()) {
        return;
      }
      setSnapshot(null);
      setError(desktopReadErrorCopy(reason));
      setPhase('error');
    }
  }, [browser]);

  useEffect(() => {
    mounted.current = true;
    reload().catch(() => undefined);
    reloadSoftwarePlane().catch(() => undefined);
    return () => {
      mounted.current = false;
    };
  }, [reload, reloadSoftwarePlane]);

  const selectSoftwarePlane = async (plane: SoftwarePlane) => {
    const backend = omiBackend;
    if (
      backend?.setSoftwarePlane === undefined ||
      pending !== null ||
      chatBusy
    ) {
      return;
    }
    setPending('software-plane');
    setActionError(null);
    try {
      const next = parseSoftwarePlane(await backend.setSoftwarePlane(plane));
      setSoftwarePlane(next);
      onWorkspaceReload?.();
      await reload();
    } catch (reason) {
      setActionError(desktopReadErrorCopy(reason));
    } finally {
      setPending(null);
    }
  };

  const selectLiveVoiceProvider = async (provider: LiveVoiceProvider) => {
    if (pending !== null) {
      return;
    }
    setPending('live-voice');
    setActionError(null);
    try {
      const next = await setDesktopPreference('liveVoiceProvider', provider);
      setLiveVoiceProvider(next.liveVoiceProvider);
    } catch (reason) {
      setActionError(desktopReadErrorCopy(reason));
    } finally {
      setPending(null);
    }
  };

  const runAction = async (id: string, action: () => Promise<void>) => {
    if (pending !== null) {
      return;
    }
    setPending(id);
    setActionError(null);
    try {
      await action();
      await reload();
    } catch (reason) {
      setActionError(desktopReadErrorCopy(reason));
    } finally {
      setPending(null);
    }
  };

  const signIn = async () => {
    if (onSignIn === undefined) {
      return;
    }
    await onSignIn();
    await reload();
  };

  const signOut = async () => {
    if (onSignOut !== undefined) {
      await onSignOut();
      return;
    }
    const auth = omiAuth;
    if (auth === undefined || auth === null) {
      throw new Error('Sign out is not available in this app session.');
    }
    const result = await auth.signOut();
    if (!result.signedOut) {
      throw new Error('Could not clear this app session.');
    }
  };

  const account =
    snapshot === null ? null : (
      <MobileGroup>
        {snapshot.profile === null ? (
          <MobileInlineState
            label={snapshot.profileError ?? 'Account profile is unavailable.'}
          />
        ) : (
          [
            <SettingRow
              key="name"
              copy={snapshot.profile.name ?? 'Name not set on this account.'}
              title="Name"
            />,
            <SettingRow
              key="email"
              copy={snapshot.profile.email ?? 'Email not set on this account.'}
              title="Email"
            />,
            <SettingRow
              key="uid"
              copy={snapshot.profile.uid}
              title="Account ID"
            />,
            snapshot.profile.company !== null && (
              <SettingRow
                key="company"
                copy={snapshot.profile.company}
                title="Company"
              />
            ),
            snapshot.profile.job !== null && (
              <SettingRow key="job" copy={snapshot.profile.job} title="Job" />
            ),
            snapshot.profile.dataProtectionLevel !== null && (
              <SettingRow
                key="protection"
                copy={snapshot.profile.dataProtectionLevel}
                title="Data Protection"
              />
            ),
          ]
        )}
        {snapshot.subscription === null ? (
          <MobileInlineState
            label={snapshot.subscriptionError ?? 'Plan is unavailable.'}
          />
        ) : (
          <SettingRow
            copy={[
              snapshot.subscription.plan,
              snapshot.subscription.status,
              snapshot.subscription.transcriptionSecondsUsed !== null &&
              snapshot.subscription.transcriptionSecondsLimit !== null
                ? `${snapshot.subscription.transcriptionSecondsUsed} / ${snapshot.subscription.transcriptionSecondsLimit} transcribed seconds`
                : null,
            ]
              .filter(item => item !== null)
              .join(' · ')}
            title="Plan"
          />
        )}
        {(onSignOut !== undefined ||
          (omiAuth !== undefined && omiAuth !== null)) && (
          <SettingRow
            action={() => {
              runAction('sign-out', signOut).catch(() => undefined);
            }}
            actionLabel="Sign out"
            actionText="Sign Out"
            busy={pending === 'sign-out'}
            copy="Leave this app's cloud session. Your Omi account stays in the cloud."
            title="Sign Out"
          />
        )}
      </MobileGroup>
    );

  const privacy =
    snapshot === null ? null : (
      <MobileGroup>
        {snapshot.storeRecordingPermission === null ? (
          <MobileInlineState
            label={
              snapshot.storeRecordingError ??
              'Recording storage permission is unavailable.'
            }
          />
        ) : (
          <SettingRow
            action={() => {
              const backend = omiBackend;
              if (backend === undefined || backend === null) {
                return;
              }
              runAction('recording', () =>
                setStoreRecordingPermission(
                  backend,
                  !snapshot.storeRecordingPermission,
                ),
              ).catch(() => undefined);
            }}
            actionLabel={
              snapshot.storeRecordingPermission
                ? 'Turn off recording storage'
                : 'Turn on recording storage'
            }
            actionText={
              snapshot.storeRecordingPermission ? 'Turn Off' : 'Turn On'
            }
            busy={pending === 'recording'}
            copy={
              snapshot.storeRecordingPermission
                ? 'Cloud recording storage is on.'
                : 'Cloud recording storage is off.'
            }
            title="Recording Storage"
          />
        )}
        {snapshot.trainingOptedIn === null ? (
          <MobileInlineState
            label={snapshot.trainingError ?? 'Training opt-in is unavailable.'}
          />
        ) : (
          <SettingRow
            action={
              snapshot.trainingOptedIn
                ? undefined
                : () => {
                    const backend = omiBackend;
                    if (backend === undefined || backend === null) {
                      return;
                    }
                    runAction('training', () =>
                      optInTrainingData(backend),
                    ).catch(() => undefined);
                  }
            }
            actionLabel={snapshot.trainingOptedIn ? undefined : 'Opt in'}
            actionText="Opt In"
            busy={pending === 'training'}
            copy={
              snapshot.trainingOptedIn
                ? 'This account has opted in to training data. The API does not expose an opt-out from here.'
                : 'This account has not opted in to training data.'
            }
            title="Training Data"
          />
        )}
        {snapshot.privateCloudSync === null ? (
          <MobileInlineState
            label={
              snapshot.privateCloudSyncError ??
              'Private cloud sync is unavailable.'
            }
          />
        ) : (
          <SettingRow
            action={() => {
              const backend = omiBackend;
              if (backend === undefined || backend === null) {
                return;
              }
              runAction('sync', () =>
                setPrivateCloudSync(backend, !snapshot.privateCloudSync),
              ).catch(() => undefined);
            }}
            actionLabel={
              snapshot.privateCloudSync
                ? 'Turn off private cloud sync'
                : 'Turn on private cloud sync'
            }
            actionText={snapshot.privateCloudSync ? 'Turn Off' : 'Turn On'}
            busy={pending === 'sync'}
            copy={
              snapshot.privateCloudSync
                ? 'Private cloud sync is on.'
                : 'Private cloud sync is off.'
            }
            title="Private Cloud Sync"
          />
        )}
      </MobileGroup>
    );

  const developer =
    snapshot === null ? null : (
      <MobileGroup>
        {snapshot.webhooks === null ? (
          <MobileInlineState
            label={
              snapshot.webhooksError ??
              'Developer webhook status is unavailable.'
            }
          />
        ) : snapshot.webhooks.length === 0 ? (
          <MobileInlineState label="No developer webhooks were returned." />
        ) : (
          snapshot.webhooks.map(webhook => (
            <SettingRow
              copy={[
                webhook.enabled === null
                  ? 'Status unknown'
                  : webhook.enabled
                  ? 'Enabled'
                  : 'Disabled',
                webhook.url,
              ]
                .filter(item => item !== null)
                .join(' · ')}
              key={webhook.type}
              title={webhook.type}
            />
          ))
        )}
      </MobileGroup>
    );

  const browserAccount =
    serviceSettings === null ? null : (
      <MobileGroup>
        <SettingRow
          title="Connection Identity"
          copy={
            serviceSettings.identity === null
              ? 'Identity unavailable for this connection.'
              : [
                  serviceSettings.identity.displayName,
                  serviceSettings.identity.email,
                ]
                  .filter(Boolean)
                  .join(' · ') || 'Identity unavailable for this connection.'
          }
        />
        {serviceSettings.entitlement !== null &&
        ['chat', 'transcription_seconds'].includes(
          serviceSettings.entitlement.limitKey,
        ) ? (
          <SettingRow
            title={
              serviceSettings.entitlement.limitKey === 'chat'
                ? 'Chat Usage'
                : 'Transcription Usage'
            }
            copy={`${serviceSettings.entitlement.used}${
              serviceSettings.entitlement.limit === null
                ? ''
                : ` of ${serviceSettings.entitlement.limit}`
            } ${
              serviceSettings.entitlement.limitKey === 'chat'
                ? 'requests'
                : 'seconds'
            } used`}
          />
        ) : (
          <SettingRow
            title="Usage"
            copy="Usage allowance is unavailable for this connection."
          />
        )}
      </MobileGroup>
    );

  const sectionOptions = sections
    .filter(label => !browser || label !== 'Developer')
    .map(label => ({value: label, label}));

  return (
    <ScrollView contentContainerStyle={local.page}>
      {appearance !== null && (
        <View style={local.block}>
          <MobileSectionHeader title="Appearance" />
          <MobileSegmented
            accessibilityLabel="Appearance"
            options={mobileAppearanceOptions}
            optionLabel={option => `${option.label} appearance`}
            value={appearance.appearance}
            onChange={appearance.setAppearance}
          />
        </View>
      )}
      {onOpenApps && (
        <MobileGroup>
          <MobileRow
            accessibilityLabel="Open apps"
            onPress={onOpenApps}
            leading={
              <MaterialIcon
                name="extension"
                color={theme.color.inkSecondary}
                size={theme.size.icon}
              />
            }
            title="Apps"
            subtitle="Manage your apps and connected services."
            accessory={
              <MaterialIcon
                name="chevron_right"
                color={theme.color.inkTertiary}
                size={theme.size.icon}
              />
            }
          />
        </MobileGroup>
      )}
      <View style={local.block}>
        <MobileSegmented
          accessibilityLabel="Settings sections"
          options={sectionOptions}
          optionLabel={option => `${option.label} settings`}
          value={section}
          onChange={setSection}
        />
      </View>
      {!browser && section === 'Developer' && (
        <View style={local.block}>
          <MobileSectionHeader title="AI & Connection" />
          <MobileGroup>
            {softwarePlane !== null && (
              <BackendPlaneRow
                busy={pending === 'software-plane' || chatBusy}
                onSelect={plane => {
                  selectSoftwarePlane(plane).catch(() => undefined);
                }}
                plane={softwarePlane}
                stampedOrigin={stampedV5Origin}
              />
            )}
            <LiveVoiceRow
              busy={pending === 'live-voice'}
              onSelect={provider => {
                selectLiveVoiceProvider(provider).catch(() => undefined);
              }}
              provider={liveVoiceProvider}
            />
          </MobileGroup>
        </View>
      )}
      <View style={local.block}>
        {phase === 'loading' && snapshot === null ? (
          <OmiPageState kind="loading" label="Loading account…" />
        ) : phase === 'signed-out' ? (
          <View style={local.state}>
            <OmiPageState
              kind="empty"
              icon="person"
              title="Signed Out"
              message={error ?? desktopBackendUnauthorizedCopy}
            />
            {onSignIn !== undefined && (
              <OmiButton
                busy={signingIn}
                label="Sign In"
                variant="primary"
                onPress={() => {
                  signIn().catch(() => undefined);
                }}
              />
            )}
          </View>
        ) : phase === 'error' ? (
          <View accessibilityRole="alert">
            <OmiPageState
              kind="error"
              title="Couldn’t Load Settings"
              message={error ?? undefined}
              onRetry={
                error === desktopBackendConfigurationCopy
                  ? undefined
                  : () => {
                      reload().catch(() => undefined);
                    }
              }
            />
          </View>
        ) : browser ? (
          section === 'Account' && serviceSettings ? (
            browserAccount
          ) : (
            <MobileGroup>
              <MobileInlineState label="Privacy preferences are unavailable for this connection." />
            </MobileGroup>
          )
        ) : section === 'Account' ? (
          account
        ) : section === 'Privacy' ? (
          privacy
        ) : (
          developer
        )}
        {actionError !== null && (
          <Text accessibilityRole="alert" style={local.actionError}>
            {actionError}
          </Text>
        )}
      </View>
      <MobileGroup>
        {!browser && (
          <LinkRow
            accessibilityLabel="Open app permissions"
            icon="open_in_new"
            title="App Permissions"
            subtitle="Review permissions for Omi in your device settings."
            onPress={() => {
              Linking.openSettings().catch(() =>
                setActionError('Device settings could not be opened.'),
              );
            }}
          />
        )}
        <LinkRow
          accessibilityLabel="Read privacy policy"
          icon="open_in_new"
          title="Privacy Policy"
          subtitle="How Omi handles your information."
          onPress={() => {
            Linking.openURL('https://www.omi.me/pages/privacy').catch(() =>
              setActionError('The privacy policy could not be opened.'),
            );
          }}
        />
        <LinkRow
          accessibilityLabel="Read terms of service"
          icon="open_in_new"
          title="Terms of Service"
          subtitle="Terms for using Omi."
          onPress={() => {
            Linking.openURL('https://www.omi.me/pages/terms-of-service').catch(
              () => setActionError('The terms of service could not be opened.'),
            );
          }}
        />
      </MobileGroup>
    </ScrollView>
  );
}

const createStyles = (t: OmiTheme) => ({
  page: {
    gap: t.space.xl,
    paddingHorizontal: t.layout.pageGutter.mobile,
    paddingTop: t.space.xs,
    paddingBottom: t.space.xxl,
  },
  block: {gap: t.space.xs},
  state: {alignItems: 'center' as const, gap: t.space.md},
  rowAction: {paddingRight: t.space.sm},
  choice: {paddingHorizontal: t.space.lg, paddingBottom: t.space.md},
  actionError: {
    ...t.type.subhead,
    color: t.color.danger,
    paddingHorizontal: t.space.xs,
    paddingTop: t.space.sm,
  },
});
