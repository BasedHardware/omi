import {NativeModules} from 'react-native';

export type BluetoothState = 'unknown' | 'poweredOff' | 'poweredOn' | 'unauthorized';
export type CaptureMode = 'stream' | 'batch';

export type Device = {
  id: string;
  name: string;
  rssi: number;
  connected: boolean;
  battery: number;
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
  requestPermissions(): Promise<Pick<NativeSnapshot, 'microphone' | 'notifications'>>;
  startScan(timeoutSeconds?: number, serviceUuids?: string[]): Promise<Device[]>;
  stopScan(): Promise<void>;
  connectDevice(id: string): Promise<void>;
  disconnectDevice(id: string): Promise<void>;
  readCharacteristic(deviceId: string, serviceUuid: string, characteristicUuid: string): Promise<number[]>;
  writeCharacteristic(deviceId: string, serviceUuid: string, characteristicUuid: string, data: number[]): Promise<void>;
  subscribeCharacteristic(deviceId: string, serviceUuid: string, characteristicUuid: string): Promise<void>;
  unsubscribeCharacteristic(deviceId: string, serviceUuid: string, characteristicUuid: string): Promise<void>;
  startRssiStreaming(deviceId: string): Promise<void>;
  stopRssiStreaming(deviceId: string): Promise<void>;
  getDeviceDiagnostics(deviceId: string): Promise<Record<string, unknown>>;
  getBatteryHistory(deviceId: string): Promise<Array<{timestamp: number; level: number}>>;
  startCapture(mode: CaptureMode): Promise<void>;
  stopCapture(): Promise<void>;
  getAudioRoute(): Promise<string>;
  startPhoneCall(phoneNumber: string): Promise<void>;
  endPhoneCall(): Promise<void>;
  setPhoneCallAudio(muted: boolean, speakerOn: boolean): Promise<void>;
  setNotificationOnKillService(title: string, description: string): Promise<void>;
  getWifiNetwork(): Promise<{ssid: string; connected: boolean}>;
  setBackgroundMode(active: boolean): Promise<void>;
  getWatchStatus(): Promise<{paired: boolean; reachable: boolean; battery: number}>;
  getCameraStatus(): Promise<{available: boolean; permission: string}>;
  capturePhoto(): Promise<{accepted: boolean; reason?: string}>;
};

const wait = (ms = 80) => new Promise<void>((resolve) => setTimeout(resolve, ms));

class HostMvpAdapter implements OmiNative {
  private snapshot: NativeSnapshot = {
    bluetooth: 'poweredOn',
    devices: [],
    capture: 'idle',
    captureMode: 'stream',
    microphone: 'unknown',
    notifications: 'unknown',
    background: 'inactive',
    audioRoute: 'phone-mic',
    lastEvent: 'Host adapter ready; native module not installed',
  };

  async getSnapshot() { return this.snapshot; }
  async getBluetoothState() { return this.snapshot.bluetooth; }

  async requestPermissions() {
    await wait();
    this.snapshot = {...this.snapshot, microphone: 'granted', notifications: 'granted', lastEvent: 'Permissions granted by host adapter'};
    return {microphone: this.snapshot.microphone, notifications: this.snapshot.notifications};
  }

  async startScan() {
    await wait(120);
    this.snapshot = {...this.snapshot, devices: [
      {id: 'mvp-omi-001', name: 'Omi MVP Simulator', rssi: -48, connected: false, battery: 87},
      {id: 'mvp-omi-002', name: 'Omi DevKit Simulator', rssi: -66, connected: false, battery: 61},
    ], lastEvent: 'BLE scan completed (host simulator)'};
    return this.snapshot.devices;
  }
  async stopScan() { await wait(20); this.snapshot = {...this.snapshot, lastEvent: 'BLE scan stopped'}; }

  async connectDevice(id: string) {
    await wait();
    this.snapshot = {...this.snapshot, devices: this.snapshot.devices.map((d) => d.id === id ? {...d, connected: true} : d), lastEvent: `Connected to ${id}`};
  }
  async disconnectDevice(id: string) {
    await wait();
    this.snapshot = {...this.snapshot, devices: this.snapshot.devices.map((d) => d.id === id ? {...d, connected: false} : d), lastEvent: `Disconnected from ${id}`};
  }
  async readCharacteristic() { await wait(20); return [0xaa, 0x55, 0x01, 0x00]; }
  async writeCharacteristic(_d: string, _s: string, _c: string, _data: number[]) { await wait(20); this.snapshot = {...this.snapshot, lastEvent: 'Characteristic write completed'}; }
  async subscribeCharacteristic() { await wait(20); this.snapshot = {...this.snapshot, lastEvent: 'Characteristic subscription active'}; }
  async unsubscribeCharacteristic() { await wait(20); this.snapshot = {...this.snapshot, lastEvent: 'Characteristic subscription stopped'}; }
  async startRssiStreaming() { await wait(20); this.snapshot = {...this.snapshot, lastEvent: 'RSSI streaming active'}; }
  async stopRssiStreaming() { await wait(20); this.snapshot = {...this.snapshot, lastEvent: 'RSSI streaming stopped'}; }
  async getDeviceDiagnostics(id: string) { await wait(20); return {deviceId: id, reconnects: 0, disconnects: 0, lastRssi: -48, source: 'host-simulator'}; }
  async getBatteryHistory(id: string) { await wait(20); return [{timestamp: Date.now(), level: this.snapshot.devices.find((d) => d.id === id)?.battery ?? 0}]; }

  async startCapture(mode: CaptureMode) { await wait(); this.snapshot = {...this.snapshot, capture: 'recording', captureMode: mode, lastEvent: `${mode} capture started`}; }
  async stopCapture() { await wait(); this.snapshot = {...this.snapshot, capture: 'idle', lastEvent: 'Capture stopped and recording finalized'}; }
  async getAudioRoute() { return this.snapshot.audioRoute; }
  async startPhoneCall(phoneNumber: string) { await wait(); this.snapshot = {...this.snapshot, lastEvent: `Phone call requested for ${phoneNumber}`}; }
  async endPhoneCall() { await wait(); this.snapshot = {...this.snapshot, lastEvent: 'Phone call ended'}; }
  async setPhoneCallAudio(muted: boolean, speakerOn: boolean) { await wait(); this.snapshot = {...this.snapshot, lastEvent: `Call audio muted=${muted} speaker=${speakerOn}`}; }
  async setNotificationOnKillService(title: string) { await wait(); this.snapshot = {...this.snapshot, lastEvent: `Notification service configured: ${title}`}; }
  async getWifiNetwork() { await wait(10); return {ssid: 'host-simulator', connected: true}; }
  async setBackgroundMode(active: boolean) { await wait(); this.snapshot = {...this.snapshot, background: active ? 'active' : 'inactive', lastEvent: `Background mode ${active ? 'enabled' : 'disabled'}`}; }
  async getWatchStatus() { await wait(10); return {paired: false, reachable: false, battery: 0}; }
  async getCameraStatus() { await wait(10); return {available: false, permission: 'unavailable'}; }
  async capturePhoto() { await wait(20); return {accepted: false, reason: 'camera native module not installed in host MVP'}; }
}

export const omiNative: OmiNative = (NativeModules.OmiNative as OmiNative | undefined) ?? new HostMvpAdapter();
export const isNativeModuleInstalled = Boolean(NativeModules.OmiNative);
