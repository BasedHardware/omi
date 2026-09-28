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
  liveVoiceProvider: 'omi.live.voiceProvider',
  appearance: 'omi.appearance',
  uiVersion: 'omi.uiVersion',
  exploreProgress: 'omi.onboarding.exploreProgress',
} as const;

export type AudioRecordingMode = 'off' | 'always' | 'meetings';
/** 'system' follows macOS light/dark; the theme resolves it at render time. */
export type DesktopAppearance = 'dark' | 'light' | 'system';

/** Resolves an appearance preference to the theme actually drawn. */
export function resolveDesktopAppearance(
  appearance: DesktopAppearance,
  systemScheme: string | null | undefined,
): 'dark' | 'light' {
  if (appearance === 'system') {
    return systemScheme === 'light' ? 'light' : 'dark';
  }
  return appearance;
}

// Major interface revisions shipped in this app. v5 is the pages IA (rail
// destinations Home/Chat/Conversations/Recall/Tasks), v5.1 is the Activity IA
// (unified timeline + chrome filters). Settings switches between them.
export type DesktopUiVersion = 'v5' | 'v5.1';
export type LiveVoiceProvider = 'gpt_live' | 'gemini_live';
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
  liveVoiceProvider: LiveVoiceProvider;
  appearance: DesktopAppearance;
  uiVersion: DesktopUiVersion;
  exploreProgress: string;
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
  liveVoiceProvider: 'gpt_live',
  appearance: 'dark',
  uiVersion: 'v5.1',
  exploreProgress: '',
  stampedV5Origin: null,
};

function desktopCommands(): DesktopCommandsNative | undefined {
  return NativeModules.OmiDesktopCommands as DesktopCommandsNative | undefined;
}

export function parseAudioRecordingMode(value: unknown): AudioRecordingMode {
  if (value === 'always' || value === 'meetings') {
    return value;
  }
  return 'off';
}

export function parseDesktopAppearance(value: unknown): DesktopAppearance {
  if (value === 'light' || value === 'system') {
    return value;
  }
  return 'dark';
}

export function parseDesktopUiVersion(value: unknown): DesktopUiVersion {
  if (value === 'v5') {
    return 'v5';
  }
  return 'v5.1';
}

export function parseLiveVoiceProvider(value: unknown): LiveVoiceProvider {
  if (value === 'gemini_live') {
    return 'gemini_live';
  }
  return 'gpt_live';
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

// The native snapshot returns NSNull for unset keys, and NSNull bridges as
// a non-nullish object — `??` would pass it straight through to the parser,
// pinning the plane to 'old'. Only strings count as a stored choice.
function storedPlane(
  record: Record<string, unknown>,
  stampedV5Origin: string | null,
): string {
  if (typeof record.softwarePlane === 'string' && record.softwarePlane) {
    return record.softwarePlane;
  }
  if (typeof record.plane === 'string' && record.plane) {
    return record.plane;
  }
  return stampedV5Origin === null ? 'old' : 'new';
}

function snapshotFromRecord(
  record: Record<string, unknown>,
): DesktopPreferences {
  const stampedV5Origin = parseStampedV5Origin(record.stampedV5Origin);
  return {
    softwarePlane: parseSoftwarePlane(storedPlane(record, stampedV5Origin)),
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
    liveVoiceProvider: parseLiveVoiceProvider(record.liveVoiceProvider),
    appearance: parseDesktopAppearance(record.appearance),
    uiVersion: parseDesktopUiVersion(record.uiVersion),
    exploreProgress:
      typeof record.exploreProgress === 'string' ? record.exploreProgress : '',
    stampedV5Origin,
  };
}

export async function loadDesktopPreferences(): Promise<DesktopPreferences> {
  const commands = desktopCommands();
  if (commands === undefined) {
    return {...memoryPreferences};
  }
  return snapshotFromRecord(await commands.loadDesktopPreferences());
}

export async function setDesktopPreference<
  Key extends Exclude<keyof DesktopPreferences, 'stampedV5Origin'>,
>(key: Key, value: DesktopPreferences[Key]): Promise<DesktopPreferences> {
  const commands = desktopCommands();
  if (commands === undefined) {
    (memoryPreferences as Record<string, unknown>)[key] = value;
    return loadDesktopPreferences();
  }
  const record = await commands.setDesktopPreference(key, value as never);
  return snapshotFromRecord(record);
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
