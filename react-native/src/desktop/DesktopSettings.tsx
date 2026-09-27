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
import {
  type DesktopTokens,
  useDesktopTheme,
  useDesktopStyleSheets,
} from './DesktopTheme';

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
  softwarePlaneLocked: boolean;
};

const PANE_ITEM_HEIGHT = 40;
const PANE_ITEM_GAP = 4;
const PANE_PILL_RADIUS = 10;

const TOGGLE_WIDTH = 44;
const TOGGLE_HEIGHT = 26;
const TOGGLE_THUMB = 20;
const TOGGLE_TRAVEL = TOGGLE_WIDTH - TOGGLE_THUMB - 6;

/**
 * The house toggle: a glass pill with a sliding thumb, matching the nav pill
 * and segmented controls instead of the system switch. Role stays "switch" so
 * accessibility behavior is unchanged.
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
  const styles = useDesktopStyleSheets(createStyles);
  const reduceMotion = useReduceMotion();
  const thumb = useRef(new Animated.Value(value ? 1 : 0)).current;
  const [pressed, setPressed] = useState(false);
  useEffect(() => {
    if (reduceMotion) {
      thumb.setValue(value ? 1 : 0);
      return;
    }
    const animation = Animated.timing(thumb, {
      toValue: value ? 1 : 0,
      duration: pressed ? 220 : 160,
      easing: Easing.out(Easing.cubic),
      useNativeDriver: true,
      isInteraction: false,
    });
    animation.start();
    return () => animation.stop();
  }, [value, pressed, reduceMotion, thumb]);
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
      onPressIn={() => setPressed(true)}
      onPressOut={() => setPressed(false)}
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
              {
                scale: thumb.interpolate({
                  inputRange: [0, 1],
                  outputRange: [1, 1.05],
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
  copy,
  title,
  trailing,
}: {
  action?: () => void;
  actionLabel?: string;
  copy: string;
  title: string;
  trailing?: React.ReactNode;
}) {
  const styles = useDesktopStyleSheets(createStyles);
  return (
    <View style={styles.row}>
      <View style={styles.rowCopy}>
        <Text style={styles.rowTitle}>{title}</Text>
        <Text style={styles.rowMeta}>{copy}</Text>
      </View>
      {trailing ? <View style={styles.rowControl}>{trailing}</View> : null}
      {action !== undefined && actionLabel !== undefined ? (
        <FocusPressable
          accessibilityLabel={actionLabel}
          accessibilityRole="button"
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
  onChange,
  options,
  value,
}: {
  disabled?: boolean;
  onChange: (value: Value) => void;
  options: readonly Value[];
  value: Value;
}) {
  const styles = useDesktopStyleSheets(createStyles);
  return (
    <View style={styles.segments}>
      {options.map(option => (
        <FocusPressable
          accessibilityRole="button"
          accessibilityState={{disabled, selected: value === option}}
          disabled={disabled}
          key={option}
          onPress={() => {
            if (value !== option) {
              onChange(option);
            }
          }}
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
            {option}
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
  const {tokens: token} = useDesktopTheme();
  const styles = useDesktopStyleSheets(createStyles);
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
                color={pane === label ? token.color.ink : token.color.inkMuted}
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
  session,
  signingIn,
  softwarePlaneLocked,
}: Props) {
  const styles = useDesktopStyleSheets(createStyles);
  const [pane, setPane] = useState<DesktopSettingsPane>('General');
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
          prefs.appearance === 'light'
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
                  value === 'Light' ? 'light' : 'dark',
                );
              });
            }}
            options={['Dark', 'Light'] as const}
            value={prefs.appearance === 'light' ? 'Light' : 'Dark'}
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
        actionLabel={
          session === 'ready'
            ? 'Sign out'
            : signingIn
            ? 'Signing in…'
            : 'Sign in'
        }
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
            <View style={styles.group}>{body}</View>
            {pane === 'General' ? deviceContent : null}
          </ShippingStage>
        </ScrollView>
      </View>
    </View>
  );
}

const createStyles = (token: DesktopTokens) => ({
  root: {
    flex: 1,
    flexDirection: 'row' as const,
    paddingHorizontal: 24,
    paddingTop: 8,
  },
  stage: {flexBasis: 'auto' as const, flexGrow: 0, flexShrink: 0, gap: 20},
  group: {
    backgroundColor: token.color.glassStrong,
    borderRadius: 18,
    overflow: 'hidden' as const,
    borderWidth: 1,
    borderColor: token.color.line,
  },
  sidebarTitle: {
    fontSize: 12,
    fontWeight: '600' as const,
    color: token.color.inkMuted,
    paddingHorizontal: 12,
    paddingTop: 6,
    paddingBottom: 22,
  },
  panes: {position: 'relative' as const},
  sidebar: {
    marginRight: 24,
    position: 'relative' as const,
    width: 182,
    flexShrink: 0,
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
    alignItems: 'center' as const,
    flexDirection: 'row' as const,
    gap: 10,
    height: PANE_ITEM_HEIGHT,
    justifyContent: 'flex-start' as const,
    marginBottom: PANE_ITEM_GAP,
    paddingHorizontal: 12,
  },
  paneText: {
    color: token.color.inkMuted,
    fontFamily: token.font,
    fontSize: token.type.caption,
    fontWeight: '500' as const,
    textAlign: 'left' as const,
  },
  paneTextActive: {color: token.color.ink},
  scroll: {flex: 1, minWidth: 0},
  content: {paddingBottom: 32},
  status: {
    color: token.color.inkMuted,
    fontFamily: token.font,
    fontSize: token.type.caption,
    marginBottom: 10,
  },
  row: {
    alignItems: 'center' as const,
    flexDirection: 'row' as const,
    flexWrap: 'wrap' as const,
    gap: 16,
    borderBottomWidth: 1,
    borderColor: token.color.line,
    minHeight: 90,
    padding: 20,
  },
  rowCopy: {flexGrow: 1, flexShrink: 1, flexBasis: 220},
  rowControl: {marginLeft: 'auto' as const, maxWidth: '100%' as const},
  rowTitle: {
    color: token.color.ink,
    fontFamily: token.font,
    fontSize: 14,
    fontWeight: '500' as const,
  },
  rowMeta: {
    color: token.color.inkMuted,
    fontFamily: token.font,
    fontSize: token.type.meta,
    lineHeight: 19,
    marginTop: 5,
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
  toggle: {
    alignItems: 'center' as const,
    borderColor: token.color.line,
    borderRadius: TOGGLE_HEIGHT / 2,
    borderWidth: 1,
    height: TOGGLE_HEIGHT,
    justifyContent: 'center' as const,
    paddingLeft: 3,
    width: TOGGLE_WIDTH,
  },
  toggleOn: {
    backgroundColor: token.color.ink,
    borderColor: token.color.ink,
  },
  toggleThumb: {
    backgroundColor: token.color.inkMuted,
    borderRadius: TOGGLE_THUMB / 2,
    height: TOGGLE_THUMB,
    width: TOGGLE_THUMB,
  },
  toggleThumbOn: {backgroundColor: token.color.dark},
  toggleDisabled: {opacity: 0.4},
  segments: {
    flexDirection: 'row' as const,
    flexWrap: 'wrap' as const,
    gap: 2,
    backgroundColor: token.color.glassQuiet,
    borderRadius: 10,
    padding: 3,
  },
  segment: {
    borderRadius: 10,
    minHeight: 28,
    justifyContent: 'center' as const,
    paddingHorizontal: 10,
  },
  segmentActive: {backgroundColor: token.color.glassStrong},
  segmentText: {
    color: token.color.inkMuted,
    fontFamily: token.font,
    fontSize: token.type.caption,
    fontWeight: '600' as const,
    textTransform: 'capitalize' as const,
  },
  segmentTextActive: {color: token.color.ink},
});
