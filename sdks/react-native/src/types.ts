/**
 * Types for the Omi React Native SDK
 */

export enum BleAudioCodec {
  PCM16 = 'pcm16',
  PCM8 = 'pcm8',
  OPUS = 'opus',
  UNKNOWN = 'unknown',
}

export enum DeviceConnectionState {
  CONNECTED = 'connected',
  DISCONNECTED = 'disconnected',
  CONNECTING = 'connecting',
  DISCONNECTING = 'disconnecting',
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
  
  // Battery methods
  getBatteryLevel(deviceId: string): Promise<number>;
  
  // Scanning methods
  startScan(): Promise<void>;
  stopScan(): Promise<void>;
}

/**
 * Options for audio processing
 */
export interface AudioProcessingOptions {
  sampleRate?: number;
  channels?: number;
  bitDepth?: number;
  codec?: BleAudioCodec;
}

/**
 * Interface for audio data events
 */
export interface AudioDataEvent {
  deviceId: string;
  data: Uint8Array;
  timestamp: number;
}

/**
 * Interface for connection state change events
 */
export interface ConnectionStateEvent {
  deviceId: string;
  state: DeviceConnectionState;
}

