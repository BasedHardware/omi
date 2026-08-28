import {
  createBrowserCapabilityAdapter,
  type BrowserCapabilityResult,
  type BrowserCapabilitySnapshot,
  type BrowserEnvironment,
} from './browser-adapters.web';
import {
  readBrowserGenerationEvents,
  type BrowserGenerationStreamResult,
} from './browser-sse.web';
export {
  BrowserGenerationCancelledError,
  BrowserGenerationRecoveryError,
} from './browser-sse.web';
import {
  assertLocalProxyPath,
  LOCAL_PROXY_PREFIX,
  localProxyRequestInit,
} from './local-proxy';
import type {
  BluetoothState as NativeBluetoothState,
  NativeHttpRequest,
  NativeHttpResponse,
  NativeSnapshot as NativeSnapshotContract,
  OmiAuth,
  OmiBackend,
  OmiNative as NativeOmiNative,
} from './omiNativeTypes';

export type {
  CaptureMode,
  ConnectionPhase,
  Device,
  NativeHttpMethod,
  NativeHttpRequest,
  NativeHttpResponse,
  OmiAuth,
  OmiAuthSignInResult,
  OmiAuthSignOutResult,
  OmiBackend,
  OmiNativeEvent,
} from './omiNativeTypes';

type WebBluetoothState = BrowserCapabilitySnapshot['bluetooth'];
type WebPermissionState = 'unknown' | 'granted' | 'denied' | 'unsupported';

export type WebNativeSnapshot = Omit<
  NativeSnapshotContract,
  'bluetooth' | 'microphone' | 'notifications'
> & {
  bluetooth: WebBluetoothState;
  microphone: WebPermissionState;
  notifications: WebPermissionState;
};

export type WebOmiNative = Omit<
  NativeOmiNative,
  'getBluetoothState' | 'getSnapshot' | 'requestPermissions'
> & {
  getBluetoothState(): Promise<WebBluetoothState>;
  getSnapshot(): Promise<WebNativeSnapshot>;
  requestPermissions(): Promise<
    Pick<WebNativeSnapshot, 'microphone' | 'notifications'>
  >;
};

export type BluetoothState = WebBluetoothState;
export type NativeSnapshot = WebNativeSnapshot;
export type OmiNative = WebOmiNative;
export type PlatformNativeSnapshot = Omit<WebNativeSnapshot, 'bluetooth'> & {
  bluetooth: NativeBluetoothState | WebBluetoothState;
};

export type BrowserScanFailureReason = Extract<
  BrowserCapabilityResult,
  {ok: false}
>['reason'];

export class BrowserScanError extends Error {
  constructor(readonly reason: BrowserScanFailureReason) {
    super(`Browser Bluetooth scan failed: ${reason}`);
    this.name = 'BrowserScanError';
  }
}

export function browserScanErrorMessage(error: unknown): string | null {
  if (!(error instanceof BrowserScanError)) {
    return null;
  }
  switch (error.reason) {
    case 'cancelled':
      return 'Scan cancelled. No Omi device was discovered.';
    case 'denied':
      return 'Bluetooth permission was denied. No Omi device was discovered.';
    case 'unsupported':
      return 'Bluetooth scanning is not supported in this browser. No Omi device was discovered.';
    case 'error':
      return 'Bluetooth scanning failed. No Omi device was discovered.';
  }
}

export function isBluetoothScanAvailable(
  state: NativeBluetoothState | WebBluetoothState | undefined,
): boolean {
  return state === 'poweredOn' || state === 'available' || state === 'selected';
}

export function unsupportedOperation(operation: string): never {
  throw new Error(`${operation} is unavailable in the browser`);
}

function unsupportedOperationAsync<Args extends unknown[]>(operation: string) {
  return async (..._args: Args): Promise<never> =>
    unsupportedOperation(operation);
}

function permissionState(result: BrowserCapabilityResult): WebPermissionState {
  if (result.ok) {
    return 'granted';
  }
  if (result.reason === 'denied') {
    return 'denied';
  }
  if (result.reason === 'unsupported') {
    return 'unsupported';
  }
  return 'unknown';
}

function browserSnapshot(
  snapshot: BrowserCapabilitySnapshot,
): WebNativeSnapshot {
  return {
    audioRoute: 'browser',
    background: 'inactive',
    bluetooth: snapshot.bluetooth,
    capture: 'idle',
    captureMode: 'stream',
    connectedDeviceId: null,
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
    phase: 'disconnected',
  };
}

export function createWebNativeAdapter(
  environment?: BrowserEnvironment,
): WebOmiNative {
  const browserCapabilities = createBrowserCapabilityAdapter(environment);

  return {
    connectDevice: unsupportedOperationAsync('Omi device capture'),
    disconnectDevice: unsupportedOperationAsync('Omi device capture'),
    getBluetoothState: async () => browserCapabilities.snapshot().bluetooth,
    getSnapshot: async () =>
      browserSnapshot(await browserCapabilities.refresh()),
    requestPermissions: async () => {
      const result = await browserCapabilities.checkMicrophone();
      return {
        microphone: permissionState(result),
        notifications: 'unknown' as const,
      };
    },
    startScan: async () => {
      const result = await browserCapabilities.chooseBluetoothDevice();
      if (!result.ok) {
        throw new BrowserScanError(result.reason);
      }
      return [];
    },
    stopScan: unsupportedOperationAsync('Omi device capture'),
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

const generationControllers = new Map<string, AbortController>();

async function browserGenerationEvents(
  generationId: string,
  lastEventId: string | null,
): Promise<NativeHttpResponse> {
  const controller = new AbortController();
  generationControllers.set(generationId, controller);
  let result: BrowserGenerationStreamResult;
  try {
    result = await readBrowserGenerationEvents({
      initialLastEventId: lastEventId,
      open: (resumeEventId, signal) =>
        fetch(
          proxyPath(
            `/v1/chat-generations/${encodeURIComponent(generationId)}/events`,
          ),
          localProxyRequestInit({
            credentials: 'omit',
            headers:
              resumeEventId === null
                ? {'cache-control': 'no-cache'}
                : {
                    'cache-control': 'no-cache',
                    'last-event-id': resumeEventId,
                  },
            method: 'GET',
            signal,
          }),
        ),
      signal: controller.signal,
    });
  } finally {
    if (generationControllers.get(generationId) === controller) {
      generationControllers.delete(generationId);
    }
  }
  return {
    body: result.body,
    id: generationId,
    retryAfterSeconds: result.retryAfterSeconds,
    status: result.status,
  };
}

const browserBackend: OmiBackend = {
  cancelGenerationEvents(generationId) {
    generationControllers.get(generationId)?.abort();
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
    return browserGenerationEvents(generationId, lastEventId);
  },
  request(request) {
    return browserRequest(request, 'application/json');
  },
};

const browserNative = createWebNativeAdapter();
const browserAuth: OmiAuth = {
  async hasCloudSession() {
    return false;
  },
  async hasCompletedOnboarding() {
    return true;
  },
  async markOnboardingComplete() {},
  async signIn() {
    return {signedIn: false};
  },
  async signOut() {
    return {signedOut: true};
  },
};

export const omiBackend = browserBackend;
export const omiAuth = browserAuth;
export const omiNative = browserNative;
export const isNativeBackendInstalled = true;
export const isNativeModuleInstalled = true;

export function subscribeOmiNativeEvents(
  _listener: (event: import('./omiNativeTypes').OmiNativeEvent) => void,
): () => void {
  return () => undefined;
}
