export declare const BLE_CONSTANTS: {
    OMI_SERVICE_UUID: string;
    AUDIO_DATA_STREAM_CHARACTERISTIC_UUID: string;
    AUDIO_CODEC_CHARACTERISTIC_UUID: string;
    BUTTON_SERVICE_UUID: string;
    BUTTON_TRIGGER_CHARACTERISTIC_UUID: string;
    BATTERY_SERVICE_UUID: string;
    BATTERY_LEVEL_CHARACTERISTIC_UUID: string;
};
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
declare const OmiModule: any;
/**
 * Echo function for testing the SDK
 * @param message Message to echo
 * @returns Echoed message
 */
export declare function echo(message: string): string;
/**
 * Connect to an Omi device
 * @param deviceId The ID of the device to connect to
 * @param onConnectionStateChanged Callback for connection state changes
 * @returns Promise that resolves when connected
 */
export declare function connect(deviceId: string, onConnectionStateChanged?: (deviceId: string, state: DeviceConnectionState) => void): Promise<void>;
/**
 * Disconnect from an Omi device
 * @param deviceId The ID of the device to disconnect from
 * @returns Promise that resolves when disconnected
 */
export declare function disconnect(deviceId: string): Promise<void>;
/**
 * Check if connected to an Omi device
 * @param deviceId The ID of the device to check
 * @returns Promise that resolves to a boolean indicating connection status
 */
export declare function isConnected(deviceId: string): Promise<boolean>;
/**
 * Get the audio codec used by the device
 * @param deviceId The ID of the device
 * @returns Promise that resolves to the audio codec
 */
export declare function getAudioCodec(deviceId: string): Promise<BleAudioCodec>;
/**
 * Listen for audio bytes from the device
 * @param deviceId The ID of the device
 * @param onAudioBytesReceived Callback for received audio bytes
 * @returns Promise that resolves to a function to remove the listener
 */
export declare function getBleAudioBytesListener(deviceId: string, onAudioBytesReceived: (bytes: number[]) => void): Promise<() => void>;
export { OmiModule };
export * from './omi';
//# sourceMappingURL=index.d.ts.map