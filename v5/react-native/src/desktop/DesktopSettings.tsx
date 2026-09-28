import React, {useCallback, useEffect, useRef, useState} from 'react';
import type {useRewindCapture} from '../app/useRewindCapture';
import type {useAmbientAudio} from '../app/useAmbientAudio';
import {Animated, Easing, ScrollView, Text, View} from 'react-native';
import {MaterialIcon, type MaterialIconName} from '../ui/MaterialIcon';

import {useReduceMotion} from '../app/useReduceMotion';
import {desktopEaseSmoothOut} from './desktopMotion';
import {AppsPage} from './DesktopPages';
import {
  loadAccountSettings,
  setPrivateCloudSync,
  setStoreRecordingPermission,
  type AccountSettingsSnapshot,
} from '../desktopCloudClient';
import {
  defaultDesktopPreferences,
  loadDesktopPreferences,
  loadPermissionStatus,
  requestDesktopPermission,
  setDesktopPreference,
  type AudioRecordingMode,
  type DesktopPreferences,
  type DesktopUiVersion,
  type LiveVoiceProvider,
  type PermissionKind,
  type PermissionState,
} from '../desktopSettingsClient';
import {omiBackend} from '../omiNative';
import {FocusPressable} from '../ui/Pressable';
import {
  desktopMotion,
  desktopSettingsPanes,
  type DesktopSession,
  type DesktopSettingsPane,
} from './desktopChrome';
import {ShippingStage} from './ShippingStage';
import {OmiButton} from '../design/primitives';
import {useOmiStyles, useOmiTheme} from '../design/OmiTheme';
import {omiMotion, type OmiTheme} from '../design/tokens';

type Props = {
  capture?: ReturnType<typeof useRewindCapture>;
  ambient?: ReturnType<typeof useAmbientAudio>;
  deviceContent?: React.ReactNode;
  session: DesktopSession;
  signingIn: boolean;
  onSignIn: () => void;
  onSignOut: () => void | Promise<void>;
  onWorkspaceReload?: () => void;
  onPreferencesChange?: (prefs: DesktopPreferences) => void;
  /** Live interface-version switch (Settings → General → Interface). */
  onUiVersionChange?: (version: DesktopUiVersion) => void;
  softwarePlaneLocked: boolean;
  /** Initial pane for previews and screenshots; users start at General. */
  initialPane?: DesktopSettingsPane;
};

const PANE_ITEM_HEIGHT = 40;
const PANE_ITEM_GAP = 4;
const PANE_PILL_RADIUS = 12;

const TOGGLE_WIDTH = 38;
const TOGGLE_HEIGHT = 22;
const TOGGLE_THUMB = 18;
const TOGGLE_INSET = (TOGGLE_HEIGHT - TOGGLE_THUMB) / 2;
const TOGGLE_TRAVEL = TOGGLE_WIDTH - TOGGLE_THUMB - 2 * TOGGLE_INSET;

/**
 * The house switch: a track with a knob, ink track when on (design
 * language: toggles look like switches, selection is ink). Role stays
 * "switch" so accessibility behavior is unchanged. Motion is the knob
 * sliding only; no scale bounce, and none under Reduce Motion.
 */
function GlassToggle({
  accessibilityLabel,
  disabled = false,
  onValueChange,
  value,
}: {
  accessibilityLabel: string;
  disabled?: boolean;
  onValueChange: (value: boolean) => void;
  value: boolean;
}) {
  const styles = useOmiStyles(createStyles);
  const reduceMotion = useReduceMotion();
  const thumb = useRef(new Animated.Value(value ? 1 : 0)).current;
  useEffect(() => {
    if (reduceMotion) {
      thumb.setValue(value ? 1 : 0);
      return;
    }
    const animation = Animated.timing(thumb, {
      toValue: value ? 1 : 0,
      duration: omiMotion.quick + 40,
      easing: Easing.out(Easing.cubic),
      useNativeDriver: true,
      isInteraction: false,
    });
    animation.start();
    return () => animation.stop();
  }, [value, reduceMotion, thumb]);
  return (
    <FocusPressable
      accessibilityLabel={accessibilityLabel}
      accessibilityRole="switch"
      accessibilityState={{disabled, checked: value}}
      disabled={disabled}
      onPress={() => {
        if (!disabled) {
          onValueChange(!value);
        }
      }}
      style={({pressed: active}) => [
        styles.toggle,
        value && styles.toggleOn,
        active && !disabled && styles.pressed,
        disabled && styles.toggleDisabled,
      ]}>
      <Animated.View
        style={[
          styles.toggleThumb,
          value && styles.toggleThumbOn,
          {
            transform: [
              {
                translateX: thumb.interpolate({
                  inputRange: [0, 1],
                  outputRange: [0, TOGGLE_TRAVEL],
                }),
              },
            ],
          },
        ]}
      />
    </FocusPressable>
  );
}
const paneInfo: Record<
  DesktopSettingsPane,
  {icon: MaterialIconName; title: string; description: string}
> = {
  General: {
    icon: 'settings',
    title: 'General',
    description: 'What Omi can remember, and when. You’re in control.',
  },
  'Account & Plan': {
    icon: 'person',
    title: 'Account & plan',
    description: 'Your Omi account and subscription.',
  },
  Transcription: {
    icon: 'graphic_eq',
    title: 'Transcription',
    description: 'Make room for the words that matter.',
  },
  Rewind: {
    icon: 'history',
    title: 'Recall',
    description: 'Choose how screen history stays on this Mac.',
  },
  'Alerts & Privacy': {
    icon: 'verified_user',
    title: 'Privacy',
    description: 'Decide what stays local and what goes to the cloud.',
  },
  Apps: {
    icon: 'extension',
    title: 'Apps & integrations',
    description: 'Your Omi app catalog and connected accounts.',
  },
  'AI & Automation': {
    icon: 'auto_awesome',
    title: 'AI & automation',
    description: 'The services behind your conversations with Omi.',
  },
  About: {
    icon: 'info',
    title: 'About Omi',
    description: 'A little less to remember. A little more room for you.',
  },
};

function Row({
  action,
  actionLabel,
  actionVariant = 'secondary',
  actionBusy = false,
  copy,
  title,
  trailing,
}: {
  action?: () => void;
  actionLabel?: string;
  actionVariant?: 'primary' | 'secondary';
  actionBusy?: boolean;
  copy: string;
  title: string;
  trailing?: React.ReactNode;
}) {
  const styles = useOmiStyles(createStyles);
  return (
    <View style={styles.row}>
      <View style={styles.rowCopy}>
        <Text style={styles.rowTitle}>{title}</Text>
        <Text style={styles.rowMeta}>{copy}</Text>
      </View>
      {trailing ? <View style={styles.rowControl}>{trailing}</View> : null}
      {action !== undefined && actionLabel !== undefined ? (
        <OmiButton
          compact
          disabled={actionBusy}
          label={actionLabel}
          onPress={action}
          variant={actionVariant}
        />
      ) : null}
    </View>
  );
}

function Segmented<Value extends string>({
  disabled = false,
  format = option => option,
  onChange,
  options,
  value,
}: {
  disabled?: boolean;
  /** Display label for an option value (values stay the stored strings). */
  format?: (option: Value) => string;
  onChange: (value: Value) => void;
  options: readonly Value[];
  value: Value;
}) {
  const styles = useOmiStyles(createStyles);
  return (
    <View style={styles.segments}>
      {options.map(option => (
        <FocusPressable
          accessibilityLabel={format(option)}
          accessibilityRole="button"
          accessibilityState={{disabled, selected: value === option}}
          disabled={disabled}
          key={option}
          onPress={() => {
            if (value !== option) {
              onChange(option);
            }
          }}
          style={state => [
            styles.segment,
            value === option
              ? styles.segmentActive
              : (state as {hovered?: boolean}).hovered && styles.segmentHover,
            state.pressed && styles.pressed,
          ]}>
          <Text
            style={[
              styles.segmentText,
              value === option && styles.segmentTextActive,
            ]}>
            {format(option)}
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
  const theme = useOmiTheme();
  const styles = useOmiStyles(createStyles);
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
      <Text style={styles.sidebarTitle}>Settings</Text>
      <View style={styles.panes}>
        <Animated.View
          pointerEvents="none"
          style={[styles.panePill, {transform: [{translateY}]}]}
        />
        {desktopSettingsPanes.map(label => {
          const icon = paneInfo[label].icon;
          return (
            <FocusPressable
              accessibilityLabel={label}
              accessibilityRole="tab"
              accessibilityState={{selected: pane === label}}
              key={label}
              onPress={() => onChange(label)}
              style={styles.paneItem}>
              <MaterialIcon
                name={icon}
                size={16}
                color={
                  pane === label ? theme.color.ink : theme.color.inkSecondary
                }
              />
              <Text
                style={[
                  styles.paneText,
                  pane === label && styles.paneTextActive,
                ]}>
                {label === 'Rewind' ? 'Recall' : label}
              </Text>
            </FocusPressable>
          );
        })}
      </View>
    </View>
  );
}

export function DesktopSettings({
  capture,
  ambient,
  deviceContent,
  onSignIn,
  onSignOut,
  onWorkspaceReload,
  onPreferencesChange,
  onUiVersionChange,
  session,
  signingIn,
  softwarePlaneLocked,
  initialPane = 'General',
}: Props) {
  const styles = useOmiStyles(createStyles);
  const [pane, setPane] = useState<DesktopSettingsPane>(initialPane);
  const [prefs, setPrefs] = useState<DesktopPreferences>(
    defaultDesktopPreferences,
  );
  const [permissions, setPermissions] = useState<
    Record<PermissionKind, PermissionState>
  >({microphone: 'unknown', notifications: 'unknown', screen: 'unknown'});
  const [account, setAccount] = useState<AccountSettingsSnapshot | null>(null);
  const [actionStatus, setActionStatus] = useState<string | null>(null);
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
    if (backend !== undefined && backend !== null && session === 'ready') {
      try {
        nextAccount = await loadAccountSettings(backend);
      } catch {
        nextAccount = {
          profile: null,
          profileError: 'Account details are unavailable.',
          subscription: null,
          subscriptionError: 'Plan is unavailable.',
          storeRecordingPermission: null,
          storeRecordingError: 'Cloud recording storage status is unavailable.',
          trainingOptedIn: null,
          trainingError: 'Training preference is unavailable.',
          privateCloudSync: null,
          privateCloudSyncError: 'Private cloud sync status is unavailable.',
          webhooks: null,
          webhooksError: 'Webhook status is unavailable.',
        };
      }
    }
    if (seq !== reloadSeqRef.current) {
      return;
    }
    setAccount(nextAccount);
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
    onPreferencesChange?.(next);
    reload().catch(() => undefined);
  };

  const runAction = (
    action: () => Promise<void>,
    failure = 'Settings change could not be saved. Try again.',
  ) => {
    const seq = ++actionSeqRef.current;
    setActionStatus('Saving settings…');
    action().then(
      () => {
        if (seq === actionSeqRef.current) {
          setActionStatus(null);
        }
      },
      () => {
        if (seq === actionSeqRef.current) {
          setActionStatus(failure);
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

  const liveVoiceLabel =
    prefs.liveVoiceProvider === 'gemini_live' ? 'Gemini Live' : 'GPT Live 1';
  const advanced = (
    <>
      <Row
        copy={
          softwarePlaneLocked
            ? 'Stop the active response before switching backends.'
            : prefs.softwarePlane === 'new'
            ? prefs.stampedV5Origin != null
              ? 'New sends v5 chat, capture, conversations, memories, and tasks to the stamped origin. Account, apps, privacy, and native Settings still use production api.omi.me.'
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
            value={
              prefs.softwarePlane === 'new' ? 'New backend' : 'Old backend'
            }
          />
        }
      />
      <Row
        copy={
          prefs.uiVersion === 'v5'
            ? 'Pages: rail destinations for Home, Chat, Conversations, Recall, and Tasks.'
            : 'Activity: one unified timeline with filters, grouping, and the omnibar up top.'
        }
        title="Interface"
        trailing={
          <Segmented
            onChange={value => {
              runAction(async () => {
                const next: DesktopUiVersion = value === 'v5' ? 'v5' : 'v5.1';
                await setPref('uiVersion', next);
                onUiVersionChange?.(next);
              });
            }}
            options={['v5.1', 'v5'] as const}
            value={prefs.uiVersion === 'v5' ? 'v5' : 'v5.1'}
          />
        }
      />
      <Row
        copy={
          prefs.liveVoiceProvider === 'gemini_live'
            ? 'Uses models/gemini-3.1-flash-live-preview over Gemini Live. Fails closed if GEMINI_API_KEY is missing on the server.'
            : 'Uses gpt-live-1 over OpenAI WebRTC. Fails closed if OPENAI_API_KEY is missing on the server.'
        }
        title="Live voice"
        trailing={
          <Segmented
            onChange={value => {
              runAction(async () => {
                const next: LiveVoiceProvider =
                  value === 'Gemini Live' ? 'gemini_live' : 'gpt_live';
                await setPref('liveVoiceProvider', next);
              });
            }}
            options={['GPT Live 1', 'Gemini Live'] as const}
            value={liveVoiceLabel}
          />
        }
      />
    </>
  );

  const general = (
    <>
      <Row
        copy={
          capture?.available
            ? capture.error ??
              (capture.capturing
                ? 'Saving screen history on this Mac.'
                : 'Start or stop saving screen history on this Mac.')
            : permissions.screen === 'granted'
            ? 'Screen capture is allowed on this Mac.'
            : 'Omi needs Screen Recording to keep what you see.'
        }
        title="Screen Capture"
        trailing={
          <GlassToggle
            accessibilityLabel="Screen capture setting"
            onValueChange={value => {
              if (capture?.available) {
                if (value) {
                  void capture.start();
                  void setPref('screenCapture', true);
                } else {
                  void capture.stop();
                  void setPref('screenCapture', false);
                }
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
            : ambient?.error ??
              ambient?.uploadError ??
              (ambient?.running
                ? ambient.pendingUploads > 0
                  ? `Listening on this Mac. ${
                      ambient.pendingUploads
                    } recording segment${
                      ambient.pendingUploads === 1 ? '' : 's'
                    } uploading.`
                  : 'Listening on this Mac. Audio uploads to your Omi account.'
                : 'Off, or always on. Meeting-only capture arrives soon.')
        }
        title="Audio Recording"
        trailing={
          <Segmented<AudioRecordingMode>
            format={mode =>
              mode === 'off' ? 'Off' : mode === 'always' ? 'Always' : 'Meetings'
            }
            onChange={value => {
              runAction(async () => {
                if (
                  value === 'off' ||
                  permissions.microphone === 'granted' ||
                  (await request('microphone')) === 'granted'
                ) {
                  await setPref('audioMode', value);
                }
              });
            }}
            options={
              prefs.audioMode === 'meetings'
                ? ['off', 'always', 'meetings']
                : ['off', 'always']
            }
            value={prefs.audioMode}
          />
        }
      />
      <Row
        copy={
          permissions.notifications === 'granted'
            ? 'Banners are allowed in System Settings.'
            : 'Ask macOS for notification permission.'
        }
        title="Notifications"
        trailing={
          <GlassToggle
            accessibilityLabel="Notifications setting"
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
      <Row
        copy={
          prefs.appearance === 'system'
            ? 'Follows macOS light and dark.'
            : prefs.appearance === 'light'
            ? 'Light chrome and surfaces across the app.'
            : 'Dark chrome and surfaces across the app.'
        }
        title="Appearance"
        trailing={
          <Segmented
            onChange={value => {
              runAction(async () => {
                await setPref(
                  'appearance',
                  value === 'System'
                    ? 'system'
                    : value === 'Light'
                    ? 'light'
                    : 'dark',
                );
              });
            }}
            options={['System', 'Light', 'Dark'] as const}
            value={
              prefs.appearance === 'system'
                ? 'System'
                : prefs.appearance === 'light'
                ? 'Light'
                : 'Dark'
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
          session === 'ready'
            ? account?.profile?.email ?? 'Signed in to Omi'
            : 'Sign in to load conversations and memories.'
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
        actionBusy={session !== 'ready' && signingIn}
        actionLabel={
          session === 'ready'
            ? 'Sign Out'
            : signingIn
            ? 'Signing In…'
            : 'Sign In'
        }
        actionVariant={session === 'ready' ? 'secondary' : 'primary'}
      />
      {account?.profile?.name != null ? (
        <Row copy={account.profile.name} title="Name" />
      ) : null}
      {account?.subscription != null ? (
        <Row
          copy={`${account.subscription.plan} · ${account.subscription.status}`}
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
    </>
  );

  const transcription = (
    <>
      <Row
        copy="Detect the spoken language automatically."
        title="Language Mode"
        trailing={
          <GlassToggle
            accessibilityLabel="Automatic language detection"
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
          <GlassToggle
            accessibilityLabel="Skip silence"
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
            onChange={value => {
              runAction(() => setPref('rewindRetentionDays', Number(value)));
            }}
            format={days => (days === '0' ? 'Forever' : `${days} days`)}
            options={['7', '14', '30', '0'] as const}
            value={String(prefs.rewindRetentionDays) as '7' | '14' | '30' | '0'}
          />
        }
      />
      <Row
        copy="Keep meeting screenshots with conversation notes."
        title="Meeting Screenshots"
        trailing={
          <GlassToggle
            accessibilityLabel="Meeting screenshots"
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
          account?.storeRecordingPermission === null || account === null
            ? account?.storeRecordingError ??
              'Cloud recording storage status is unavailable.'
            : account.storeRecordingPermission
            ? 'Cloud recording storage is on.'
            : 'Cloud recording storage is off until you allow it.'
        }
        title="Store Recordings"
        action={
          session === 'ready' &&
          backend != null &&
          typeof account?.storeRecordingPermission === 'boolean'
            ? () => {
                runAction(async () => {
                  await setStoreRecordingPermission(
                    backend,
                    !(account?.storeRecordingPermission ?? false),
                  );
                  await reload();
                });
              }
            : undefined
        }
        actionLabel="Update"
      />
      <Row
        copy={
          account?.privateCloudSync === null || account === null
            ? account?.privateCloudSyncError ??
              'Private cloud sync status is unavailable.'
            : account.privateCloudSync
            ? 'Private cloud sync is on.'
            : 'Private cloud sync is off.'
        }
        title="Private Cloud Sync"
        action={
          session === 'ready' &&
          backend != null &&
          typeof account?.privateCloudSync === 'boolean'
            ? () => {
                runAction(async () => {
                  await setPrivateCloudSync(
                    backend,
                    !(account?.privateCloudSync ?? false),
                  );
                  await reload();
                });
              }
            : undefined
        }
        actionLabel="Update"
      />
    </>
  );

  const apps = <AppsPage session={session} />;

  const about = (
    <>
      <Row copy="Omi v5 for Mac" title="Version" />
      <Row copy="https://omi.me" title="Website" />
      <Row copy="https://omi.me/privacy" title="Privacy Policy" />
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
      ? advanced
      : pane === 'Apps'
      ? apps
      : about;

  return (
    <View style={styles.root}>
      <SettingsNav onChange={setPane} pane={pane} />
      <View style={styles.scroll}>
        <ScrollView
          scrollEventThrottle={16}
          contentContainerStyle={styles.content}>
          {actionStatus !== null ? (
            <Text
              accessibilityLabel="Settings action status"
              accessibilityLiveRegion="polite"
              style={styles.status}>
              {actionStatus}
            </Text>
          ) : null}
          <ShippingStage stageKey={pane} variant="page" style={styles.stage}>
            {pane === 'Apps' ? (
              // The gallery brings its own tabs and states; it is not a
              // settings group.
              body
            ) : (
              <View style={styles.group}>
                <View style={styles.groupRows}>{body}</View>
              </View>
            )}
            {pane === 'General' ? deviceContent : null}
          </ShippingStage>
        </ScrollView>
      </View>
    </View>
  );
}

const createStyles = (t: OmiTheme) => ({
  root: {
    flex: 1,
    flexDirection: 'row' as const,
    paddingHorizontal: t.layout.pageGutter.desktop,
    paddingTop: t.space.sm,
  },
  stage: {
    flexBasis: 'auto' as const,
    flexGrow: 0,
    flexShrink: 0,
    gap: t.space.xl,
  },
  // One grouped card on the glass: a fill, no shadow, rows split by
  // separators. The inner -1 margin hides the first row's top rule.
  group: {
    backgroundColor: t.color.fill,
    borderRadius: t.radius.card - 4,
    overflow: 'hidden' as const,
  },
  groupRows: {marginTop: -1},
  sidebarTitle: {
    ...t.type.footnote,
    fontWeight: '600' as const,
    color: t.color.inkSecondary,
    paddingHorizontal: t.space.md,
    paddingTop: t.space.xs + 2,
    paddingBottom: t.space.lg,
  },
  panes: {position: 'relative' as const},
  sidebar: {
    marginRight: t.space.xxl,
    position: 'relative' as const,
    width: 182,
    flexShrink: 0,
  },
  panePill: {
    backgroundColor: t.color.fillSelected,
    borderRadius: PANE_PILL_RADIUS,
    height: PANE_ITEM_HEIGHT,
    left: 0,
    position: 'absolute' as const,
    right: 0,
    top: 0,
  },
  paneItem: {
    alignItems: 'center' as const,
    flexDirection: 'row' as const,
    gap: t.space.sm + 2,
    height: PANE_ITEM_HEIGHT,
    justifyContent: 'flex-start' as const,
    marginBottom: PANE_ITEM_GAP,
    paddingHorizontal: t.space.md,
  },
  paneText: {
    ...t.type.subhead,
    color: t.color.inkSecondary,
    textAlign: 'left' as const,
  },
  paneTextActive: {color: t.color.ink, fontWeight: '500' as const},
  scroll: {flex: 1, minWidth: 0},
  content: {
    paddingBottom: t.space.section,
    maxWidth: t.layout.listColumn,
    width: '100%' as const,
  },
  status: {
    ...t.type.footnote,
    color: t.color.inkSecondary,
    marginBottom: t.space.sm + 2,
  },
  row: {
    alignItems: 'center' as const,
    flexDirection: 'row' as const,
    flexWrap: 'wrap' as const,
    gap: t.space.lg,
    borderTopWidth: 1,
    borderColor: t.color.separator,
    minHeight: 60,
    paddingHorizontal: t.space.lg,
    paddingVertical: t.space.md,
  },
  rowCopy: {flexGrow: 1, flexShrink: 1, flexBasis: 220, gap: t.space.xxs},
  rowControl: {marginLeft: 'auto' as const, maxWidth: '100%' as const},
  rowTitle: {...t.type.body, fontWeight: '500' as const, color: t.color.ink},
  rowMeta: {...t.type.footnote, color: t.color.inkSecondary},
  pressed: {opacity: t.motion.pressedOpacity},
  toggle: {
    backgroundColor: t.color.hairline,
    borderRadius: t.radius.pill,
    height: TOGGLE_HEIGHT,
    justifyContent: 'center' as const,
    paddingHorizontal: TOGGLE_INSET,
    width: TOGGLE_WIDTH,
  },
  toggleOn: {backgroundColor: t.color.ink},
  toggleThumb: {
    // White knob on the off track in light; the light ink knob in dark.
    backgroundColor: t.scheme === 'light' ? t.color.surface : t.color.ink,
    borderRadius: t.radius.pill,
    height: TOGGLE_THUMB,
    width: TOGGLE_THUMB,
  },
  toggleThumbOn: {backgroundColor: t.color.onInk},
  toggleDisabled: {opacity: 0.4},
  segments: {
    flexDirection: 'row' as const,
    flexWrap: 'wrap' as const,
    gap: t.space.xxs,
    backgroundColor: t.color.fill,
    borderRadius: t.radius.pill,
    padding: t.space.xxs,
  },
  segment: {
    borderRadius: t.radius.pill,
    borderWidth: 1,
    borderColor: 'transparent',
    minHeight: t.size.controlCompact - 2,
    justifyContent: 'center' as const,
    paddingHorizontal: t.space.md,
  },
  segmentHover: {backgroundColor: t.color.fill},
  segmentActive: {
    backgroundColor: t.color.fillSelected,
    borderColor: t.color.separator,
  },
  segmentText: {
    ...t.type.footnote,
    fontWeight: '500' as const,
    color: t.color.inkSecondary,
  },
  segmentTextActive: {color: t.color.ink},
});
