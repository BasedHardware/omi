import React, {useCallback, useEffect, useState} from 'react';
import {ScrollView, Switch, Text, View} from 'react-native';
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
  desktopSettingsPanes,
  type DesktopSession,
  type DesktopSettingsPane,
} from './desktopChrome';
import {ShippingPressable} from './ShippingPressable';
import {ShippingStage} from './ShippingStage';
import {desktopTokens as token} from './tokens';

type Props = {
  session: DesktopSession;
  signingIn: boolean;
  onSignIn: () => void;
  onSignOut: () => void;
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

export function DesktopSettings({
  onSignIn,
  onSignOut,
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
      <Row
        copy="Play Omi interface sounds."
        title="Interface Sounds"
        trailing={
          <Switch
            onValueChange={value => {
              setPref('interfaceSounds', value).catch(() => undefined);
            }}
            value={prefs.interfaceSounds}
          />
        }
      />
      <Row
        copy={`${prefs.fontScale}% of the shipping system size.`}
        title="Font Size"
        trailing={
          <Segmented
            onChange={value => {
              setPref('fontScale', Number(value)).catch(() => undefined);
            }}
            options={['80', '100', '120'] as const}
            value={String(prefs.fontScale) as '80' | '100' | '120'}
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

  const floatingBar = (
    <Row
      copy="Show the floating Ask Omi bar."
      title="Show floating bar"
      trailing={
        <Switch
          onValueChange={value => {
            setPref('floatingBar', value).catch(() => undefined);
          }}
          value={prefs.floatingBar}
        />
      }
    />
  );

  const alerts = (
    <>
      <Row
        copy="Product notifications for tasks, memories, and summaries."
        title="Notifications"
        trailing={
          <Switch
            onValueChange={value => {
              setPref('notificationsEnabled', value).catch(() => undefined);
            }}
            value={prefs.notificationsEnabled}
          />
        }
      />
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

  const permissionPane = (
    <>
      {(
        [
          ['screen', 'Screen Recording'],
          ['microphone', 'Microphone'],
          ['notifications', 'Notifications'],
        ] as const
      ).map(([kind, title]) => (
        <Row
          action={() => {
            request(kind).catch(() => undefined);
          }}
          actionLabel={permissions[kind] === 'granted' ? 'Allowed' : 'Request'}
          copy={`macOS reports this permission as ${permissions[kind]}.`}
          key={kind}
          title={title}
        />
      ))}
    </>
  );

  const shortcuts = (
    <>
      <Row
        copy="Open the Omi window from anywhere."
        title="Open Omi Shortcut"
        trailing={
          <Switch
            onValueChange={value => {
              setPref('openOmiShortcut', value).catch(() => undefined);
            }}
            value={prefs.openOmiShortcut}
          />
        }
      />
      <Row
        copy="Hold to talk without opening the window."
        title="Push to Talk"
        trailing={
          <Switch
            onValueChange={value => {
              setPref('pushToTalk', value).catch(() => undefined);
            }}
            value={prefs.pushToTalk}
          />
        }
      />
    </>
  );

  const advanced = (
    <>
      <Row
        copy="Old uses production api.omi.me for chat, memories, tasks, profile, and session."
        title="Backend"
      />
      <Segmented
        onChange={value => {
          setPref('softwarePlane', value === 'new' ? 'new' : 'old').catch(
            () => undefined,
          );
        }}
        options={['old', 'new'] as const}
        value={prefs.softwarePlane}
      />
      <Row
        copy={
          prefs.stampedV5Origin == null
            ? 'New backend origin is not stamped on this build. OMI_V5_BACKEND_URL is read from the environment only.'
            : 'This build has a stamped new-backend origin. It is used only after you flip Advanced to new.'
        }
        title="New backend origin"
      />
    </>
  );

  const about = (
    <>
      <Row copy="Omi v5 for Mac" title="About" />
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
      : pane === 'Floating Bar'
      ? floatingBar
      : pane === 'Alerts & Privacy'
      ? alerts
      : pane === 'Permissions'
      ? permissionPane
      : pane === 'Shortcuts'
      ? shortcuts
      : pane === 'AI & Automation'
      ? advanced
      : about;

  return (
    <View style={styles.root}>
      <View accessibilityRole="tablist" style={styles.sidebar}>
        {desktopSettingsPanes.map(label => (
          <ShippingPressable
            accessibilityLabel={label}
            accessibilityRole="tab"
            accessibilityState={{selected: pane === label}}
            active={pane === label}
            key={label}
            onPress={() => setPane(label)}
            style={styles.paneItem}>
            <Text
              style={[
                styles.paneText,
                pane === label && styles.paneTextActive,
              ]}>
              {label}
            </Text>
          </ShippingPressable>
        ))}
      </View>
      <ScrollView contentContainerStyle={styles.content} style={styles.scroll}>
        <ShippingStage stageKey={pane} variant="page">
          <Text style={styles.pageTitle}>{pane}</Text>
          {pane === 'AI & Automation' ? (
            <Text style={styles.advancedLabel}>Advanced</Text>
          ) : null}
          {body}
        </ShippingStage>
      </ScrollView>
    </View>
  );
}

const styles = {
  root: {flex: 1, flexDirection: 'row' as const, gap: 16},
  sidebar: {gap: 4, width: 188},
  paneItem: {
    borderRadius: token.radius.chip,
    minHeight: 28,
    justifyContent: 'center' as const,
    paddingHorizontal: 12,
  },
  paneItemActive: {backgroundColor: token.color.glassSelected},
  paneText: {
    color: token.color.inkMuted,
    fontFamily: token.font,
    fontSize: token.type.caption,
    fontWeight: '600' as const,
  },
  paneTextActive: {color: token.color.ink},
  scroll: {flex: 1},
  content: {gap: 10, paddingBottom: 32},
  pageTitle: {
    color: token.color.ink,
    fontFamily: token.font,
    fontSize: token.type.title,
    fontWeight: '600' as const,
    marginBottom: 8,
  },
  advancedLabel: {
    color: token.color.inkMuted,
    fontFamily: token.font,
    fontSize: token.type.caption,
    fontWeight: '600' as const,
  },
  row: {
    alignItems: 'center' as const,
    backgroundColor: token.color.glassQuiet,
    borderRadius: 16,
    flexDirection: 'row' as const,
    gap: 12,
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
