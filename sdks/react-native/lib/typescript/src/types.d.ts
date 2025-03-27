/**
 * Types for the Omi React Native SDK
 */
export declare enum BleAudioCodec {
    PCM16 = "pcm16",
    PCM8 = "pcm8",
    MULAW16 = "mulaw16",
    MULAW8 = "mulaw8",
    OPUS = "opus",
    UNKNOWN = "unknown"
}
export declare enum DeviceConnectionState {
    CONNECTED = "connected",
    DISCONNECTED = "disconnected"
}
export interface OmiDevice {
    id: string;
    name: string;
    rssi: number;
}
export interface OmiNativeModule {
    connect(deviceId: string): Promise<void>;
    disconnect(deviceId: string): Promise<void>;
    isConnected(deviceId: string): Promise<boolean>;
    getAudioCodec(deviceId: string): Promise<number>;
    startAudioBytesNotifications(deviceId: string): Promise<void>;
    stopAudioBytesNotifications(deviceId: string): Promise<void>;
    startScan(): Promise<void>;
    stopScan(): Promise<void>;
}
//# sourceMappingURL=types.d.ts.map