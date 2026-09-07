import React, {useCallback, useEffect, useRef, useState} from 'react';
import {
  ActivityIndicator,
  Linking,
  Platform,
  ScrollView,
  StyleSheet,
  Text,
  View,
} from 'react-native';
import {
  cloudSessionUnavailableCopy,
  loadAccountSettings,
  loadServiceSettings,
  optInTrainingData,
  serviceSettingsCanRetry,
  serviceSettingsErrorCopy,
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
import {FocusPressable} from '../ui/Pressable';
import {styles} from '../ui/styles';
import {parseSoftwarePlane, type SoftwarePlane} from '../v5BackendOrigin';

const sections = ['Account', 'Privacy', 'Developer'] as const;
type SettingsSection = (typeof sections)[number];

function SettingRow({
  action,
  actionLabel,
  busy = false,
  copy,
  title,
}: {
  action?: () => void;
  actionLabel?: string;
  busy?: boolean;
  copy: string;
  title: string;
}) {
  return (
    <View style={styles.cloudRow}>
      <View style={styles.cloudRowBody}>
        <Text style={styles.cloudRowTitle}>{title}</Text>
        <Text style={styles.cloudRowMeta}>{copy}</Text>
      </View>
      {action !== undefined && actionLabel !== undefined && (
        <FocusPressable
          accessibilityLabel={actionLabel}
          accessibilityRole="button"
          disabled={busy}
          onPress={action}
          style={({pressed}) => [
            styles.cloudAction,
            settingsStyles.touchAction,
            pressed && styles.pressed,
          ]}>
          <Text style={styles.cloudActionText}>
            {busy ? 'Updating…' : actionLabel}
          </Text>
        </FocusPressable>
      )}
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
        ? 'New sends v5 chat, capture, conversations, memories, tasks, and settings to the stamped origin. Account, apps, and privacy controls still use production api.omi.me.'
        : 'New is selected, but no valid stamped v5 origin is configured.'
      : 'Old backend uses your existing Omi account and api.omi.me.';
  return (
    <View style={styles.cloudRow}>
      <View style={styles.cloudRowBody}>
        <Text style={styles.cloudRowTitle}>Backend</Text>
        <Text style={styles.cloudRowMeta}>{copy}</Text>
      </View>
      <View>
        {(['old', 'new'] as const).map(option => (
          <FocusPressable
            accessibilityLabel={
              option === 'new' ? 'Use New backend' : 'Use Old backend'
            }
            accessibilityRole="button"
            accessibilityState={{selected: plane === option}}
            disabled={busy}
            key={option}
            onPress={() => onSelect(option)}
            style={({pressed}) => [
              styles.cloudAction,
              settingsStyles.touchAction,
              pressed && styles.pressed,
            ]}>
            <Text style={styles.cloudActionText}>
              {option === 'new' ? 'New backend' : 'Old backend'}
            </Text>
          </FocusPressable>
        ))}
      </View>
    </View>
  );
}

export function SettingsPage({
  onSignIn,
  onSignOut,
  onWorkspaceReload,
  signingIn = false,
}: {
  onSignIn?: () => Promise<void>;
  onSignOut?: () => Promise<void>;
  onWorkspaceReload?: () => void;
  signingIn?: boolean;
}) {
  const browser = Platform.OS === 'web';
  const [serviceSettings, setServiceSettings] =
    useState<ServiceSettingsSnapshot | null>(null);
  const [section, setSection] = useState<SettingsSection>('Account');
  const [phase, setPhase] = useState<
    'loading' | 'signed-out' | 'ready' | 'error'
  >('loading');
  const [error, setError] = useState<string | null>(null);
  const [settingsCanRetry, setSettingsCanRetry] = useState(true);
  const [snapshot, setSnapshot] = useState<AccountSettingsSnapshot | null>(
    null,
  );
  const [pending, setPending] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const [softwarePlane, setSoftwarePlane] = useState<SoftwarePlane | null>(
    null,
  );
  const [stampedV5Origin, setStampedV5Origin] = useState<string | null>(null);
  const loadGeneration = useRef(0);
  const mounted = useRef(false);

  const reloadSoftwarePlane = useCallback(async () => {
    const backend = omiBackend;
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
        setError(serviceSettingsErrorCopy(reason));
        setSettingsCanRetry(serviceSettingsCanRetry(reason));
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
        setSettingsCanRetry(true);
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
      setSettingsCanRetry(true);
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
    if (backend?.setSoftwarePlane === undefined || pending !== null) {
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
      <>
        {snapshot.profile === null ? (
          <Text style={styles.projectionEmptyCopy}>
            {snapshot.profileError ?? 'Account profile is unavailable.'}
          </Text>
        ) : (
          <>
            <SettingRow
              copy={snapshot.profile.name ?? 'Name not set on this account.'}
              title="Name"
            />
            <SettingRow
              copy={snapshot.profile.email ?? 'Email not set on this account.'}
              title="Email"
            />
            <SettingRow copy={snapshot.profile.uid} title="Account id" />
            {snapshot.profile.company !== null && (
              <SettingRow copy={snapshot.profile.company} title="Company" />
            )}
            {snapshot.profile.job !== null && (
              <SettingRow copy={snapshot.profile.job} title="Job" />
            )}
            {snapshot.profile.dataProtectionLevel !== null && (
              <SettingRow
                copy={snapshot.profile.dataProtectionLevel}
                title="Data protection"
              />
            )}
          </>
        )}
        {snapshot.subscription === null ? (
          <Text style={styles.projectionEmptyCopy}>
            {snapshot.subscriptionError ?? 'Plan is unavailable.'}
          </Text>
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
            busy={pending === 'sign-out'}
            copy="Leave this app's cloud session. Your Omi account stays in the cloud."
            title="Sign out"
          />
        )}
      </>
    );

  const privacy =
    snapshot === null ? null : (
      <>
        {snapshot.storeRecordingPermission === null ? (
          <Text style={styles.projectionEmptyCopy}>
            {snapshot.storeRecordingError ??
              'Recording storage permission is unavailable.'}
          </Text>
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
            busy={pending === 'recording'}
            copy={
              snapshot.storeRecordingPermission
                ? 'Cloud recording storage is on.'
                : 'Cloud recording storage is off.'
            }
            title="Recording storage"
          />
        )}
        {snapshot.trainingOptedIn === null ? (
          <Text style={styles.projectionEmptyCopy}>
            {snapshot.trainingError ?? 'Training opt-in is unavailable.'}
          </Text>
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
            busy={pending === 'training'}
            copy={
              snapshot.trainingOptedIn
                ? 'This account has opted in to training data. The API does not expose an opt-out from here.'
                : 'This account has not opted in to training data.'
            }
            title="Training data"
          />
        )}
        {snapshot.privateCloudSync === null ? (
          <Text style={styles.projectionEmptyCopy}>
            {snapshot.privateCloudSyncError ??
              'Private cloud sync is unavailable.'}
          </Text>
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
            busy={pending === 'sync'}
            copy={
              snapshot.privateCloudSync
                ? 'Private cloud sync is on.'
                : 'Private cloud sync is off.'
            }
            title="Private cloud sync"
          />
        )}
      </>
    );

  const developer =
    snapshot === null ? null : snapshot.webhooks === null ? (
      <Text style={styles.projectionEmptyCopy}>
        {snapshot.webhooksError ?? 'Developer webhook status is unavailable.'}
      </Text>
    ) : snapshot.webhooks.length === 0 ? (
      <Text style={styles.projectionEmptyCopy}>
        No developer webhooks were returned.
      </Text>
    ) : (
      <>
        {snapshot.webhooks.map(webhook => (
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
        ))}
      </>
    );

  return (
    <ScrollView contentContainerStyle={styles.destinationPage}>
      {!browser && softwarePlane !== null && (
        <BackendPlaneRow
          busy={pending === 'software-plane'}
          onSelect={plane => {
            selectSoftwarePlane(plane).catch(() => undefined);
          }}
          plane={softwarePlane}
          stampedOrigin={stampedV5Origin}
        />
      )}
      <View accessibilityRole="tablist" style={styles.destinationTabs}>
        {sections
          .filter(label => !browser || label !== 'Developer')
          .map(label => (
            <FocusPressable
              accessibilityLabel={`${label} settings`}
              accessibilityRole="tab"
              accessibilityState={{selected: section === label}}
              key={label}
              onPress={() => setSection(label)}
              style={({pressed}) => [
                styles.destinationTab,
                section === label && styles.destinationTabActive,
                pressed && styles.pressed,
              ]}>
              <Text
                style={[
                  styles.destinationTabText,
                  section === label && styles.destinationTabTextActive,
                ]}>
                {label}
              </Text>
            </FocusPressable>
          ))}
      </View>
      <View style={styles.destinationSection}>
        <Text style={styles.destinationSectionTitle}>{section}</Text>
        {phase === 'loading' && snapshot === null ? (
          <>
            <ActivityIndicator color="#888888" />
            <Text style={styles.projectionEmptyCopy}>Loading account…</Text>
          </>
        ) : phase === 'signed-out' || phase === 'error' ? (
          <>
            <Text style={styles.projectionEmptyCopy}>
              {error ?? desktopBackendUnauthorizedCopy}
            </Text>
            {phase === 'signed-out' && onSignIn !== undefined && (
              <FocusPressable
                accessibilityLabel="Sign in"
                accessibilityRole="button"
                disabled={signingIn}
                onPress={() => {
                  signIn().catch(() => undefined);
                }}
                style={({pressed}) => [
                  styles.cloudAction,
                  settingsStyles.touchAction,
                  pressed && styles.pressed,
                ]}>
                <Text style={styles.cloudActionText}>
                  {signingIn ? 'Signing in…' : 'Sign in'}
                </Text>
              </FocusPressable>
            )}
            {phase === 'error' &&
              error !== desktopBackendConfigurationCopy &&
              settingsCanRetry && (
                <FocusPressable
                  accessibilityLabel="Retry settings"
                  accessibilityRole="button"
                  onPress={() => {
                    reload().catch(() => undefined);
                  }}
                  style={({pressed}) => [
                    styles.cloudAction,
                    settingsStyles.touchAction,
                    pressed && styles.pressed,
                  ]}>
                  <Text style={styles.cloudActionText}>Retry</Text>
                </FocusPressable>
              )}
          </>
        ) : browser ? (
          section === 'Account' && serviceSettings ? (
            <>
              <SettingRow
                title="Connection identity"
                copy={
                  serviceSettings.identity === null
                    ? 'Identity unavailable for this connection.'
                    : [
                        serviceSettings.identity.displayName,
                        serviceSettings.identity.email,
                      ]
                        .filter(Boolean)
                        .join(' · ') ||
                      'Identity unavailable for this connection.'
                }
              />
              {serviceSettings.entitlement !== null &&
              ['chat', 'transcription_seconds'].includes(
                serviceSettings.entitlement.limitKey,
              ) ? (
                <SettingRow
                  title={
                    serviceSettings.entitlement.limitKey === 'chat'
                      ? 'Chat usage'
                      : 'Transcription usage'
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
            </>
          ) : (
            <Text style={styles.projectionEmptyCopy}>
              Privacy preferences are unavailable for this connection.
            </Text>
          )
        ) : section === 'Account' ? (
          account
        ) : section === 'Privacy' ? (
          privacy
        ) : (
          developer
        )}
        {actionError !== null && (
          <Text style={styles.cloudActionError}>{actionError}</Text>
        )}
      </View>
      <View style={styles.destinationSection}>
        {!browser && (
          <SettingRow
            title="App permissions"
            copy="Review permissions for Omi in your device settings."
            actionLabel="Open app permissions"
            action={() => {
              Linking.openSettings().catch(() =>
                setActionError('Device settings could not be opened.'),
              );
            }}
          />
        )}
        <SettingRow
          title="Privacy policy"
          copy="How Omi handles your information."
          actionLabel="Read privacy policy"
          action={() => {
            Linking.openURL('https://www.omi.me/pages/privacy').catch(() =>
              setActionError('The privacy policy could not be opened.'),
            );
          }}
        />
        <SettingRow
          title="Terms of service"
          copy="Terms for using Omi."
          actionLabel="Read terms of service"
          action={() => {
            Linking.openURL('https://www.omi.me/pages/terms-of-service').catch(
              () => setActionError('The terms of service could not be opened.'),
            );
          }}
        />
      </View>
    </ScrollView>
  );
}

const settingsStyles = StyleSheet.create({touchAction: {minHeight: 44}});
