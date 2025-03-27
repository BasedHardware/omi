import { BleManager, Device } from 'react-native-ble-plx';
import { DeviceConnectionState, BleAudioCodec, OmiDevice } from './types';

// Service and characteristic UUIDs
const OMI_SERVICE_UUID = '19b10000-e8f2-537e-4f6c-d104768a1214';
const AUDIO_CODEC_CHARACTERISTIC_UUID = '19b10002-e8f2-537e-4f6c-d104768a1214';

export class OmiConnection {
  private bleManager: BleManager;
  private device: Device | null = null;
  private isConnecting: boolean = false;

  constructor() {
    this.bleManager = new BleManager();
  }

  /**
   * Scan for Omi devices
   * @param onDeviceFound Callback when a device is found
   * @param timeoutMs Scan timeout in milliseconds
   * @returns A function to stop scanning
   */
  scanForDevices(
    onDeviceFound: (device: OmiDevice) => void,
    timeoutMs: number = 10000
  ): () => void {
    this.bleManager.startDeviceScan(
      null,
      null,
      (error, device) => {
        if (error) {
          console.error('Scan error:', error);
          return;
        }
        if (device && device.name) {
          onDeviceFound({
            id: device.id,
            name: device.name,
            rssi: device.rssi || 0,
          });
        }
      }
    );

    // Set timeout to stop scanning
    const timeoutId = setTimeout(() => {
      this.bleManager.stopDeviceScan();
    }, timeoutMs);

    // Return function to stop scanning
    return () => {
      clearTimeout(timeoutId);
      this.bleManager.stopDeviceScan();
    };
  }

  /**
   * Connect to an Omi device
   * @param deviceId The device ID to connect to
   * @param onConnectionStateChanged Callback for connection state changes
   * @returns Promise that resolves when connected
   */
  async connect(
    deviceId: string,
    onConnectionStateChanged?: (
      deviceId: string,
      state: DeviceConnectionState
    ) => void
  ): Promise<boolean> {
    if (this.isConnecting) {
      return false;
    }

    this.isConnecting = true;

    try {
      // Connect to the device
      const device = await this.bleManager.connectToDevice(deviceId);
      
      // Discover services and characteristics
      await device.discoverAllServicesAndCharacteristics();
      
      this.device = device;
      
      // Set up disconnection listener
      device.onDisconnected((_, disconnectedDevice) => {
        this.device = null;
        if (onConnectionStateChanged) {
          onConnectionStateChanged(
            disconnectedDevice.id,
            DeviceConnectionState.DISCONNECTED
          );
        }
      });

      if (onConnectionStateChanged) {
        onConnectionStateChanged(deviceId, DeviceConnectionState.CONNECTED);
      }

      this.isConnecting = false;
      return true;
    } catch (error) {
      console.error('Connection error:', error);
      this.isConnecting = false;
      return false;
    }
  }

  /**
   * Disconnect from the currently connected device
   */
  async disconnect(): Promise<void> {
    if (this.device) {
      await this.device.cancelConnection();
      this.device = null;
    }
  }

  /**
   * Check if connected to a device
   * @returns True if connected
   */
  isConnected(): boolean {
    return this.device !== null;
  }

  /**
   * Convert base64 string to byte array
   * @param base64 Base64 encoded string
   * @returns Uint8Array of bytes
   */
  private base64ToBytes(base64: string): Uint8Array {
    // React Native compatible base64 decoding
    const chars = 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/=';
    const lookup = new Uint8Array(256);
    for (let i = 0; i < chars.length; i++) {
      lookup[chars.charCodeAt(i)] = i;
    }
    
    const len = base64.length;
    let bufferLength = base64.length * 0.75;
    if (base64[len - 1] === '=') {
      bufferLength--;
      if (base64[len - 2] === '=') {
        bufferLength--;
      }
    }
    
    const bytes = new Uint8Array(bufferLength);
    
    let p = 0;
    let encoded1, encoded2, encoded3, encoded4;
    
    for (let i = 0; i < len; i += 4) {
      encoded1 = lookup[base64.charCodeAt(i)];
      encoded2 = lookup[base64.charCodeAt(i + 1)];
      encoded3 = lookup[base64.charCodeAt(i + 2)];
      encoded4 = lookup[base64.charCodeAt(i + 3)];
      
      bytes[p++] = (encoded1 << 2) | (encoded2 >> 4);
      if (encoded3 !== 64) {
        bytes[p++] = ((encoded2 & 15) << 4) | (encoded3 >> 2);
      }
      if (encoded4 !== 64) {
        bytes[p++] = ((encoded3 & 3) << 6) | encoded4;
      }
    }
    
    return bytes;
  }

  /**
   * Get the audio codec used by the device
   * @returns Promise that resolves with the audio codec
   */
  async getAudioCodec(): Promise<BleAudioCodec> {
    if (!this.device) {
      throw new Error('Device not connected');
    }

    try {
      // Get the Omi service
      const services = await this.device.services();
      const omiService = services.find(
        (service) => service.uuid.toLowerCase() === OMI_SERVICE_UUID.toLowerCase()
      );

      if (!omiService) {
        console.error('Omi service not found');
        return BleAudioCodec.PCM8; // Default codec
      }

      // Get the audio codec characteristic
      const characteristics = await omiService.characteristics();
      const codecCharacteristic = characteristics.find(
        (char) => char.uuid.toLowerCase() === AUDIO_CODEC_CHARACTERISTIC_UUID.toLowerCase()
      );

      if (!codecCharacteristic) {
        console.error('Audio codec characteristic not found');
        return BleAudioCodec.PCM8; // Default codec
      }

      // Default codec is PCM8
      let codecId = 1;
      let codec = BleAudioCodec.PCM8;

      // Read the codec value
      const codecValue = await codecCharacteristic.read();
      const base64Value = codecValue.value || '';
      
      if (base64Value) {
        // Decode base64 to get the first byte
        const bytes = this.base64ToBytes(base64Value);
        if (bytes.length > 0) {
          codecId = bytes[0];
        }
      }

      // Map codec ID to enum - following the same pattern as in omi_connection.dart
      switch (codecId) {
        // case 0:
        //   codec = BleAudioCodec.PCM16;
        case 1:
          codec = BleAudioCodec.PCM8;
          break;
        // case 10:
        //   codec = BleAudioCodec.MULAW16;
        // case 11:
        //   codec = BleAudioCodec.MULAW8;
        case 20:
          codec = BleAudioCodec.OPUS;
          break;
        default:
          console.warn(`Unknown codec id: ${codecId}`);
          break;
      }

      return codec;
    } catch (error) {
      console.error('Error getting audio codec:', error);
      return BleAudioCodec.PCM8; // Default codec on error
    }
  }
}
