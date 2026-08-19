import {
  createBrowserCapabilityAdapter,
  type BrowserCapabilityResult,
  type BrowserCapabilitySnapshot,
  type BrowserEnvironment,
} from '../../pwa/src/browser-adapters';
import {
  assertLocalProxyPath,
  LOCAL_PROXY_PREFIX,
  localProxyRequestInit,
} from '../../pwa/src/local-proxy';
import type {
  BluetoothState,
  NativeHttpRequest,
  NativeHttpResponse,
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

export function unsupportedOperation(operation: string): never {
  throw new Error(`${operation} is unavailable in the browser`);
}

function unsupportedOperationAsync<Args extends unknown[]>(operation: string) {
  return async (..._args: Args): Promise<never> =>
    unsupportedOperation(operation);
}

function permissionState(
  result: BrowserCapabilityResult,
): NativeSnapshot['microphone'] {
  if (result.ok) return 'granted';
  if (result.reason === 'denied') return 'denied';
  if (result.reason === 'unsupported') return 'unsupported';
  return 'unknown';
}

function browserSnapshot(snapshot: BrowserCapabilitySnapshot): NativeSnapshot {
  return {
    audioRoute: 'browser',
    background: 'inactive',
    bluetooth: snapshot.bluetooth,
    capture: 'idle',
    captureMode: 'stream',
    devices: [],
    lastEvent:
      snapshot.bluetooth === 'unsupported'
        ? 'Web Bluetooth is unavailable in this browser.'
        : snapshot.bluetooth === 'selected'
          ? 'Browser Bluetooth selection recorded. Omi capture is not wired.'
          : 'Omi device capture is not wired in the browser.',
    microphone:
      snapshot.microphone === 'granted'
        ? 'granted'
        : snapshot.microphone === 'denied'
          ? 'denied'
          : snapshot.microphone === 'unsupported'
            ? 'unsupported'
            : 'unknown',
    notifications: 'unknown',
  };
}

export function createWebNativeAdapter(
  environment?: BrowserEnvironment,
): OmiNative {
  const browserCapabilities = createBrowserCapabilityAdapter(environment);

  return {
    capturePhoto: async () => ({accepted: false, reason: 'unsupported'}),
    connectDevice: unsupportedOperationAsync('Omi device capture'),
    disconnectDevice: unsupportedOperationAsync('Omi device capture'),
    endPhoneCall: unsupportedOperationAsync('Phone calls'),
    getAudioRoute: async () => 'browser',
    getBatteryHistory: async () => [],
    getBluetoothState: async () => browserCapabilities.snapshot().bluetooth,
    getCameraStatus: async () => ({
      available: false,
      permission: 'unsupported',
    }),
    getDeviceDiagnostics: async () => ({}),
    getSnapshot: async () =>
      browserSnapshot(await browserCapabilities.refresh()),
    getWatchStatus: async () => ({battery: 0, paired: false, reachable: false}),
    getWifiNetwork: async () => ({connected: false, ssid: ''}),
    readCharacteristic: unsupportedOperationAsync('Omi device capture'),
    requestPermissions: async () => {
      const result = await browserCapabilities.checkMicrophone();
      return {
        microphone: permissionState(result),
        notifications: 'unknown' as const,
      };
    },
    setBackgroundMode: unsupportedOperationAsync('Background mode'),
    setNotificationOnKillService: unsupportedOperationAsync(
      'Kill-service notifications',
    ),
    setPhoneCallAudio: unsupportedOperationAsync('Phone calls'),
    startCapture: unsupportedOperationAsync('Omi capture'),
    startPhoneCall: unsupportedOperationAsync('Phone calls'),
    startRssiStreaming: unsupportedOperationAsync('Omi device capture'),
    startScan: async () => {
      await browserCapabilities.chooseBluetoothDevice();
      return [];
    },
    stopCapture: unsupportedOperationAsync('Omi capture'),
    stopRssiStreaming: unsupportedOperationAsync('Omi device capture'),
    stopScan: unsupportedOperationAsync('Omi device capture'),
    subscribeCharacteristic: unsupportedOperationAsync('Omi device capture'),
    unsubscribeCharacteristic: unsupportedOperationAsync('Omi device capture'),
    writeCharacteristic: unsupportedOperationAsync('Omi device capture'),
  };
}

function proxyPath(path: string): string {
  const candidate = path.startsWith(LOCAL_PROXY_PREFIX)
    ? path
    : `${LOCAL_PROXY_PREFIX}${path}`;
  return assertLocalProxyPath(candidate);
}

function retryAfterSeconds(response: Response): number | null {
  const value = Number(response.headers.get('retry-after'));
  return Number.isInteger(value) && value > 0 && value <= 3600 ? value : null;
}

async function browserRequest(
  request: NativeHttpRequest,
  accept: string,
): Promise<NativeHttpResponse> {
  const response = await fetch(
    proxyPath(request.path),
    localProxyRequestInit({
      body: request.body,
      credentials: 'omit',
      headers: {...request.headers, accept},
      method: request.method,
    }),
  );
  const body = await response.text();
  return {
    body: body === '' ? null : body,
    id: request.id,
    retryAfterSeconds: retryAfterSeconds(response),
    status: response.status,
  };
}

const browserBackend: OmiBackend = {
  cancelGenerationEvents(generationId) {
    return browserRequest(
      {
        id: `cancel-${generationId}`,
        method: 'DELETE',
        path: `/v1/chat-generations/${encodeURIComponent(generationId)}`,
      },
      'application/json',
    ).then(response => {
      if (response.status !== 202 && response.status !== 204) {
        throw new Error(`Generation cancellation failed (${response.status})`);
      }
    });
  },
  generationEvents(generationId, lastEventId) {
    return browserRequest(
      {
        headers:
          lastEventId === null ? undefined : {'last-event-id': lastEventId},
        id: generationId,
        method: 'GET',
        path: `/v1/chat-generations/${encodeURIComponent(generationId)}/events`,
      },
      'text/event-stream',
    );
  },
  request(request) {
    return browserRequest(request, 'application/json');
  },
};

const browserNative = createWebNativeAdapter();

export const omiBackend = browserBackend;
export const omiNative = browserNative;
export const isNativeBackendInstalled = true;
export const isNativeModuleInstalled = true;
