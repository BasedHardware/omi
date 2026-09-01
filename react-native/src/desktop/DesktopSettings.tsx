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
  const backend = omiBackend;

  const reload = useCallback(async () => {
    const nextPrefs = await loadDesktopPreferences();
    const nextPermissions = await loadPermissionStatus();
    let nextAccount: AccountSettingsSnapshot | null = null;
    if (backend !== undefined && backend !== null && session === 'ready') {
      try {
        nextAccount = await loadAccountSettings(backend);
      } catch {
        nextAccount = null;
      }
    }
    return {nextAccount, nextPermissions, nextPrefs};
  }, [backend, session]);

  useEffect(() => {
    let active = true;
    reload()
      .then(snapshot => {
        if (!active) {
          return;
        }
        setPrefs(snapshot.nextPrefs);
        setPermissions(snapshot.nextPermissions);
        setAccount(snapshot.nextAccount);
      })
      .catch(() => undefined);
    return () => {
      active = false;
    };
  }, [reload]);

  const setPref = async <
    Key extends Exclude<keyof DesktopPreferences, 'stampedV5Origin'>,
  >(
    key: Key,
    value: DesktopPreferences[Key],
  ) => {
    setPrefs(await setDesktopPreference(key, value));
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
                request('screen').catch(() => undefined);
                return;
              }
              setPref('screenCapture', false).catch(() => undefined);
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
              if (value !== 'off') {
                request('microphone').catch(() => undefined);
              }
              setPref('audioMode', value).catch(() => undefined);
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
                request('notifications').catch(() => undefined);
                return;
              }
              setPref('notificationsEnabled', false).catch(() => undefined);
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
              setPref('transcriptionAutoDetect', value).catch(() => undefined);
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
              setPref('vadGate', value).catch(() => undefined);
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
              setPref('rewindRetentionDays', Number(value)).catch(
                () => undefined,
              );
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
              setPref('meetingNoteScreenshots', value).catch(() => undefined);
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
          account?.storeRecordingPermission
            ? 'Cloud recording storage is on.'
            : 'Cloud recording storage is off until you allow it.'
        }
        title="Store Recordings"
        action={
          session === 'ready' && backend != null
            ? () => {
                setStoreRecordingPermission(
                  backend,
                  !(account?.storeRecordingPermission ?? false),
                )
                  .then(() => reload())
                  .catch(() => undefined);
              }
            : undefined
        }
        actionLabel="Update"
      />
      <Row
        copy={
          account?.privateCloudSync
            ? 'Private cloud sync is on.'
            : 'Private cloud sync is off.'
        }
        title="Private Cloud Sync"
        action={
          session === 'ready' && backend != null
            ? () => {
                setPrivateCloudSync(
                  backend,
                  !(account?.privateCloudSync ?? false),
                )
                  .then(() => reload())
                  .catch(() => undefined);
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
            ? 'New uses the stamped v5 origin with the same OmiAuth keychain session as the shipping Mac app.'
            : 'New is selected, but no stamped v5 origin is configured, so requests stay on production api.omi.me with the same OmiAuth session.'
          : 'Old uses production api.omi.me. Session is the same OmiAuth keychain as the shipping Mac app.'
      }
      title="Backend"
      trailing={
        <Segmented
          onChange={value => {
            setPref('softwarePlane', value === 'new' ? 'new' : 'old')
              .then(() => {
                onWorkspaceReload?.();
              })
              .catch(() => undefined);
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
