import {NativeModules} from 'react-native';

export type BluetoothState =
  | 'unknown'
  | 'poweredOff'
  | 'poweredOn'
  | 'unauthorized';
export type CaptureMode = 'stream' | 'batch';
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
};

export type OmiBackend = {
  request(request: NativeHttpRequest): Promise<NativeHttpResponse>;
  generationEvents(
    generationId: string,
    lastEventId: string | null,
  ): Promise<string>;
  cancelGenerationEvents(generationId: string): Promise<void>;
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
  capture: 'idle' | 'recording' | 'stopping';
  captureMode: CaptureMode;
  microphone: 'unknown' | 'granted' | 'denied';
  notifications: 'unknown' | 'granted' | 'denied';
  background: 'inactive' | 'active';
  audioRoute: string;
  lastEvent: string;
};

export type OmiNative = {
  getSnapshot(): Promise<NativeSnapshot>;
  getBluetoothState(): Promise<BluetoothState>;
  requestPermissions(): Promise<
    Pick<NativeSnapshot, 'microphone' | 'notifications'>
  >;
  startScan(
    timeoutSeconds?: number,
    serviceUuids?: string[],
  ): Promise<Device[]>;
  stopScan(): Promise<void>;
  connectDevice(id: string): Promise<void>;
  disconnectDevice(id: string): Promise<void>;
  readCharacteristic(
    deviceId: string,
    serviceUuid: string,
    characteristicUuid: string,
  ): Promise<number[]>;
  writeCharacteristic(
    deviceId: string,
    serviceUuid: string,
    characteristicUuid: string,
    data: number[],
  ): Promise<void>;
  subscribeCharacteristic(
    deviceId: string,
    serviceUuid: string,
    characteristicUuid: string,
  ): Promise<void>;
  unsubscribeCharacteristic(
    deviceId: string,
    serviceUuid: string,
    characteristicUuid: string,
  ): Promise<void>;
  startRssiStreaming(deviceId: string): Promise<void>;
  stopRssiStreaming(deviceId: string): Promise<void>;
  getDeviceDiagnostics(deviceId: string): Promise<Record<string, unknown>>;
  getBatteryHistory(
    deviceId: string,
  ): Promise<Array<{timestamp: number; level: number}>>;
  startCapture(mode: CaptureMode): Promise<void>;
  stopCapture(): Promise<void>;
  getAudioRoute(): Promise<string>;
  startPhoneCall(phoneNumber: string): Promise<void>;
  endPhoneCall(): Promise<void>;
  setPhoneCallAudio(muted: boolean, speakerOn: boolean): Promise<void>;
  setNotificationOnKillService(
    title: string,
    description: string,
  ): Promise<void>;
  getWifiNetwork(): Promise<{ssid: string; connected: boolean}>;
  setBackgroundMode(active: boolean): Promise<void>;
  getWatchStatus(): Promise<{
    paired: boolean;
    reachable: boolean;
    battery: number;
  }>;
  getCameraStatus(): Promise<{available: boolean; permission: string}>;
  capturePhoto(): Promise<{accepted: boolean; reason?: string}>;
};

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
