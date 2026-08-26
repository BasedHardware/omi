import React, {useCallback, useEffect, useState} from 'react';
import {ActivityIndicator, ScrollView, Text, View} from 'react-native';
import {
  cloudSessionUnavailableCopy,
  loadAccountSettings,
  optInTrainingData,
  setPrivateCloudSync,
  setStoreRecordingPermission,
  type AccountSettingsSnapshot,
} from '../desktopCloudClient';
import {
  desktopBackendConfigurationCopy,
  desktopBackendUnauthorizedCopy,
  desktopReadErrorCopy,
} from '../desktopReadClient';
import {omiAuth, omiBackend} from '../omiNative';
import {FocusPressable} from '../ui/Pressable';
import {styles} from '../ui/styles';

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
          style={({pressed}) => [styles.cloudAction, pressed && styles.pressed]}>
          <Text style={styles.cloudActionText}>
            {busy ? 'Updating…' : actionLabel}
          </Text>
        </FocusPressable>
      )}
    </View>
  );
}

export function SettingsPage({
  onSignIn,
  onSignOut,
  signingIn = false,
}: {
  onSignIn?: () => Promise<void>;
  onSignOut?: () => Promise<void>;
  signingIn?: boolean;
}) {
  const [section, setSection] = useState<SettingsSection>('Account');
  const [phase, setPhase] = useState<'loading' | 'signed-out' | 'ready' | 'error'>(
    'loading',
  );
  const [error, setError] = useState<string | null>(null);
  const [snapshot, setSnapshot] = useState<AccountSettingsSnapshot | null>(null);
  const [pending, setPending] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);

  const reload = useCallback(async () => {
    const backend = omiBackend;
    const auth = omiAuth;
    setActionError(null);
    if (backend === undefined || backend === null) {
      setSnapshot(null);
      setError(cloudSessionUnavailableCopy(backend));
      setPhase('error');
      return;
    }
    if (auth !== undefined && auth !== null) {
      const hasSession = await auth.hasCloudSession();
      if (!hasSession) {
        setSnapshot(null);
        setError(desktopBackendUnauthorizedCopy);
        setPhase('signed-out');
        return;
      }
    }
    setPhase(current => (current === 'ready' ? current : 'loading'));
    try {
      setSnapshot(await loadAccountSettings(backend));
      setError(null);
      setPhase('ready');
    } catch (reason) {
      setSnapshot(null);
      setError(desktopReadErrorCopy(reason));
      setPhase('error');
    }
  }, []);

  useEffect(() => {
    reload().catch(() => undefined);
  }, [reload]);

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

  const account = snapshot === null ? null : (
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
      <Text style={styles.projectionEmptyCopy}>
        Notification and usage controls that need other account APIs are not
        shown.
      </Text>
    </>
  );

  const privacy = snapshot === null ? null : (
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
      <Text style={styles.projectionEmptyCopy}>
        Export and account deletion are not offered here. Those actions need
        file download or irreversible deletion flows this page does not run.
      </Text>
    </>
  );

  const developer = snapshot === null ? null : snapshot.webhooks === null ? (
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
      <Text style={styles.projectionEmptyCopy}>
        API keys and webhook URL edits are not offered here.
      </Text>
    </>
  );

  return (
    <ScrollView contentContainerStyle={styles.destinationPage}>
      <View accessibilityRole="tablist" style={styles.destinationTabs}>
        {sections.map(label => (
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
                  pressed && styles.pressed,
                ]}>
                <Text style={styles.cloudActionText}>
                  {signingIn ? 'Signing in…' : 'Sign in'}
                </Text>
              </FocusPressable>
            )}
            {phase === 'error' &&
              error !== desktopBackendConfigurationCopy && (
                <FocusPressable
                  accessibilityLabel="Retry settings"
                  accessibilityRole="button"
                  onPress={() => {
                    reload().catch(() => undefined);
                  }}
                  style={({pressed}) => [
                    styles.cloudAction,
                    pressed && styles.pressed,
                  ]}>
                  <Text style={styles.cloudActionText}>Retry</Text>
                </FocusPressable>
              )}
          </>
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
    </ScrollView>
  );
}
