import {NativeModules} from 'react-native';

import type {
  BluetoothState,
  NativeSnapshot,
  OmiBackend,
  OmiNative,
} from './omiNativeTypes';

export type {
  BluetoothState,
  CaptureMode,
  Device,
  NativeHttpMethod,
  NativeHttpRequest,
  NativeHttpResponse,
  NativeSnapshot,
  OmiBackend,
  OmiNative,
} from './omiNativeTypes';

export type PlatformNativeSnapshot = NativeSnapshot;

export function isBluetoothScanAvailable(
  state: BluetoothState | undefined,
): boolean {
  return state === 'poweredOn';
}

export function resolveOmiNative(nativeModule: OmiNative | null | undefined) {
  return {adapter: nativeModule, installed: nativeModule != null};
}

export function resolveOmiBackend(nativeModule: OmiBackend | null | undefined) {
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
