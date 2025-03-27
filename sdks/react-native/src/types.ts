/**
 * Types for the Omi React Native SDK
 */

export enum BleAudioCodec {
  PCM16 = 'pcm16',
  PCM8 = 'pcm8',
  MULAW16 = 'mulaw16',
  MULAW8 = 'mulaw8',
  OPUS = 'opus',
  UNKNOWN = 'unknown',
}

export enum DeviceConnectionState {
  CONNECTED = 'connected',
  DISCONNECTED = 'disconnected',
}

export interface OmiDevice {
  id: string;
  name: string;
  rssi: number;
}

export interface OmiNativeModule {
  // Connection methods
  connect(deviceId: string): Promise<void>;
  disconnect(deviceId: string): Promise<void>;
  isConnected(deviceId: string): Promise<boolean>;
  
  // Audio methods
  getAudioCodec(deviceId: string): Promise<number>;
  startAudioBytesNotifications(deviceId: string): Promise<void>;
  stopAudioBytesNotifications(deviceId: string): Promise<void>;
  
  // Scanning methods
  startScan(): Promise<void>;
  stopScan(): Promise<void>;
}
