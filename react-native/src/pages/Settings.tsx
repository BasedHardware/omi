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
  cloudErrorCanRetry,
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
  dataProtectionCopy,
  developerWebhookRowCopy,
  developerWebhookTypeCopy,
  developerKeysCopy,
  accountFieldCopy,
  connectionIdentityCopy,
  subscriptionPlanCopy,
  subscriptionStatusCopy,
  usageStatsCopy,
  usagePeriodStatsCopy,
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
import {omiAuth, omiBackend} from '../omiNative';
import {loadOmiPeopleNames} from '../legacyOmiPeople';
import {
  loadOmiTaskIntegrations,
  taskIntegrationRowCopy,
  type OmiTaskIntegration,
} from '../legacyOmiTaskIntegrations';
import {
  loadOmiIntegrations,
  type OmiIntegration,
} from '../legacyOmiIntegrations';
import {
  loadOmiAppChangelogs,
  type OmiAppChangelogRow,
} from '../legacyOmiAppChangelogs';
import {loadOmiUsagePeriod, type OmiUsageStats} from '../legacyOmiUsage';
import {loadOmiFairUseStatus} from '../legacyOmiFairUse';
import {loadOmiDailySummaries} from '../legacyOmiDailySummaries';
import {loadOmiDailySummarySchedule} from '../legacyOmiDailySummarySchedule';
import {loadOmiMentorNotificationSettings} from '../legacyOmiMentorNotifications';
import {loadOmiTranscriptionPreferences} from '../legacyOmiTranscriptionPreferences';
import {loadOmiDevApiKeys, loadOmiMcpApiKeys} from '../legacyOmiDeveloperKeys';
import {
  importJobsCopy,
  loadOmiImportJobs,
  type OmiImportJobRow,
} from '../legacyOmiImportJobs';
import {FocusPressable} from '../ui/Pressable';
import {styles} from '../ui/styles';
import {parseSoftwarePlane, type SoftwarePlane} from '../v5BackendOrigin';

const sections = ['Account', 'Privacy', 'Developer'] as const;
type SettingsSection = (typeof sections)[number];

type PrivacyWriteKind = 'recording' | 'training' | 'sync';

function isPrivacyWriteKind(id: string): id is PrivacyWriteKind {
  return id === 'recording' || id === 'training' || id === 'sync';
}

function SettingRow({
  action,
  actionLabel,
  busy = false,
  copy,
  disabled = false,
  title,
}: {
  action?: () => void;
  actionLabel?: string;
  busy?: boolean;
  copy: string;
  disabled?: boolean;
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
          accessibilityState={{disabled: busy || disabled}}
          disabled={busy || disabled}
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
  const [peopleNames, setPeopleNames] = useState<{id: string; name: string}[]>(
    [],
  );
  const [taskIntegrations, setTaskIntegrations] = useState<
    OmiTaskIntegration[]
  >([]);
  const [integrations, setIntegrations] = useState<OmiIntegration[]>([]);
  const [appChangelogs, setAppChangelogs] = useState<OmiAppChangelogRow[]>([]);
  const [usageMonthly, setUsageMonthly] = useState<OmiUsageStats | null>(null);
  const [usageYearly, setUsageYearly] = useState<OmiUsageStats | null>(null);
  const [usageAllTime, setUsageAllTime] = useState<OmiUsageStats | null>(null);
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
  const [importJobs, setImportJobs] = useState<OmiImportJobRow[]>([]);
  const [pending, setPending] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const [privacyWritesAvailable, setPrivacyWritesAvailable] = useState<
    Record<PrivacyWriteKind, boolean>
  >({recording: true, training: true, sync: true});
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
      setPeopleNames([]);
      setTaskIntegrations([]);
      setIntegrations([]);
      setAppChangelogs([]);
      setUsageMonthly(null);
      setUsageYearly(null);
      setUsageAllTime(null);
      setFairUse(null);
      setDailySummaries([]);
      setDailySummarySchedule([]);
      setNotificationFrequency([]);
      setAutomaticTranslation([]);
      setCustomVocabulary([]);
      setDeveloperKeys([]);
      setMcpKeys([]);
      setImportJobs([]);
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
        setPeopleNames([]);
        setTaskIntegrations([]);
        setIntegrations([]);
        setAppChangelogs([]);
        setUsageMonthly(null);
        setUsageYearly(null);
        setUsageAllTime(null);
        setFairUse(null);
        setDailySummaries([]);
        setDailySummarySchedule([]);
        setNotificationFrequency([]);
        setAutomaticTranslation([]);
        setCustomVocabulary([]);
        setDeveloperKeys([]);
        setMcpKeys([]);
        setImportJobs([]);
        setError(desktopBackendServiceCopy);
        setSettingsCanRetry(true);
        setPhase('error');
        return;
      }
      if (!hasSession) {
        setSnapshot(null);
        setPeopleNames([]);
        setTaskIntegrations([]);
        setIntegrations([]);
        setAppChangelogs([]);
        setUsageMonthly(null);
        setUsageYearly(null);
        setUsageAllTime(null);
        setFairUse(null);
        setDailySummaries([]);
        setDailySummarySchedule([]);
        setNotificationFrequency([]);
        setAutomaticTranslation([]);
        setCustomVocabulary([]);
        setDeveloperKeys([]);
        setMcpKeys([]);
        setImportJobs([]);
        setError(desktopBackendUnauthorizedCopy);
        setPhase('signed-out');
        return;
      }
    }
    const peopleTask = loadOmiPeopleNames(backend).catch(
      () => new Map<string, string>(),
    );
    const taskIntegrationsTask = loadOmiTaskIntegrations(backend).catch(
      () => [],
    );
    const integrationsTask = loadOmiIntegrations(backend).catch(() => []);
    const appChangelogsTask = loadOmiAppChangelogs(backend).catch(() => []);
    const usageMonthlyTask = loadOmiUsagePeriod(backend, 'monthly').catch(
      () => null,
    );
    const usageYearlyTask = loadOmiUsagePeriod(backend, 'yearly').catch(
      () => null,
    );
    const usageAllTimeTask = loadOmiUsagePeriod(backend, 'all_time').catch(
      () => null,
    );
    const fairUseTask = loadOmiFairUseStatus(backend).catch(() => null);
    const dailySummariesTask = loadOmiDailySummaries(backend).catch(() => []);
    const dailySummaryScheduleTask = loadOmiDailySummarySchedule(backend).catch(
      () => null,
    );
    const notificationFrequencyTask = loadOmiMentorNotificationSettings(
      backend,
    ).catch(() => null);
    const transcriptionPreferencesTask = loadOmiTranscriptionPreferences(
      backend,
    ).catch(() => null);
    const developerKeysTask = loadOmiDevApiKeys(backend).catch(() => []);
    const mcpKeysTask = loadOmiMcpApiKeys(backend).catch(() => []);
    const importJobsTask = loadOmiImportJobs(backend).catch(() => []);
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
    const names = await peopleTask;
    const nextTaskIntegrations = await taskIntegrationsTask;
    const nextIntegrations = await integrationsTask;
    const nextAppChangelogs = await appChangelogsTask;
    const nextUsageMonthly = await usageMonthlyTask;
    const nextUsageYearly = await usageYearlyTask;
    const nextUsageAllTime = await usageAllTimeTask;
    const status = await fairUseTask;
    const summaries = await dailySummariesTask;
    const schedule = await dailySummaryScheduleTask;
    const frequency = await notificationFrequencyTask;
    const transcription = await transcriptionPreferencesTask;
    const nextDeveloperKeys = await developerKeysTask;
    const nextMcpKeys = await mcpKeysTask;
    const nextImportJobs = await importJobsTask;
    if (!current()) {
      return;
    }
    setPeopleNames(peopleNameRows(names));
    setTaskIntegrations(nextTaskIntegrations);
    setIntegrations(nextIntegrations);
    setAppChangelogs(nextAppChangelogs);
    setUsageMonthly(nextUsageMonthly);
    setUsageYearly(nextUsageYearly);
    setUsageAllTime(nextUsageAllTime);
    setFairUse(fairUseCopy(status));
    setDailySummaries(dailySummaryCopy(summaries));
    setDailySummarySchedule(dailySummaryScheduleCopy(schedule));
    setNotificationFrequency(
      mentorNotificationFrequencyCopy(frequency?.frequency),
    );
    setAutomaticTranslation(
      automaticTranslationCopy(transcription?.singleLanguageMode),
    );
    setCustomVocabulary(customVocabularyCopy(transcription?.vocabulary));
    setDeveloperKeys(developerKeysCopy(nextDeveloperKeys, 'Developer key'));
    setMcpKeys(
      developerKeysCopy(
        nextMcpKeys.map(key => ({name: key.name, keyPrefix: key.keyPrefix})),
        'MCP key',
      ),
    );
    setImportJobs(importJobsCopy(nextImportJobs));
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
      if (isPrivacyWriteKind(id) && !cloudErrorCanRetry(reason)) {
        setPrivacyWritesAvailable(current => ({...current, [id]: false}));
      }
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
              copy={accountFieldCopy(
                snapshot.profile.name,
                'Name not set on this account.',
              )}
              title="Name"
            />
            <SettingRow
              copy={accountFieldCopy(
                snapshot.profile.email,
                'Email not set on this account.',
              )}
              title="Email"
            />
            <SettingRow
              copy={accountFieldCopy(
                snapshot.profile.uid,
                'Account id unavailable',
              )}
              title="Account id"
            />
            {visibleDisplayText(snapshot.profile.company ?? '') !== '' && (
              <SettingRow
                copy={visibleDisplayText(snapshot.profile.company ?? '')}
                title="Company"
              />
            )}
            {visibleDisplayText(snapshot.profile.job ?? '') !== '' && (
              <SettingRow
                copy={visibleDisplayText(snapshot.profile.job ?? '')}
                title="Job"
              />
            )}
            {snapshot.profile.dataProtectionLevel !== null && (
              <SettingRow
                copy={dataProtectionCopy(snapshot.profile.dataProtectionLevel)}
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
              subscriptionPlanCopy(snapshot.subscription.plan),
              subscriptionStatusCopy(snapshot.subscription.status),
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
        {usageStatsCopy(snapshot.usage)?.map(row => (
          <SettingRow copy={row.copy} key={row.title} title={row.title} />
        ))}
        {usagePeriodStatsCopy('This month', usageMonthly)?.map(row => (
          <SettingRow copy={row.copy} key={row.title} title={row.title} />
        ))}
        {usagePeriodStatsCopy('This year', usageYearly)?.map(row => (
          <SettingRow copy={row.copy} key={row.title} title={row.title} />
        ))}
        {usagePeriodStatsCopy('All time', usageAllTime)?.map(row => (
          <SettingRow copy={row.copy} key={row.title} title={row.title} />
        ))}
        {subscriptionPeriodCopy(snapshot.subscription)?.map(row => (
          <SettingRow copy={row.copy} key={row.title} title={row.title} />
        ))}
        {primaryLanguageCopy(snapshot.language, snapshot.languageNames) !==
        null ? (
          <SettingRow
            copy={
              primaryLanguageCopy(snapshot.language, snapshot.languageNames) ??
              ''
            }
            title="Primary language"
          />
        ) : null}
        {automaticTranslation.map((row, index) => (
          <SettingRow
            copy={row.copy}
            key={`${row.title}-${index}`}
            title={row.title}
          />
        ))}
        {customVocabulary.map((row, index) => (
          <SettingRow
            copy={row.copy}
            key={`${row.title}-${index}`}
            title={row.title}
          />
        ))}
        {peopleNames.map(person => (
          <SettingRow copy={person.name} key={person.id} title="People" />
        ))}
        {taskIntegrations.map(row => (
          <SettingRow
            copy={taskIntegrationRowCopy(row)}
            key={row.key}
            title="Task integrations"
          />
        ))}
        {integrations.map(row => (
          <SettingRow copy={row.name} key={row.key} title="Integrations" />
        ))}
        {fairUse?.map((row, index) => (
          <SettingRow
            copy={row.copy}
            key={`${row.title}-${index}`}
            title={row.title}
          />
        ))}
        {notificationFrequency.map((row, index) => (
          <SettingRow
            copy={row.copy}
            key={`${row.title}-${index}`}
            title={row.title}
          />
        ))}
        {dailySummarySchedule.map((row, index) => (
          <SettingRow
            copy={row.copy}
            key={`${row.title}-${index}`}
            title={row.title}
          />
        ))}
        {dailySummaries.map((row, index) => (
          <SettingRow
            copy={row.copy}
            key={`${row.title}-${index}`}
            title={row.title}
          />
        ))}
        {appChangelogs.map(row => (
          <SettingRow copy={row.copy} key={row.key} title={row.title} />
        ))}
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
            action={
              privacyWritesAvailable.recording
                ? () => {
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
                  }
                : undefined
            }
            actionLabel={
              privacyWritesAvailable.recording
                ? snapshot.storeRecordingPermission
                  ? 'Turn off recording storage'
                  : 'Turn on recording storage'
                : undefined
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
              snapshot.trainingOptedIn || !privacyWritesAvailable.training
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
            actionLabel={
              snapshot.trainingOptedIn || !privacyWritesAvailable.training
                ? undefined
                : 'Opt in'
            }
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
            action={
              privacyWritesAvailable.sync
                ? () => {
                    const backend = omiBackend;
                    if (backend === undefined || backend === null) {
                      return;
                    }
                    runAction('sync', () =>
                      setPrivateCloudSync(backend, !snapshot.privateCloudSync),
                    ).catch(() => undefined);
                  }
                : undefined
            }
            actionLabel={
              privacyWritesAvailable.sync
                ? snapshot.privateCloudSync
                  ? 'Turn off private cloud sync'
                  : 'Turn on private cloud sync'
                : undefined
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
    snapshot === null ? null : (
      <>
        {snapshot.webhooks === null ? (
          <Text style={styles.projectionEmptyCopy}>
            {snapshot.webhooksError ??
              'Developer webhook status is unavailable.'}
          </Text>
        ) : snapshot.webhooks.length === 0 ? (
          <Text style={styles.projectionEmptyCopy}>
            No developer webhooks were returned.
          </Text>
        ) : (
          snapshot.webhooks.map(webhook => (
            <SettingRow
              copy={developerWebhookRowCopy(webhook)}
              key={webhook.type}
              title={developerWebhookTypeCopy(webhook.type)}
            />
          ))
        )}
        {developerKeys.map((row, index) => (
          <SettingRow
            copy={row.copy}
            key={`dev-key-${index}`}
            title={row.title}
          />
        ))}
        {mcpKeys.map((row, index) => (
          <SettingRow
            copy={row.copy}
            key={`mcp-key-${index}`}
            title={row.title}
          />
        ))}
        {importJobs.map(row => (
          <SettingRow copy={row.copy} key={row.key} title={row.title} />
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
                copy={connectionIdentityCopy(serviceSettings.identity)}
              />
              {serviceSettings.entitlement !== null ? (
                <SettingRow
                  title="Plan"
                  copy={accountFieldCopy(
                    serviceSettings.entitlement.planLabel,
                    'Plan unavailable',
                  )}
                />
              ) : null}
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
                  } used${
                    serviceSettings.entitlement.limitReached
                      ? ' · Limit reached'
                      : ''
                  }`}
                />
              ) : (
                <SettingRow
                  title="Usage"
                  copy={`Usage allowance is unavailable for this connection.${
                    serviceSettings.entitlement?.limitReached
                      ? ' · Limit reached'
                      : ''
                  }`}
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
