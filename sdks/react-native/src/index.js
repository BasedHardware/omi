import { NativeModules, Platform, NativeEventEmitter } from 'react-native';
// Constants for BLE services and characteristics
export const BLE_CONSTANTS = {
    OMI_SERVICE_UUID: '19b10000-e8f2-537e-4f6c-d104768a1214',
    AUDIO_DATA_STREAM_CHARACTERISTIC_UUID: '19b10001-e8f2-537e-4f6c-d104768a1214',
    AUDIO_CODEC_CHARACTERISTIC_UUID: '19b10002-e8f2-537e-4f6c-d104768a1214',
    BUTTON_SERVICE_UUID: '23ba7924-0000-1000-7450-346eac492e92',
    BUTTON_TRIGGER_CHARACTERISTIC_UUID: '23ba7925-0000-1000-7450-346eac492e92',
    BATTERY_SERVICE_UUID: '0000180f-0000-1000-8000-00805f9b34fb',
    BATTERY_LEVEL_CHARACTERISTIC_UUID: '00002a19-0000-1000-8000-00805f9b34fb',
};
// Audio codec enum
export var BleAudioCodec;
(function (BleAudioCodec) {
    BleAudioCodec["PCM16"] = "pcm16";
    BleAudioCodec["PCM8"] = "pcm8";
    BleAudioCodec["MULAW16"] = "mulaw16";
    BleAudioCodec["MULAW8"] = "mulaw8";
    BleAudioCodec["OPUS"] = "opus";
    BleAudioCodec["UNKNOWN"] = "unknown";
})(BleAudioCodec || (BleAudioCodec = {}));
// Device connection state enum
export var DeviceConnectionState;
(function (DeviceConnectionState) {
    DeviceConnectionState["CONNECTED"] = "connected";
    DeviceConnectionState["DISCONNECTED"] = "disconnected";
})(DeviceConnectionState || (DeviceConnectionState = {}));
const LINKING_ERROR = `The package 'omi-react-native' doesn't seem to be linked. Make sure: \n\n` +
    Platform.select({ ios: "- You have run 'pod install'\n", default: '' }) +
    '- You rebuilt the app after installing the package\n' +
    '- You are not using Expo Go\n';
const OmiModule = NativeModules.OmiModule
    ? NativeModules.OmiModule
    : new Proxy({}, {
        get() {
            throw new Error(LINKING_ERROR);
        },
    });
// Create event emitter for native events
const eventEmitter = new NativeEventEmitter(OmiModule);
/**
 * Echo function for testing the SDK
 * @param message Message to echo
 * @returns Echoed message
 */
export function echo(message) {
    console.log('Hello from the Omi SDK!');
    return `SDK received: ${message}`;
}
/**
 * Connect to an Omi device
 * @param deviceId The ID of the device to connect to
 * @param onConnectionStateChanged Callback for connection state changes
 * @returns Promise that resolves when connected
 */
export function connect(deviceId, onConnectionStateChanged) {
    return OmiModule.connect(deviceId).then(() => {
        if (onConnectionStateChanged) {
            const subscription = eventEmitter.addListener('connectionStateChanged', ({ id, state }) => {
                if (id === deviceId) {
                    onConnectionStateChanged(id, state === 'connected'
                        ? DeviceConnectionState.CONNECTED
                        : DeviceConnectionState.DISCONNECTED);
                }
            });
            // Store subscription for cleanup
            activeSubscriptions.set(`connection_${deviceId}`, subscription);
        }
    });
}
/**
 * Disconnect from an Omi device
 * @param deviceId The ID of the device to disconnect from
 * @returns Promise that resolves when disconnected
 */
export function disconnect(deviceId) {
    // Clean up any subscriptions for this device
    cleanupSubscriptionsForDevice(deviceId);
    return OmiModule.disconnect(deviceId);
}
/**
 * Check if connected to an Omi device
 * @param deviceId The ID of the device to check
 * @returns Promise that resolves to a boolean indicating connection status
 */
export function isConnected(deviceId) {
    return OmiModule.isConnected(deviceId);
}
/**
 * Get the audio codec used by the device
 * @param deviceId The ID of the device
 * @returns Promise that resolves to the audio codec
 */
export function getAudioCodec(deviceId) {
    return OmiModule.getAudioCodec(deviceId).then((codecId) => {
        switch (codecId) {
            case 0:
                return BleAudioCodec.PCM16;
            case 1:
                return BleAudioCodec.PCM8;
            case 10:
                return BleAudioCodec.MULAW16;
            case 11:
                return BleAudioCodec.MULAW8;
            case 20:
                return BleAudioCodec.OPUS;
            default:
                return BleAudioCodec.UNKNOWN;
        }
    });
}
// Store active subscriptions for cleanup
const activeSubscriptions = new Map();
/**
 * Listen for audio bytes from the device
 * @param deviceId The ID of the device
 * @param onAudioBytesReceived Callback for received audio bytes
 * @returns Promise that resolves to a function to remove the listener
 */
export function getBleAudioBytesListener(deviceId, onAudioBytesReceived) {
    return OmiModule.startAudioBytesNotifications(deviceId).then(() => {
        const subscription = eventEmitter.addListener('audioBytesReceived', ({ id, bytes }) => {
            if (id === deviceId) {
                onAudioBytesReceived(bytes);
            }
        });
        // Store subscription for cleanup
        activeSubscriptions.set(`audio_${deviceId}`, subscription);
        // Return function to remove listener
        return () => {
            subscription.remove();
            activeSubscriptions.delete(`audio_${deviceId}`);
            OmiModule.stopAudioBytesNotifications(deviceId);
        };
    });
}
/**
 * Clean up subscriptions for a specific device
 * @param deviceId The ID of the device
 */
function cleanupSubscriptionsForDevice(deviceId) {
    for (const [key, subscription] of activeSubscriptions.entries()) {
        if (key.includes(deviceId)) {
            subscription.remove();
            activeSubscriptions.delete(key);
        }
    }
}
export { OmiModule };
export * from './omi';
