import {
  createBrowserCapabilityAdapter,
  type BrowserCapabilitySnapshot,
} from '../../pwa/src/browser-adapters';
import {
  assertLocalProxyPath,
  LOCAL_PROXY_PREFIX,
  localProxyRequestInit,
} from '../../pwa/src/local-proxy';
import type {
  BluetoothState,
  Device,
  NativeHttpRequest,
  NativeHttpResponse,
  NativeSnapshot,
  OmiBackend,
  OmiNative,
} from './omiNative';

const browserCapabilities = createBrowserCapabilityAdapter();

function bluetoothState(snapshot: BrowserCapabilitySnapshot): BluetoothState {
  if (snapshot.bluetooth === 'available' || snapshot.bluetooth === 'selected') {
    return 'poweredOn';
  }
  if (snapshot.bluetooth === 'denied' || snapshot.bluetooth === 'unsupported') {
    return 'unauthorized';
  }
  return 'unknown';
}

function browserSnapshot(snapshot: BrowserCapabilitySnapshot): NativeSnapshot {
  return {
    audioRoute: 'browser',
    background: 'inactive',
    bluetooth: bluetoothState(snapshot),
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
        : 'unknown',
    notifications: 'unknown',
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
  return {
    body: await response.text(),
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

const browserNative: OmiNative = {
  capturePhoto: async () => ({accepted: false, reason: 'unsupported'}),
  connectDevice: async () => {
    throw new Error('Omi device capture is unavailable in the browser');
  },
  disconnectDevice: async () => {
    throw new Error('Omi device capture is unavailable in the browser');
  },
  endPhoneCall: async () => {
    throw new Error('Phone calls are unavailable in the browser');
  },
  getAudioRoute: async () => 'browser',
  getBatteryHistory: async () => [],
  getBluetoothState: async () => bluetoothState(browserCapabilities.snapshot()),
  getCameraStatus: async () => ({available: false, permission: 'unsupported'}),
  getDeviceDiagnostics: async () => ({}),
  getSnapshot: async () => browserSnapshot(await browserCapabilities.refresh()),
  getWatchStatus: async () => ({battery: 0, paired: false, reachable: false}),
  getWifiNetwork: async () => ({connected: false, ssid: ''}),
  readCharacteristic: async () => {
    throw new Error('Omi device capture is unavailable in the browser');
  },
  requestPermissions: async () => {
    const result = await browserCapabilities.checkMicrophone();
    return {
      microphone: result.ok ? 'granted' : 'denied',
      notifications: 'denied',
    };
  },
  setBackgroundMode: async () => undefined,
  setNotificationOnKillService: async () => undefined,
  setPhoneCallAudio: async () => undefined,
  startCapture: async () => {
    throw new Error('Omi capture is unavailable in the browser');
  },
  startPhoneCall: async () => {
    throw new Error('Phone calls are unavailable in the browser');
  },
  startRssiStreaming: async () => {
    throw new Error('Omi device capture is unavailable in the browser');
  },
  startScan: async () => {
    await browserCapabilities.chooseBluetoothDevice();
    return [] as Device[];
  },
  stopCapture: async () => undefined,
  stopRssiStreaming: async () => undefined,
  stopScan: async () => undefined,
  subscribeCharacteristic: async () => {
    throw new Error('Omi device capture is unavailable in the browser');
  },
  unsubscribeCharacteristic: async () => {
    throw new Error('Omi device capture is unavailable in the browser');
  },
  writeCharacteristic: async () => {
    throw new Error('Omi device capture is unavailable in the browser');
  },
};

export const omiBackendWeb = browserBackend;
export const omiNativeWeb = browserNative;
export const omiBackend = omiBackendWeb;
export const omiNative = omiNativeWeb;
export const isNativeBackendInstalled = true;
export const isNativeModuleInstalled = true;
