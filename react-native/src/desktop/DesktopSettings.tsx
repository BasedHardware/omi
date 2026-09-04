import React, {useCallback, useEffect, useRef, useState} from 'react';
import {Animated, ScrollView, Switch, Text, View} from 'react-native';
import {useReduceMotion} from '../app/useReduceMotion';
import {desktopEaseSmoothOut} from './desktopMotion';
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
import {desktopTokens as token} from './tokens';

type Props = {
  session: DesktopSession;
  signingIn: boolean;
  onSignIn: () => void;
  onSignOut: () => void;
  onWorkspaceReload?: () => void;
};

const PANE_ITEM_HEIGHT = 40;
const PANE_ITEM_GAP = 12;
const PANE_PILL_RADIUS = 14;

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
          onPress={action}
          style={({pressed}) => [styles.action, pressed && styles.pressed]}>
          <Text style={styles.actionText}>{actionLabel}</Text>
        </FocusPressable>
      ) : null}
    </View>
  );
}

function Segmented<Value extends string>({
  onChange,
  options,
  value,
}: {
  onChange: (value: Value) => void;
  options: readonly Value[];
  value: Value;
}) {
  return (
    <View style={styles.segments}>
      {options.map(option => (
        <FocusPressable
          accessibilityRole="button"
          accessibilityState={{selected: value === option}}
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
  onSignIn,
  onSignOut,
  onWorkspaceReload,
  session,
  signingIn,
}: Props) {
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
    const [nextPrefs, nextPermissions] = await Promise.all([
      loadDesktopPreferences(),
      loadPermissionStatus(),
    ]);
    if (seq !== reloadSeqRef.current) {
      return;
    }
    setPrefs(nextPrefs);
    setPermissions(nextPermissions);
    let nextAccount: AccountSettingsSnapshot | null = null;
    if (backend !== undefined && backend !== null && session === 'ready') {
      try {
        nextAccount = await loadAccountSettings(backend);
      } catch {
        nextAccount = null;
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
    reload().catch(() => undefined);
  };

  const runAction = (action: () => Promise<void>) => {
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
          setActionStatus('Settings change could not be saved. Try again.');
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

  const general = (
    <>
      <Row
        copy={
          permissions.screen === 'granted'
            ? 'Screen capture is allowed on this Mac.'
            : 'Omi needs Screen Recording to keep what you see.'
        }
        title="Screen Capture"
        trailing={
          <Switch
            onValueChange={value => {
              if (value) {
                runAction(async () => {
                  await request('screen');
                });
                return;
              }
              runAction(() => setPref('screenCapture', false));
            }}
            value={prefs.screenCapture && permissions.screen !== 'denied'}
          />
        }
      />
      <Row
        copy="Off, always, or only while a meeting is in the foreground."
        title="Audio Recording"
        trailing={
          <Segmented<AudioRecordingMode>
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
          session === 'ready'
            ? account?.profile?.email ?? 'Signed in to Omi'
            : 'Sign in to load conversations and memories.'
        }
        title="Account"
        action={session === 'ready' ? onSignOut : onSignIn}
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
        <Row copy="Plan details load after sign-in." title="Current plan" />
      )}
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

  const advanced = (
    <Row
      copy={
        prefs.softwarePlane === 'new'
          ? prefs.stampedV5Origin != null
            ? 'New sends v5 chat, capture, conversations, memories, tasks, and settings to the stamped origin. Account, apps, and privacy controls still use production api.omi.me.'
            : 'New is selected, but no valid stamped v5 origin is configured.'
          : 'Old uses production api.omi.me. This v5 desktop requires New for chat, memories, and tasks.'
      }
      title="Backend"
      trailing={
        <Segmented
          onChange={value => {
            runAction(async () => {
              await setPref('softwarePlane', value === 'new' ? 'new' : 'old');
              onWorkspaceReload?.();
            });
          }}
          options={['old', 'new'] as const}
          value={prefs.softwarePlane}
        />
      }
    />
  );

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
