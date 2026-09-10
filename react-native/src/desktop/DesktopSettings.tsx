import React, {useCallback, useEffect, useRef, useState} from 'react';
import type {useRewindCapture} from '../app/useRewindCapture';
import {Animated, ScrollView, Switch, Text, View} from 'react-native';
import {useReduceMotion} from '../app/useReduceMotion';
import {desktopEaseSmoothOut} from './desktopMotion';
import {
  cloudErrorCanRetry,
  loadAccountSettings,
  optInTrainingData,
  setPrivateCloudSync,
  setStoreRecordingPermission,
  type AccountSettingsSnapshot,
} from '../desktopCloudClient';
import {
  dataProtectionCopy,
  desktopReadErrorCopy,
  developerWebhookRowCopy,
  developerWebhookTypeCopy,
  developerKeysCopy,
  accountFieldCopy,
  subscriptionPlanCopy,
  subscriptionStatusCopy,
  usageStatsCopy,
  subscriptionPeriodCopy,
  primaryLanguageCopy,
  peopleNameRows,
  fairUseCopy,
  dailySummaryCopy,
  dailySummaryScheduleCopy,
  mentorNotificationFrequencyCopy,
  automaticTranslationCopy,
  customVocabularyCopy,
  visibleDisplayText,
} from '../desktopReadClient';
import {
  audioRecordingModeCopy,
  defaultDesktopPreferences,
  loadDesktopPreferences,
  loadPermissionStatus,
  requestDesktopPermission,
  rewindRetentionCopy,
  setDesktopPreference,
  type AudioRecordingMode,
  type DesktopPreferences,
  type PermissionKind,
  type PermissionState,
} from '../desktopSettingsClient';
import {omiBackend} from '../omiNative';
import {loadOmiPeopleNames} from '../legacyOmiPeople';
import {loadOmiFairUseStatus} from '../legacyOmiFairUse';
import {loadOmiDailySummaries} from '../legacyOmiDailySummaries';
import {loadOmiDailySummarySchedule} from '../legacyOmiDailySummarySchedule';
import {loadOmiMentorNotificationSettings} from '../legacyOmiMentorNotifications';
import {loadOmiTranscriptionPreferences} from '../legacyOmiTranscriptionPreferences';
import {loadOmiDevApiKeys, loadOmiMcpApiKeys} from '../legacyOmiDeveloperKeys';
import {FocusPressable} from '../ui/Pressable';
import {
  desktopMotion,
  desktopSettingsPanes,
  type DesktopSession,
  type DesktopSettingsPane,
} from './desktopChrome';
import {ShippingStage} from './ShippingStage';
import {desktopTokens as token} from './tokens';

type Props = {
  capture?: ReturnType<typeof useRewindCapture>;
  deviceContent?: React.ReactNode;
  session: DesktopSession;
  signingIn: boolean;
  onSignIn: () => void;
  onSignOut: () => void | Promise<void>;
  onWorkspaceReload?: () => void;
  softwarePlaneLocked: boolean;
};

function failedAccountSettings(error: string): AccountSettingsSnapshot {
  return {
    profile: null,
    profileError: error,
    subscription: null,
    subscriptionError: error,
    storeRecordingPermission: null,
    storeRecordingError: error,
    trainingOptedIn: null,
    trainingError: error,
    privateCloudSync: null,
    privateCloudSyncError: error,
    webhooks: null,
    webhooksError: error,
    usage: null,
    usageError: error,
    language: null,
    languageError: error,
    languageNames: null,
    languageNamesError: error,
  };
}

const PANE_ITEM_HEIGHT = 40;
const PANE_ITEM_GAP = 12;
const PANE_PILL_RADIUS = 14;

type PrivacyWriteKind = 'recording' | 'training' | 'sync';

function Row({
  action,
  actionLabel,
  copy,
  disabled = false,
  title,
  trailing,
}: {
  action?: () => void;
  actionLabel?: string;
  copy: string;
  disabled?: boolean;
  title: string;
  trailing?: React.ReactNode;
}) {
  return (
    <View style={styles.row}>
      <View style={styles.rowCopy}>
        <Text style={styles.rowTitle}>{title}</Text>
        <Text style={styles.rowMeta}>{copy}</Text>
      </View>
      {trailing}
      {action !== undefined && actionLabel !== undefined ? (
        <FocusPressable
          accessibilityLabel={actionLabel}
          accessibilityRole="button"
          accessibilityState={{disabled}}
          disabled={disabled}
          onPress={action}
          style={({pressed}) => [styles.action, pressed && styles.pressed]}>
          <Text style={styles.actionText}>{actionLabel}</Text>
        </FocusPressable>
      ) : null}
    </View>
  );
}

function Segmented<Value extends string>({
  disabled = false,
  formatOption,
  onChange,
  options,
  value,
}: {
  disabled?: boolean;
  formatOption?: (value: Value) => string;
  onChange: (value: Value) => void;
  options: readonly Value[];
  value: Value;
}) {
  return (
    <View style={styles.segments}>
      {options.map(option => (
        <FocusPressable
          accessibilityRole="button"
          accessibilityState={{disabled, selected: value === option}}
          disabled={disabled}
          key={option}
          onPress={() => onChange(option)}
          style={({pressed}) => [
            styles.segment,
            value === option && styles.segmentActive,
            pressed && styles.pressed,
          ]}>
          <Text
            style={[
              styles.segmentText,
              value === option && styles.segmentTextActive,
            ]}>
            {formatOption ? formatOption(option) : option}
          </Text>
        </FocusPressable>
      ))}
    </View>
  );
}

function SettingsNav({
  pane,
  onChange,
}: {
  pane: DesktopSettingsPane;
  onChange: (pane: DesktopSettingsPane) => void;
}) {
  const reduceMotion = useReduceMotion();
  const index = Math.max(0, desktopSettingsPanes.indexOf(pane));
  const translateY = useRef(
    new Animated.Value(index * (PANE_ITEM_HEIGHT + PANE_ITEM_GAP)),
  ).current;
  useEffect(() => {
    const next = index * (PANE_ITEM_HEIGHT + PANE_ITEM_GAP);
    if (reduceMotion) {
      translateY.setValue(next);
      return;
    }
    const animation = Animated.timing(translateY, {
      duration: desktopMotion.navMs,
      easing: desktopEaseSmoothOut(),
      toValue: next,
      useNativeDriver: true,
    });
    animation.start();
    return () => {
      animation.stop();
    };
  }, [index, reduceMotion, translateY]);
  return (
    <View accessibilityRole="tablist" style={styles.sidebar}>
      <Animated.View
        pointerEvents="none"
        style={[styles.panePill, {transform: [{translateY}]}]}
      />
      {desktopSettingsPanes.map(label => (
        <FocusPressable
          accessibilityLabel={label}
          accessibilityRole="tab"
          accessibilityState={{selected: pane === label}}
          key={label}
          onPress={() => onChange(label)}
          style={styles.paneItem}>
          <Text
            style={[styles.paneText, pane === label && styles.paneTextActive]}>
            {label}
          </Text>
        </FocusPressable>
      ))}
    </View>
  );
}

export function DesktopSettings({
  capture,
  deviceContent,
  onSignIn,
  onSignOut,
  onWorkspaceReload,
  session,
  signingIn,
  softwarePlaneLocked,
}: Props) {
  const [pane, setPane] = useState<DesktopSettingsPane>('General');
  const [prefs, setPrefs] = useState<DesktopPreferences>(
    defaultDesktopPreferences,
  );
  const [permissions, setPermissions] = useState<
    Record<PermissionKind, PermissionState>
  >({microphone: 'unknown', notifications: 'unknown', screen: 'unknown'});
  const [account, setAccount] = useState<AccountSettingsSnapshot | null>(null);
  const [peopleNames, setPeopleNames] = useState<{id: string; name: string}[]>(
    [],
  );
  const [fairUse, setFairUse] = useState<ReturnType<typeof fairUseCopy>>(null);
  const [dailySummaries, setDailySummaries] = useState<
    ReturnType<typeof dailySummaryCopy>
  >([]);
  const [dailySummarySchedule, setDailySummarySchedule] = useState<
    ReturnType<typeof dailySummaryScheduleCopy>
  >([]);
  const [notificationFrequency, setNotificationFrequency] = useState<
    ReturnType<typeof mentorNotificationFrequencyCopy>
  >([]);
  const [automaticTranslation, setAutomaticTranslation] = useState<
    ReturnType<typeof automaticTranslationCopy>
  >([]);
  const [customVocabulary, setCustomVocabulary] = useState<
    ReturnType<typeof customVocabularyCopy>
  >([]);
  const [developerKeys, setDeveloperKeys] = useState<
    ReturnType<typeof developerKeysCopy>
  >([]);
  const [mcpKeys, setMcpKeys] = useState<ReturnType<typeof developerKeysCopy>>(
    [],
  );
  const [actionStatus, setActionStatus] = useState<string | null>(null);
  const [privacyWritesAvailable, setPrivacyWritesAvailable] = useState<
    Record<PrivacyWriteKind, boolean>
  >({recording: true, training: true, sync: true});
  const actionSeqRef = useRef(0);
  const reloadSeqRef = useRef(0);
  const backend = omiBackend;

  const reload = useCallback(async () => {
    const seq = ++reloadSeqRef.current;
    const nextPrefs = await loadDesktopPreferences();
    if (seq !== reloadSeqRef.current) {
      return;
    }
    setPrefs(nextPrefs);
    try {
      const nextPermissions = await loadPermissionStatus();
      if (seq !== reloadSeqRef.current) {
        return;
      }
      setPermissions(nextPermissions);
    } catch {}
    let nextAccount: AccountSettingsSnapshot | null = null;
    let nextPeople: {id: string; name: string}[] = [];
    let nextFairUse: ReturnType<typeof fairUseCopy> = null;
    let nextDailySummaries: ReturnType<typeof dailySummaryCopy> = [];
    let nextDailySummarySchedule: ReturnType<typeof dailySummaryScheduleCopy> =
      [];
    let nextNotificationFrequency: ReturnType<
      typeof mentorNotificationFrequencyCopy
    > = [];
    let nextAutomaticTranslation: ReturnType<typeof automaticTranslationCopy> =
      [];
    let nextCustomVocabulary: ReturnType<typeof customVocabularyCopy> = [];
    let nextDeveloperKeys: ReturnType<typeof developerKeysCopy> = [];
    let nextMcpKeys: ReturnType<typeof developerKeysCopy> = [];
    if (backend !== undefined && backend !== null && session === 'ready') {
      const peopleTask = loadOmiPeopleNames(backend).catch(
        () => new Map<string, string>(),
      );
      const fairUseTask = loadOmiFairUseStatus(backend).catch(() => null);
      const dailySummariesTask = loadOmiDailySummaries(backend).catch(() => []);
      const dailySummaryScheduleTask = loadOmiDailySummarySchedule(
        backend,
      ).catch(() => null);
      const notificationFrequencyTask = loadOmiMentorNotificationSettings(
        backend,
      ).catch(() => null);
      const transcriptionPreferencesTask = loadOmiTranscriptionPreferences(
        backend,
      ).catch(() => null);
      const developerKeysTask = loadOmiDevApiKeys(backend).catch(() => []);
      const mcpKeysTask = loadOmiMcpApiKeys(backend).catch(() => []);
      try {
        nextAccount = await loadAccountSettings(backend);
      } catch (reason) {
        nextAccount = failedAccountSettings(desktopReadErrorCopy(reason));
      }
      nextPeople = peopleNameRows(await peopleTask);
      nextFairUse = fairUseCopy(await fairUseTask);
      nextDailySummaries = dailySummaryCopy(await dailySummariesTask);
      nextDailySummarySchedule = dailySummaryScheduleCopy(
        await dailySummaryScheduleTask,
      );
      nextNotificationFrequency = mentorNotificationFrequencyCopy(
        (await notificationFrequencyTask)?.frequency,
      );
      const transcription = await transcriptionPreferencesTask;
      nextAutomaticTranslation = automaticTranslationCopy(
        transcription?.singleLanguageMode,
      );
      nextCustomVocabulary = customVocabularyCopy(transcription?.vocabulary);
      nextDeveloperKeys = developerKeysCopy(
        await developerKeysTask,
        'Developer key',
      );
      nextMcpKeys = developerKeysCopy(
        (await mcpKeysTask).map(key => ({
          name: key.name,
          keyPrefix: key.keyPrefix,
        })),
        'MCP key',
      );
    }
    if (seq !== reloadSeqRef.current) {
      return;
    }
    setAccount(nextAccount);
    setPeopleNames(nextPeople);
    setFairUse(nextFairUse);
    setDailySummaries(nextDailySummaries);
    setDailySummarySchedule(nextDailySummarySchedule);
    setNotificationFrequency(nextNotificationFrequency);
    setAutomaticTranslation(nextAutomaticTranslation);
    setCustomVocabulary(nextCustomVocabulary);
    setDeveloperKeys(nextDeveloperKeys);
    setMcpKeys(nextMcpKeys);
  }, [backend, session]);

  useEffect(() => {
    reload().catch(() => undefined);
    return () => {
      reloadSeqRef.current += 1;
      actionSeqRef.current += 1;
    };
  }, [reload]);

  const setPref = async <
    Key extends Exclude<keyof DesktopPreferences, 'stampedV5Origin'>,
  >(
    key: Key,
    value: DesktopPreferences[Key],
  ) => {
    const seq = ++reloadSeqRef.current;
    const next = await setDesktopPreference(key, value);
    if (seq !== reloadSeqRef.current) {
      return;
    }
    setPrefs(next);
    reload().catch(() => undefined);
  };

  const runAction = (
    action: () => Promise<void>,
    failure = 'Settings change could not be saved. Try again.',
    writeKind?: PrivacyWriteKind,
  ) => {
    const seq = ++actionSeqRef.current;
    setActionStatus('Saving settings…');
    action().then(
      () => {
        if (seq === actionSeqRef.current) {
          setActionStatus(null);
        }
      },
      (reason: unknown) => {
        if (seq === actionSeqRef.current) {
          setActionStatus(
            cloudErrorCanRetry(reason) ? failure : desktopReadErrorCopy(reason),
          );
          if (writeKind !== undefined && !cloudErrorCanRetry(reason)) {
            setPrivacyWritesAvailable(current => ({
              ...current,
              [writeKind]: false,
            }));
          }
        }
      },
    );
  };

  const request = async (kind: PermissionKind) => {
    const next = await requestDesktopPermission(kind);
    setPermissions(current => ({...current, [kind]: next}));
    if (kind === 'screen' && next === 'granted') {
      await setPref('screenCapture', true);
    }
    if (kind === 'notifications' && next === 'granted') {
      await setPref('notificationsEnabled', true);
    }
    return next;
  };

  const advanced = (
    <Row
      copy={
        softwarePlaneLocked
          ? 'Stop the active response before switching backends.'
          : prefs.softwarePlane === 'new'
          ? prefs.stampedV5Origin != null
            ? 'New sends v5 chat, capture, conversations, memories, tasks, and settings to the stamped origin. Account, apps, and privacy controls still use production api.omi.me.'
            : 'New is selected, but no valid stamped v5 origin is configured.'
          : 'Old backend uses your existing Omi account and api.omi.me.'
      }
      title="Backend"
      trailing={
        <Segmented
          disabled={softwarePlaneLocked}
          onChange={value => {
            runAction(async () => {
              await setPref(
                'softwarePlane',
                value === 'New backend' ? 'new' : 'old',
              );
              onWorkspaceReload?.();
            });
          }}
          options={['Old backend', 'New backend'] as const}
          value={prefs.softwarePlane === 'new' ? 'New backend' : 'Old backend'}
        />
      }
    />
  );

  const general = (
    <>
      {advanced}
      <Row
        copy={
          capture?.available
            ? capture.error ??
              (capture.capturing
                ? 'Saving screen history on this Mac.'
                : 'Start or stop saving screen history on this Mac.')
            : permissions.screen === 'granted'
            ? 'Screen capture is allowed on this Mac.'
            : permissions.screen === 'denied'
            ? 'Screen Recording access is denied in System Settings.'
            : 'Omi needs Screen Recording to keep what you see.'
        }
        title="Screen Capture"
        trailing={
          <Switch
            onValueChange={value => {
              if (capture?.available) {
                if (value) void capture.start();
                else void capture.stop();
                return;
              }
              if (value) {
                runAction(async () => {
                  await request('screen');
                });
                return;
              }
              runAction(() => setPref('screenCapture', false));
            }}
            value={
              capture?.available
                ? capture.capturing || capture.busy
                : prefs.screenCapture && permissions.screen !== 'denied'
            }
          />
        }
      />
      <Row
        copy={
          permissions.microphone === 'denied'
            ? 'Microphone access is denied in System Settings.'
            : 'Off, always, or only while a meeting is in the foreground.'
        }
        title="Audio Recording"
        trailing={
          <Segmented<AudioRecordingMode>
            formatOption={audioRecordingModeCopy}
            onChange={value => {
              runAction(async () => {
                if (
                  value === 'off' ||
                  (await request('microphone')) === 'granted'
                ) {
                  await setPref('audioMode', value);
                }
              });
            }}
            options={['off', 'always', 'meetings']}
            value={prefs.audioMode}
          />
        }
      />
      <Row
        copy={
          permissions.notifications === 'granted'
            ? 'Banners are allowed in System Settings.'
            : permissions.notifications === 'denied'
            ? 'Notification access is denied in System Settings.'
            : 'Ask macOS for notification permission.'
        }
        title="Notifications"
        trailing={
          <Switch
            onValueChange={value => {
              if (value) {
                runAction(async () => {
                  await request('notifications');
                });
                return;
              }
              runAction(() => setPref('notificationsEnabled', false));
            }}
            value={
              prefs.notificationsEnabled &&
              permissions.notifications !== 'denied'
            }
          />
        }
      />
    </>
  );

  const accountPane = (
    <>
      <Row
        copy={
          session !== 'ready'
            ? 'Sign in to load conversations and memories.'
            : account === null
            ? 'Loading account…'
            : account.profile != null
            ? accountFieldCopy(
                account.profile.email,
                'Email not set on this account.',
              )
            : account.profileError ?? 'Account profile is unavailable.'
        }
        title="Account"
        action={
          session === 'ready'
            ? () => {
                runAction(
                  async () => onSignOut(),
                  'Sign out failed. Try again.',
                );
              }
            : onSignIn
        }
        actionLabel={
          session === 'ready'
            ? 'Sign out'
            : signingIn
            ? 'Signing in…'
            : 'Sign in'
        }
      />
      {account?.profile != null ? (
        <Row
          copy={accountFieldCopy(
            account.profile.name,
            'Name not set on this account.',
          )}
          title="Name"
        />
      ) : null}
      {account?.profile != null ? (
        <Row
          copy={accountFieldCopy(account.profile.uid, 'Account id unavailable')}
          title="Account id"
        />
      ) : null}
      {account?.profile != null &&
      visibleDisplayText(account.profile.company ?? '') !== '' ? (
        <Row
          copy={visibleDisplayText(account.profile.company ?? '')}
          title="Company"
        />
      ) : null}
      {account?.profile != null &&
      visibleDisplayText(account.profile.job ?? '') !== '' ? (
        <Row copy={visibleDisplayText(account.profile.job ?? '')} title="Job" />
      ) : null}
      {account?.profile?.dataProtectionLevel != null ? (
        <Row
          copy={dataProtectionCopy(account.profile.dataProtectionLevel)}
          title="Data protection"
        />
      ) : null}
      {account?.subscription != null ? (
        <Row
          copy={[
            subscriptionPlanCopy(account.subscription.plan),
            subscriptionStatusCopy(account.subscription.status),
            account.subscription.transcriptionSecondsUsed !== null &&
            account.subscription.transcriptionSecondsLimit !== null
              ? `${account.subscription.transcriptionSecondsUsed} / ${account.subscription.transcriptionSecondsLimit} transcribed seconds`
              : null,
          ]
            .filter(item => item !== null)
            .join(' · ')}
          title="Current plan"
        />
      ) : (
        <Row
          copy={
            account === null
              ? 'Loading plan…'
              : account.subscriptionError ?? 'Plan is unavailable.'
          }
          title="Current plan"
        />
      )}
      {usageStatsCopy(account?.usage)?.map(row => (
        <Row copy={row.copy} key={row.title} title={row.title} />
      ))}
      {subscriptionPeriodCopy(account?.subscription)?.map(row => (
        <Row copy={row.copy} key={row.title} title={row.title} />
      ))}
      {primaryLanguageCopy(account?.language, account?.languageNames) !==
      null ? (
        <Row
          copy={
            primaryLanguageCopy(account?.language, account?.languageNames) ?? ''
          }
          title="Primary language"
        />
      ) : null}
      {automaticTranslation.map((row, index) => (
        <Row copy={row.copy} key={`${row.title}-${index}`} title={row.title} />
      ))}
      {customVocabulary.map((row, index) => (
        <Row copy={row.copy} key={`${row.title}-${index}`} title={row.title} />
      ))}
      {peopleNames.map(person => (
        <Row copy={person.name} key={person.id} title="People" />
      ))}
      {fairUse?.map((row, index) => (
        <Row copy={row.copy} key={`${row.title}-${index}`} title={row.title} />
      ))}
      {notificationFrequency.map((row, index) => (
        <Row copy={row.copy} key={`${row.title}-${index}`} title={row.title} />
      ))}
      {dailySummarySchedule.map((row, index) => (
        <Row copy={row.copy} key={`${row.title}-${index}`} title={row.title} />
      ))}
      {dailySummaries.map((row, index) => (
        <Row copy={row.copy} key={`${row.title}-${index}`} title={row.title} />
      ))}
    </>
  );

  const transcription = (
    <>
      <Row
        copy="Detect the spoken language automatically."
        title="Language Mode"
        trailing={
          <Switch
            onValueChange={value => {
              runAction(() => setPref('transcriptionAutoDetect', value));
            }}
            value={prefs.transcriptionAutoDetect}
          />
        }
      />
      <Row
        copy="Skip silence before sending audio."
        title="Local VAD Gate"
        trailing={
          <Switch
            onValueChange={value => {
              runAction(() => setPref('vadGate', value));
            }}
            value={prefs.vadGate}
          />
        }
      />
    </>
  );

  const rewind = (
    <>
      <Row
        copy="How long captured frames stay on this Mac."
        title="Data Retention"
        trailing={
          <Segmented
            formatOption={rewindRetentionCopy}
            onChange={value => {
              runAction(() => setPref('rewindRetentionDays', Number(value)));
            }}
            options={['7', '14', '30', '0'] as const}
            value={String(prefs.rewindRetentionDays) as '7' | '14' | '30' | '0'}
          />
        }
      />
      <Row
        copy="Keep meeting screenshots with conversation notes."
        title="Meeting Screenshots"
        trailing={
          <Switch
            onValueChange={value => {
              runAction(() => setPref('meetingNoteScreenshots', value));
            }}
            value={prefs.meetingNoteScreenshots}
          />
        }
      />
    </>
  );

  const alerts = (
    <>
      <Row
        copy={
          session !== 'ready'
            ? 'Sign in to load this account setting.'
            : account === null
            ? 'Loading recording storage…'
            : account.storeRecordingPermission === null
            ? account.storeRecordingError ??
              'Cloud recording storage status is unavailable.'
            : account.storeRecordingPermission
            ? 'Cloud recording storage is on.'
            : 'Cloud recording storage is off until you allow it.'
        }
        title="Store Recordings"
        action={
          session === 'ready' &&
          backend != null &&
          typeof account?.storeRecordingPermission === 'boolean' &&
          privacyWritesAvailable.recording
            ? () => {
                runAction(
                  async () => {
                    await setStoreRecordingPermission(
                      backend,
                      !(account?.storeRecordingPermission ?? false),
                    );
                    await reload();
                  },
                  'Settings change could not be saved. Try again.',
                  'recording',
                );
              }
            : undefined
        }
        actionLabel="Update"
      />
      <Row
        copy={
          session !== 'ready'
            ? 'Sign in to load this account setting.'
            : account === null
            ? 'Loading private cloud sync…'
            : account.privateCloudSync === null
            ? account.privateCloudSyncError ??
              'Private cloud sync status is unavailable.'
            : account.privateCloudSync
            ? 'Private cloud sync is on.'
            : 'Private cloud sync is off.'
        }
        title="Private Cloud Sync"
        action={
          session === 'ready' &&
          backend != null &&
          typeof account?.privateCloudSync === 'boolean' &&
          privacyWritesAvailable.sync
            ? () => {
                runAction(
                  async () => {
                    await setPrivateCloudSync(
                      backend,
                      !(account?.privateCloudSync ?? false),
                    );
                    await reload();
                  },
                  'Settings change could not be saved. Try again.',
                  'sync',
                );
              }
            : undefined
        }
        actionLabel="Update"
      />
      <Row
        copy={
          session !== 'ready'
            ? 'Sign in to load this account setting.'
            : account === null
            ? 'Loading training data…'
            : account.trainingOptedIn === null
            ? account.trainingError ?? 'Training opt-in is unavailable.'
            : account.trainingOptedIn
            ? 'This account has opted in to training data. The API does not expose an opt-out from here.'
            : 'This account has not opted in to training data.'
        }
        title="Training Data"
        action={
          session === 'ready' &&
          backend != null &&
          account?.trainingOptedIn === false &&
          privacyWritesAvailable.training
            ? () => {
                runAction(
                  async () => {
                    await optInTrainingData(backend);
                    await reload();
                  },
                  'Settings change could not be saved. Try again.',
                  'training',
                );
              }
            : undefined
        }
        actionLabel="Opt in"
      />
    </>
  );

  const about = (
    <>
      <Row copy="Omi v5 for Mac" title="Version" />
      <Row copy="https://omi.me" title="Website" />
      <Row copy="https://omi.me/privacy" title="Privacy Policy" />
    </>
  );

  const automation = (
    <>
      {advanced}
      {session !== 'ready' ? (
        <Row
          copy="Sign in to load this account setting."
          title="Developer Webhooks"
        />
      ) : account === null ? (
        <Row copy="Loading developer webhooks…" title="Developer Webhooks" />
      ) : account.webhooks === null ? (
        <Row
          copy={
            account.webhooksError ?? 'Developer webhook status is unavailable.'
          }
          title="Developer Webhooks"
        />
      ) : account.webhooks.length === 0 ? (
        <Row
          copy="No developer webhooks were returned."
          title="Developer Webhooks"
        />
      ) : (
        account.webhooks.map(webhook => (
          <Row
            copy={developerWebhookRowCopy(webhook)}
            key={webhook.type}
            title={developerWebhookTypeCopy(webhook.type)}
          />
        ))
      )}
      {developerKeys.map((row, index) => (
        <Row copy={row.copy} key={`dev-key-${index}`} title={row.title} />
      ))}
      {mcpKeys.map((row, index) => (
        <Row copy={row.copy} key={`mcp-key-${index}`} title={row.title} />
      ))}
    </>
  );

  const body =
    pane === 'General'
      ? general
      : pane === 'Account & Plan'
      ? accountPane
      : pane === 'Transcription'
      ? transcription
      : pane === 'Rewind'
      ? rewind
      : pane === 'Alerts & Privacy'
      ? alerts
      : pane === 'AI & Automation'
      ? automation
      : about;

  return (
    <View style={styles.root}>
      <SettingsNav onChange={setPane} pane={pane} />
      <ScrollView contentContainerStyle={styles.content} style={styles.scroll}>
        {actionStatus !== null ? (
          <Text
            accessibilityLabel="Settings action status"
            style={styles.status}>
            {actionStatus}
          </Text>
        ) : null}
        <ShippingStage stageKey={pane} variant="page">
          {body}
          {pane === 'General' ? deviceContent : null}
        </ShippingStage>
      </ScrollView>
    </View>
  );
}

const styles = {
  root: {flex: 1, flexDirection: 'row' as const},
  sidebar: {
    marginRight: 24,
    position: 'relative' as const,
    width: 196,
  },
  panePill: {
    backgroundColor: token.color.glassSelected,
    borderRadius: PANE_PILL_RADIUS,
    height: PANE_ITEM_HEIGHT,
    left: 0,
    position: 'absolute' as const,
    right: 0,
    top: 0,
  },
  paneItem: {
    alignItems: 'flex-start' as const,
    height: PANE_ITEM_HEIGHT,
    justifyContent: 'center' as const,
    marginBottom: PANE_ITEM_GAP,
    paddingHorizontal: 14,
  },
  paneText: {
    color: token.color.inkMuted,
    fontFamily: token.font,
    fontSize: token.type.caption,
    fontWeight: '600' as const,
    textAlign: 'left' as const,
  },
  paneTextActive: {color: token.color.ink},
  scroll: {flex: 1},
  content: {paddingBottom: 32},
  status: {
    color: token.color.inkMuted,
    fontFamily: token.font,
    fontSize: token.type.caption,
    marginBottom: 10,
  },
  row: {
    alignItems: 'center' as const,
    backgroundColor: token.color.glassQuiet,
    borderRadius: 16,
    flexDirection: 'row' as const,
    gap: 12,
    marginBottom: 14,
    minHeight: 64,
    padding: 14,
  },
  rowCopy: {flex: 1},
  rowTitle: {
    color: token.color.ink,
    fontFamily: token.font,
    fontSize: token.type.title,
    fontWeight: '500' as const,
  },
  rowMeta: {
    color: token.color.inkMuted,
    fontFamily: token.font,
    fontSize: token.type.meta,
    marginTop: 3,
  },
  action: {
    backgroundColor: token.color.dark,
    borderRadius: token.radius.control,
    paddingHorizontal: 12,
    paddingVertical: 7,
  },
  actionText: {
    color: token.color.white,
    fontFamily: token.font,
    fontSize: token.type.caption,
    fontWeight: '600' as const,
  },
  pressed: {opacity: 0.78},
  segments: {flexDirection: 'row' as const, gap: 6},
  segment: {
    borderRadius: 10,
    minHeight: 28,
    justifyContent: 'center' as const,
    paddingHorizontal: 10,
  },
  segmentActive: {backgroundColor: token.color.glassSelected},
  segmentText: {
    color: token.color.inkMuted,
    fontFamily: token.font,
    fontSize: token.type.caption,
    fontWeight: '600' as const,
    textTransform: 'capitalize' as const,
  },
  segmentTextActive: {color: token.color.ink},
};
