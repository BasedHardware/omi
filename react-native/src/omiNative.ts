import {
  NativeEventEmitter,
  NativeModules,
  PermissionsAndroid,
  Platform,
} from 'react-native';

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

export async function requestBluetoothScanPermission(): Promise<boolean> {
  if (Platform.OS !== 'android') {
    return true;
  }
  const permissions =
    Number(Platform.Version) >= 31
      ? [
          PermissionsAndroid.PERMISSIONS.BLUETOOTH_SCAN,
          PermissionsAndroid.PERMISSIONS.BLUETOOTH_CONNECT,
        ]
      : [PermissionsAndroid.PERMISSIONS.ACCESS_FINE_LOCATION];
  const results = await PermissionsAndroid.requestMultiple(permissions);
  return permissions.every(
    permission => results[permission] === PermissionsAndroid.RESULTS.GRANTED,
  );
}

export function isBluetoothScanAvailable(
  state: BluetoothState | undefined,
): boolean {
  return (
    state === 'poweredOn' ||
    (Platform.OS === 'android' && state === 'unauthorized')
  );
}

export function browserScanErrorMessage(_error: unknown): string | null {
  return null;
}

export function resolveOmiNative(nativeModule: OmiNative | null | undefined) {
  return {
    adapter:
      nativeModule == null
        ? nativeModule
        : (Object.create(nativeModule, {
            startScan: {
              value: (timeoutSeconds = 8, serviceUuids: string[] = []) =>
                nativeModule.startScan(timeoutSeconds, serviceUuids),
            },
          }) as OmiNative),
    installed: nativeModule != null,
  };
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

export function subscribeOmiGenerationFrame(
  listener: (event: {streamId: string; frame: string}) => void,
): () => void {
  const nativeModule = NativeModules.OmiBackend;
  if (nativeModule == null) {
    return () => undefined;
  }
  const emitter = new NativeEventEmitter(nativeModule);
  const subscription = emitter.addListener(
    'omiGenerationFrame',
    (value: unknown) => {
      if (value === null || typeof value !== 'object') {
        return;
      }
      const event = value as {streamId?: unknown; frame?: unknown};
      if (
        typeof event.streamId !== 'string' ||
        typeof event.frame !== 'string'
      ) {
        return;
      }
      listener({streamId: event.streamId, frame: event.frame});
    },
  );
  return () => subscription.remove();
}

function listenToGenerationFrames(
  streamId: string,
  onFrame?: (frame: string) => void,
): () => void {
  if (onFrame === undefined) {
    return () => undefined;
  }
  let live = true;
  const stop = subscribeOmiGenerationFrame(event => {
    if (!live || event.streamId !== streamId) {
      return;
    }
    onFrame(event.frame);
  });
  return () => {
    live = false;
    stop();
  };
}

export function resolveOmiBackend(nativeModule: OmiBackend | null | undefined) {
  if (nativeModule == null) {
    return {adapter: nativeModule, installed: false};
  }
  const sendOmiChat = nativeModule.sendOmiChat?.bind(nativeModule);
  const generationEvents = nativeModule.generationEvents.bind(nativeModule);
  return {
    adapter: Object.create(nativeModule, {
      sendOmiChat: {
        value:
          sendOmiChat === undefined
            ? undefined
            : async (
                requestId: string,
                text: string,
                onFrame?: (frame: string) => void,
              ) => {
                const stop = listenToGenerationFrames(requestId, onFrame);
                try {
                  return await sendOmiChat(requestId, text);
                } finally {
                  stop();
                }
              },
      },
      generationEvents: {
        value: async (
          generationId: string,
          lastEventId: string | null,
          onFrame?: (frame: string) => void,
        ) => {
          const stop = listenToGenerationFrames(generationId, onFrame);
          try {
            return await generationEvents(generationId, lastEventId);
          } finally {
            stop();
          }
        },
      },
    }) as OmiBackend,
    installed: true,
  };
}

export function subscribeOmiBackendSessionInvalidated(
  listener: () => void,
): () => void {
  const nativeModule = NativeModules.OmiBackend;
  if (nativeModule == null) {
    return () => undefined;
  }
  const emitter = new NativeEventEmitter(nativeModule);
  const subscription = emitter.addListener(
    'omiBackendSessionInvalidated',
    listener,
  );
  return () => subscription.remove();
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
