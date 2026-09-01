import {NativeModules} from 'react-native';
import {
  parseSoftwarePlane,
  SOFTWARE_PLANE_DEFAULTS_KEY,
  type SoftwarePlane,
  validateV5BackendUrl,
} from './v5BackendOrigin';

export const desktopPreferenceKeys = {
  softwarePlane: SOFTWARE_PLANE_DEFAULTS_KEY,
  screenCapture: 'screenAnalysisEnabled',
  audioMode: 'audioRecordingMode',
  interfaceSounds: 'omi.sound.effectsEnabled',
  fontScale: 'fontScale',
  notificationsEnabled: 'notifications_enabled',
  rewindRetentionDays: 'rewindRetentionDays',
  meetingNoteScreenshots: 'meetingNoteScreenshotsEnabled',
  floatingBar: 'askOmiBarEnabled',
  transcriptionAutoDetect: 'transcriptionAutoDetect',
  vadGate: 'vadGateEnabled',
  openOmiShortcut: 'shortcut_askOmiEnabled',
  pushToTalk: 'shortcut_pttEnabled',
} as const;

export type AudioRecordingMode = 'off' | 'always' | 'meetings';
export type PermissionKind = 'screen' | 'microphone' | 'notifications';
export type PermissionState = 'unknown' | 'granted' | 'denied';

export type DesktopPreferences = {
  softwarePlane: SoftwarePlane;
  screenCapture: boolean;
  audioMode: AudioRecordingMode;
  interfaceSounds: boolean;
  fontScale: number;
  notificationsEnabled: boolean;
  rewindRetentionDays: number;
  meetingNoteScreenshots: boolean;
  floatingBar: boolean;
  transcriptionAutoDetect: boolean;
  vadGate: boolean;
  openOmiShortcut: boolean;
  pushToTalk: boolean;
  stampedV5Origin: string | null;
};

type DesktopCommandsNative = {
  loadDesktopPreferences(): Promise<Record<string, unknown>>;
  setDesktopPreference(
    key: string,
    value: boolean | number | string,
  ): Promise<Record<string, unknown>>;
  permissionStatus(): Promise<Record<PermissionKind, PermissionState>>;
  requestPermission(kind: PermissionKind): Promise<PermissionState>;
};

type BackendPlaneNative = {
  getSoftwarePlane(): Promise<string>;
  setSoftwarePlane(plane: string): Promise<string>;
  stampedV5BackendOrigin(): Promise<string | null>;
};

const memoryPreferences: DesktopPreferences = {
  softwarePlane: 'old',
  screenCapture: false,
  audioMode: 'off',
  interfaceSounds: true,
  fontScale: 100,
  notificationsEnabled: false,
  rewindRetentionDays: 14,
  meetingNoteScreenshots: true,
  floatingBar: true,
  transcriptionAutoDetect: true,
  vadGate: true,
  openOmiShortcut: true,
  pushToTalk: true,
  stampedV5Origin: null,
};

function desktopCommands(): DesktopCommandsNative | undefined {
  return NativeModules.OmiDesktopCommands as DesktopCommandsNative | undefined;
}

function backendPlane(): BackendPlaneNative | undefined {
  return NativeModules.OmiBackend as BackendPlaneNative | undefined;
}

export function parseAudioRecordingMode(value: unknown): AudioRecordingMode {
  if (value === 'always' || value === 'meetings') {
    return value;
  }
  return 'off';
}

export function parseStampedV5Origin(value: unknown): string | null {
  if (typeof value !== 'string' || value.length === 0) {
    return null;
  }
  return validateV5BackendUrl(value)?.origin ?? null;
}

export function defaultDesktopPreferences(): DesktopPreferences {
  return {...memoryPreferences};
}

function snapshotFromRecord(
  record: Record<string, unknown>,
  stampedV5Origin: string | null,
): DesktopPreferences {
  return {
    softwarePlane: parseSoftwarePlane(record.softwarePlane ?? record.plane),
    screenCapture: record.screenCapture === true,
    audioMode: parseAudioRecordingMode(record.audioMode),
    interfaceSounds: record.interfaceSounds !== false,
    fontScale:
      typeof record.fontScale === 'number' && record.fontScale >= 50
        ? Math.min(record.fontScale, 200)
        : 100,
    notificationsEnabled: record.notificationsEnabled === true,
    rewindRetentionDays:
      typeof record.rewindRetentionDays === 'number'
        ? record.rewindRetentionDays
        : 14,
    meetingNoteScreenshots: record.meetingNoteScreenshots !== false,
    floatingBar: record.floatingBar !== false,
    transcriptionAutoDetect: record.transcriptionAutoDetect !== false,
    vadGate: record.vadGate !== false,
    openOmiShortcut: record.openOmiShortcut !== false,
    pushToTalk: record.pushToTalk !== false,
    stampedV5Origin,
  };
}

export async function loadDesktopPreferences(): Promise<DesktopPreferences> {
  const commands = desktopCommands();
  const plane = backendPlane();
  const stamped =
    plane === undefined
      ? null
      : parseStampedV5Origin(await plane.stampedV5BackendOrigin());
  if (commands === undefined) {
    return {
      ...memoryPreferences,
      softwarePlane:
        plane === undefined
          ? memoryPreferences.softwarePlane
          : parseSoftwarePlane(await plane.getSoftwarePlane()),
      stampedV5Origin: stamped,
    };
  }
  const record = await commands.loadDesktopPreferences();
  const softwarePlane =
    plane === undefined
      ? parseSoftwarePlane(record.softwarePlane)
      : parseSoftwarePlane(await plane.getSoftwarePlane());
  return snapshotFromRecord({...record, softwarePlane}, stamped);
}

export async function setDesktopPreference<
  Key extends Exclude<keyof DesktopPreferences, 'stampedV5Origin'>,
>(key: Key, value: DesktopPreferences[Key]): Promise<DesktopPreferences> {
  if (key === 'softwarePlane') {
    const plane = backendPlane();
    if (plane !== undefined) {
      await plane.setSoftwarePlane(String(value));
    } else {
      memoryPreferences.softwarePlane = parseSoftwarePlane(value);
    }
    return loadDesktopPreferences();
  }
  const commands = desktopCommands();
  if (commands === undefined) {
    (memoryPreferences as Record<string, unknown>)[key] = value;
    return loadDesktopPreferences();
  }
  const record = await commands.setDesktopPreference(key, value as never);
  return snapshotFromRecord(
    record,
    (await loadDesktopPreferences()).stampedV5Origin,
  );
}

export async function loadPermissionStatus(): Promise<
  Record<PermissionKind, PermissionState>
> {
  const commands = desktopCommands();
  if (commands === undefined) {
    return {screen: 'unknown', microphone: 'unknown', notifications: 'unknown'};
  }
  return commands.permissionStatus();
}

export async function requestDesktopPermission(
  kind: PermissionKind,
): Promise<PermissionState> {
  const commands = desktopCommands();
  if (commands === undefined) {
    return 'unknown';
  }
  return commands.requestPermission(kind);
}
