export type BluetoothState =
  | 'unknown'
  | 'poweredOff'
  | 'poweredOn'
  | 'unauthorized';
export type CaptureMode = 'stream' | 'batch';
export type ConnectionPhase = 'disconnected' | 'connecting' | 'connected';
export type NativeHttpMethod = 'GET' | 'POST' | 'PATCH' | 'DELETE';

export type NativeHttpRequest = {
  id: string;
  method: NativeHttpMethod;
  path: `/${string}`;
  headers?: Record<string, string>;
  body?: string;
};

export type NativeHttpResponse = {
  id: string;
  status: number;
  body: string | null;
  retryAfterSeconds?: number | null;
};

export type OmiBackend = {
  request(request: NativeHttpRequest): Promise<NativeHttpResponse>;
  generationEvents(
    generationId: string,
    lastEventId: string | null,
  ): Promise<NativeHttpResponse>;
  cancelGenerationEvents(generationId: string): Promise<void>;
};

export type OmiAuthSignInResult = {
  signedIn: boolean;
};

export type OmiAuthSignOutResult = {
  signedOut: boolean;
};

export type OmiAuth = {
  signIn(): Promise<OmiAuthSignInResult>;
  signOut(): Promise<OmiAuthSignOutResult>;
  hasCloudSession(): Promise<boolean>;
  hasCompletedOnboarding(): Promise<boolean>;
  markOnboardingComplete(): Promise<void>;
};

export type Device = {
  id: string;
  name: string;
  rssi: number;
  connected: boolean;
  battery?: number;
};

export type NativeSnapshot = {
  bluetooth: BluetoothState;
  devices: Device[];
  connectedDeviceId: string | null;
  phase: ConnectionPhase;
  capture: 'idle' | 'recording' | 'stopping';
  lastEvent: string;
  microphone: 'unknown' | 'granted' | 'denied';
  notifications: 'unknown' | 'granted' | 'denied';
  codec?: number;
  captureMode?: CaptureMode;
  background?: 'inactive' | 'active';
  audioRoute?: string;
};

export type OmiNativeEvent =
  | {type: 'discovery'; device: Device}
  | {type: 'battery'; deviceId: string; battery: number}
  | {type: 'audio'; deviceId: string; codec: number; payloadBase64: string}
  | {type: 'snapshot'; snapshot: NativeSnapshot};

export type OmiNative = {
  getSnapshot(): Promise<NativeSnapshot>;
  getBluetoothState(): Promise<BluetoothState>;
  requestPermissions(): Promise<{
    microphone: NativeSnapshot['microphone'];
    notifications: NativeSnapshot['notifications'];
  }>;
  startScan(
    timeoutSeconds?: number,
    serviceUuids?: string[],
  ): Promise<Device[]>;
  stopScan(): Promise<void>;
  connectDevice(id: string): Promise<void>;
  disconnectDevice(id: string): Promise<void>;
};
