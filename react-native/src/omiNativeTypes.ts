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
  expectedApiContract?: 'omi' | 'canonical';
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

export type RecordingJournalInput = {
  capturedAtMs?: number;
  deviceId: string;
  deviceName?: string;
  codec: number;
};

export type RecordingJournal = {
  capturedAtMs?: number;
  handle: string;
  captureId: string;
  deviceId: string;
  deviceName: string | null;
  codec: number;
  sessionId: string | null;
  entries: string[];
};

export type OmiBackend = {
  getApiContract?(): Promise<'omi' | 'canonical'>;
  getSoftwarePlane?(): Promise<'old' | 'new'>;
  setSoftwarePlane?(plane: 'old' | 'new'): Promise<'old' | 'new'>;
  stampedV5BackendOrigin?(): Promise<string | null>;
  sendOmiChat?(
    requestId: string,
    text: string,
    onFrame?: (frame: string) => void,
  ): Promise<NativeHttpResponse>;
  cancelOmiChat?(requestId: string): Promise<void>;
  createRecordingJournal?(
    input: RecordingJournalInput,
  ): Promise<RecordingJournal>;
  listRecordingJournals?(): Promise<RecordingJournal[]>;
  readRecordingJournal?(handle: string): Promise<RecordingJournal>;
  appendRecordingJournal?(handle: string, entry: string): Promise<number>;
  requestRecordingJournal?(
    handle: string,
    request: NativeHttpRequest,
  ): Promise<NativeHttpResponse>;
  removeRecordingJournal?(handle: string): Promise<void>;
  createWriteId?(): Promise<string>;
  createRecordingId?(): Promise<string>;
  request(request: NativeHttpRequest): Promise<NativeHttpResponse>;
  generationEvents(
    generationId: string,
    lastEventId: string | null,
    onFrame?: (frame: string) => void,
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
  cancelSignIn(): Promise<void>;
  signOut(): Promise<OmiAuthSignOutResult>;
  hasCloudSession(): Promise<boolean>;
  hasCompletedOnboarding(): Promise<boolean>;
  markOnboardingComplete(): Promise<void>;
};

export type DeviceStorageStatus = {
  usedBytes: number;
  unreadPackets: number;
  freeBytes: number;
  clockValid: boolean;
};

export type Device = {
  id: string;
  name: string;
  rssi?: number;
  connected: boolean;
  battery?: number;
  features?: number;
  ledBrightness?: number;
  microphoneGain?: number;
  buttonSupported?: boolean;
  findDeviceSupported?: boolean;
  storageStatusSupported?: boolean;
  charging?: boolean;
  information?: Partial<
    Record<
      'model' | 'firmware' | 'hardware' | 'manufacturer' | 'serial',
      string
    >
  >;
};

export type NativeSnapshot = {
  bluetooth: BluetoothState;
  devices: Device[];
  connectedDeviceId: string | null;
  connectionId?: string;
  phase: ConnectionPhase;
  capture: 'idle' | 'recording' | 'stopping';
  lastEvent: string;
  microphone: 'unknown' | 'granted' | 'denied';
  notifications: 'unknown' | 'granted' | 'denied';
  codec?: number;
  captureMode?: CaptureMode;
  background?: 'inactive' | 'active';
  audioStatus?: 'waiting' | 'active';
  audioRoute?: string;
};

export type OmiNativeEvent =
  | {
      type: 'button';
      deviceId: string;
      connectionId: string;
      action: 'doublePress';
    }
  | {type: 'discovery'; device: Device}
  | {type: 'battery'; deviceId: string; battery: number}
  | {
      type: 'audio';
      capturedAtMs?: number;
      deviceId: string;
      connectionId: string;
      codec: number;
      payloadBase64: string;
    }
  | {type: 'snapshot'; snapshot: NativeSnapshot};

export type OmiNative = {
  getRememberedDevice?(): Promise<{id: string; name: string} | null>;
  rememberConnectedDevice?(): Promise<{id: string; name: string}>;
  forgetRememberedDevice?(): Promise<void>;
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
  findDevice?(id: string): Promise<void>;
  readStorageStatus?(id: string): Promise<DeviceStorageStatus>;
  setDeviceSetting?(
    id: string,
    setting: 'ledBrightness' | 'microphoneGain',
    value: number,
  ): Promise<number>;
};
