import {NativeEventEmitter, NativeModules} from 'react-native';

import type {
  BluetoothState,
  NativeSnapshot,
  OmiAuth,
  OmiBackend,
  OmiNative,
  OmiNativeEvent,
} from './omiNativeTypes';

export type {
  BluetoothState,
  CaptureMode,
  ConnectionPhase,
  Device,
  NativeHttpMethod,
  NativeHttpRequest,
  NativeHttpResponse,
  NativeSnapshot,
  OmiBackend,
  OmiAuth,
  OmiAuthSignInResult,
  OmiAuthSignOutResult,
  OmiNative,
  OmiNativeEvent,
} from './omiNativeTypes';

export type PlatformNativeSnapshot = NativeSnapshot;

export function isBluetoothScanAvailable(
  state: BluetoothState | undefined,
): boolean {
  return state === 'poweredOn';
}

export function browserScanErrorMessage(_error: unknown): string | null {
  return null;
}

export function resolveOmiNative(nativeModule: OmiNative | null | undefined) {
  return {adapter: nativeModule, installed: nativeModule != null};
}

export function subscribeOmiNativeEvents(
  listener: (event: OmiNativeEvent) => void,
): () => void {
  const nativeModule = NativeModules.OmiNative;
  if (nativeModule == null) {
    return () => undefined;
  }
  const emitter = new NativeEventEmitter(nativeModule);
  const subscription = emitter.addListener('omiNativeEvent', listener);
  return () => subscription.remove();
}

export function resolveOmiBackend(nativeModule: OmiBackend | null | undefined) {
  return {adapter: nativeModule, installed: nativeModule != null};
}

export function resolveOmiAuth(nativeModule: OmiAuth | null | undefined) {
  return {adapter: nativeModule, installed: nativeModule != null};
}

const selectedOmiNative = resolveOmiNative(
  NativeModules.OmiNative as OmiNative | undefined,
);

export const omiNative = selectedOmiNative.adapter;
export const isNativeModuleInstalled = selectedOmiNative.installed;

const selectedOmiBackend = resolveOmiBackend(
  NativeModules.OmiBackend as OmiBackend | undefined,
);

export const omiBackend = selectedOmiBackend.adapter;
export const isNativeBackendInstalled = selectedOmiBackend.installed;

const selectedOmiAuth = resolveOmiAuth(
  NativeModules.OmiAuth as OmiAuth | undefined,
);

export const omiAuth = selectedOmiAuth.adapter;
