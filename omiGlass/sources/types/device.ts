import { Device } from 'react-native-ble-plx';

/**
 * Cross-platform device interface for OMI Glass devices
 * Supports both Web Bluetooth API and React Native BLE
 */
export interface OmiDevice {
    /** Unique device identifier */
    id: string;
    
    /** Device name */
    name: string;
    
    /** Web Bluetooth GATT server (web platform only) */
    gatt?: BluetoothRemoteGATTServer;
    
    /** React Native BLE device (mobile platforms only) */
    nativeDevice?: Device;
}

/**
 * Device connection state
 */
export enum DeviceConnectionState {
    DISCONNECTED = 'disconnected',
    CONNECTING = 'connecting',
    CONNECTED = 'connected',
    RECONNECTING = 'reconnecting'
}

/**
 * Service and characteristic UUIDs for OMI Glass
 */
export const OMI_UUIDS = {
    SERVICE: '19B10000-E8F2-537E-4F6C-D104768A1214',
    AUDIO_CODEC: '19b10002-e8f2-537e-4f6c-d104768a1214',
    AUDIO_DATA_STREAM: '19b10001-e8f2-537e-4f6c-d104768a1214',
    PHOTO_DATA: '19b10005-e8f2-537e-4f6c-d104768a1214',
    PHOTO_CONTROL: '19b10006-e8f2-537e-4f6c-d104768a1214',
} as const;
