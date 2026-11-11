import { PermissionsAndroid, Platform } from 'react-native'
import { requireNativeModule } from 'expo-modules-core'

export type CallState = 'idle' | 'ringing' | 'offhook'

export interface CallPermissionState {
  READ_PHONE_STATE: boolean
  ANSWER_PHONE_CALLS: boolean
  canDetect: boolean
  canAnswer: boolean
}

interface LocalCallsNative {
  permissionState(): Promise<CallPermissionState>
  start(): Promise<boolean>
  stop(): Promise<boolean>
  answer(): Promise<boolean>
  endCall(): Promise<boolean>
  addListener(eventName: 'callState', listener: (event: { state: CallState; caller: string | null }) => void): {
    remove(): void
  }
}

// requireNativeModule THROWS when the module is absent, so it cannot be called
// unguarded at module scope: a bare import of this file would then take down
// anything that touches it -- Expo Go, iOS, and every Jest test, which has no
// native modules at all. Probe inside a try instead, and let the functions below
// refuse rather than crash when native is null.
function probe(): LocalCallsNative | null {
  try {
    return requireNativeModule<LocalCallsNative>('LocalCalls')
  } catch {
    return null
  }
}

const native = probe()

export const isCallDetectionAvailable = native != null
export const isSupportedPlatform = Platform.OS === 'android'

/** Nothing granted. The honest answer when the module is not linked at all. */
const NO_PERMISSIONS: CallPermissionState = {
  READ_PHONE_STATE: false,
  ANSWER_PHONE_CALLS: false,
  canDetect: false,
  canAnswer: false,
}

let callSub: { remove(): void } | null = null

/** What the OS currently permits. Not a prompt. */
export function getCallPermissions(): Promise<CallPermissionState> {
  // Informational, so it reports rather than throws when unavailable: the caller
  // renders a state, it does not handle an exception.
  return native ? native.permissionState() : Promise.resolve(NO_PERMISSIONS)
}

/**
 * Prompts for what is missing and returns the resulting state.
 *
 * Both permissions are runtime grants and either can be revoked between calls, so
 * this reports the state after prompting rather than assuming success.
 */
export async function requestCallPermissions(): Promise<CallPermissionState> {
  if (!isSupportedPlatform || !native) return { ...NO_PERMISSIONS }
  await PermissionsAndroid.requestMultiple([
    PermissionsAndroid.PERMISSIONS.READ_PHONE_STATE as never,
    PermissionsAndroid.PERMISSIONS.ANSWER_PHONE_CALLS as never,
  ])
  return native.permissionState()
}

/**
 * Starts listening for call state.
 *
 * Returns false rather than throwing when READ_PHONE_STATE is missing, so a
 * caller prompts instead of catching. The listener is removed again on failure.
 */
export async function startCallDetection(
  onState: (state: CallState, caller: string | null) => void
): Promise<boolean> {
  if (!isSupportedPlatform || !native) return false
  if (callSub) return true
  const sub = native.addListener('callState', ({ state, caller }) => onState(state, caller ?? null))
  callSub = sub
  try {
    const started = await native.start()
    if (!started) {
      sub.remove()
      if (callSub === sub) callSub = null
      return false
    }
    return true
  } catch {
    sub.remove()
    if (callSub === sub) callSub = null
    return false
  }
}

export const stopCallDetection = async (): Promise<void> => {
  if (!isSupportedPlatform || !native) return
  try {
    await native.stop()
  } catch {
    // ignore
  }
  callSub?.remove()
  callSub = null
}

/**
 * Answers a ringing call. Requires ANSWER_PHONE_CALLS.
 *
 * This does not enable audio injection: a carrier call takes exclusive audio and
 * Android exposes no API for a third-party app to add a stream to it.
 */
export async function answerCall(): Promise<boolean> {
  if (!isSupportedPlatform || !native) return false
  try {
    return (await native.answer()) === true
  } catch {
    return false
  }
}

export async function hangUp(): Promise<boolean> {
  if (!isSupportedPlatform || !native) return false
  try {
    return (await native.endCall()) === true
  } catch {
    return false
  }
}
