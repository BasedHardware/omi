import { BleManager, Device, Subscription, ConnectionPriority } from 'react-native-ble-plx';
import { DeviceConnectionState, OmiDevice, BleAudioCodec} from './types';
import { Platform } from 'react-native';

// Service and characteristic UUIDs
const OMI_SERVICE_UUID = '19b10000-e8f2-537e-4f6c-d104768a1214';
const AUDIO_CODEC_CHARACTERISTIC_UUID = '19b10002-e8f2-537e-4f6c-d104768a1214';
const AUDIO_DATA_STREAM_CHARACTERISTIC_UUID = '19b10001-e8f2-537e-4f6c-d104768a1214';

// Battery service UUIDs
const BATTERY_SERVICE_UUID = '0000180f-0000-1000-8000-00805f9b34fb';
const BATTERY_LEVEL_CHARACTERISTIC_UUID = '00002a19-0000-1000-8000-00805f9b34fb';

export class OmiConnection {
  private bleManager: BleManager;
  private device: Device | null = null;
  private isConnecting: boolean = false;
  private _connectedDeviceId: string | null = null;

  // Public getter for the connected device ID
  get connectedDeviceId(): string | null {
    return this._connectedDeviceId;
  }

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
      (error: any, device: any) => {
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
      // Connect to the device with MTU request for Android
      const connectionOptions = Platform.OS === 'android'
        ? { requestMTU: 512 }
        : undefined;

      const device = await this.bleManager.connectToDevice(deviceId, connectionOptions);

      if (Platform.OS === 'android') {
        console.log('Requested MTU size of 512 during connection');
      }

      // Discover services and characteristics
      await device.discoverAllServicesAndCharacteristics();

      this.device = device;
      this._connectedDeviceId = deviceId;

      // Set up disconnection listener
      device.onDisconnected((_: any, disconnectedDevice: any) => {
        this.device = null;
        this._connectedDeviceId = null;
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
      this._connectedDeviceId = null;
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
    let encoded1: number = 0;
    let encoded2: number = 0;
    let encoded3: number = 0;
    let encoded4: number = 0;

    for (let i = 0; i < len; i += 4) {
      encoded1 = lookup[base64.charCodeAt(i)] || 0;
      encoded2 = lookup[base64.charCodeAt(i + 1)] || 0;
      encoded3 = lookup[base64.charCodeAt(i + 2)] || 0;
      encoded4 = lookup[base64.charCodeAt(i + 3)] || 0;

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
        (service: any) => service.uuid.toLowerCase() === OMI_SERVICE_UUID.toLowerCase()
      );

      if (!omiService) {
        console.error('Omi service not found');
        return BleAudioCodec.PCM8; // Default codec
      }

      // Get the audio codec characteristic
      const characteristics = await omiService.characteristics();
      const codecCharacteristic = characteristics.find(
        (char: any) => char.uuid.toLowerCase() === AUDIO_CODEC_CHARACTERISTIC_UUID.toLowerCase()
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
          codecId = bytes[0] || 1; // Default to 1 if undefined
        }
      }

      // Map codec ID to enum - following the same pattern as in omi_connection.dart
      switch (codecId) {
        case 0:
          codec = BleAudioCodec.PCM16;
          break;
        case 1:
          codec = BleAudioCodec.PCM8;
          break;
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


  /**
   * Start listening for audio bytes from the device
   * @param onAudioBytesReceived Callback function that receives audio bytes
   * @returns Promise that resolves with a subscription that can be used to stop listening
   */
  async startAudioBytesListener(
    onAudioBytesReceived: (bytes: number[]) => void
  ): Promise<Subscription | null> {
    if (!this.device) {
      throw new Error('Device not connected');
    }

    try {
      // Get the Omi service
      const services = await this.device.services();
      const omiService = services.find(
        (service: any) => service.uuid.toLowerCase() === OMI_SERVICE_UUID.toLowerCase()
      );

      if (!omiService) {
        console.error('Omi service not found');
        return null;
      }

      // Get the audio data stream characteristic
      const characteristics = await omiService.characteristics();
      const audioDataStreamCharacteristic = characteristics.find(
        (char: any) => char.uuid.toLowerCase() === AUDIO_DATA_STREAM_CHARACTERISTIC_UUID.toLowerCase()
      );

      if (!audioDataStreamCharacteristic) {
        console.error('Audio data stream characteristic not found');
        return null;
      }

      try {
        console.log('Setting up audio bytes notification for characteristic:',
          audioDataStreamCharacteristic.uuid);

        // First try to read the characteristic to ensure it's accessible
        try {
          const initialValue = await audioDataStreamCharacteristic.read();
          console.log('Initial audio characteristic value length:', initialValue?.value?.length || 0);
        } catch (readError) {
          console.log('Could not read initial value, continuing anyway:', readError);
        }

        // Set up the monitor - this automatically enables notifications
        const subscription = audioDataStreamCharacteristic.monitor((error: any, characteristic: any) => {
          if (error) {
            console.error('Audio data stream notification error:', error);
            return;
          }

          // console.log('Received audio data notification');
          if (characteristic?.value) {
            const base64Value = characteristic.value;
            // console.log('Received base64 value of length:', base64Value.length);

            try {
              const bytes = this.base64ToBytes(base64Value);
              // console.log('Decoded bytes length:', bytes.length);

              if (bytes.length > 0) {
                // Convert Uint8Array to number[]
                const byteArray = Array.from(bytes);

                // Trim the first 3 bytes (header) as seen in the Flutter implementation
                const trimmedBytes = byteArray.length > 3 ? byteArray.slice(3) : byteArray;

                // Send to callback
                onAudioBytesReceived(trimmedBytes);

              }
            } catch (decodeError) {
              console.error('Error decoding base64 data:', decodeError);
            }
          } else {
            console.log('Received notification but no value');
          }
        });

        console.log('Subscribed to audio bytes stream from Omi Device');

        // Return the subscription so it can be used to stop listening
        return subscription;
      } catch (e) {
        console.error('Error subscribing to audio data stream:', e);
        return null;
      }
    } catch (error) {
      console.error('Error starting audio bytes listener:', error);
      return null;
    }
  }

  /**
   * Stop listening for audio bytes
   * @param subscription The subscription returned by startAudioBytesListener
   */
  async stopAudioBytesListener(subscription: Subscription): Promise<void> {
    if (subscription) {
      subscription.remove();
    }
  }

  /**
   * Get the current battery level from the device
   * @returns Promise that resolves with the battery level percentage (0-100)
   */
  async getBatteryLevel(): Promise<number> {
    if (!this.device) {
      throw new Error('Device not connected');
    }

    try {
      // Get the Battery service
      const services = await this.device.services();
      const batteryService = services.find(
        (service: any) => service.uuid.toLowerCase() === BATTERY_SERVICE_UUID.toLowerCase()
      );

      if (!batteryService) {
        console.error('Battery service not found');
        return -1;
      }

      // Get the battery level characteristic
      const characteristics = await batteryService.characteristics();
      const batteryLevelCharacteristic = characteristics.find(
        (char: any) => char.uuid.toLowerCase() === BATTERY_LEVEL_CHARACTERISTIC_UUID.toLowerCase()
      );

      if (!batteryLevelCharacteristic) {
        console.error('Battery level characteristic not found');
        return -1;
      }

      // Read the battery level value
      const batteryValue = await batteryLevelCharacteristic.read();
      const base64Value = batteryValue.value || '';

      if (base64Value) {
        // Decode base64 to get the first byte
        const bytes = this.base64ToBytes(base64Value);
        if (bytes.length > 0) {
          return bytes[0] || -1; // Battery level is a percentage (0-100), use -1 if undefined
        }
      }

      return -1;
    } catch (error) {
      console.error('Error getting battery level:', error);
      return -1;
    }
  }

  /**
   * Request a specific connection priority (Android only).
   * @param priority Connection priority level from ConnectionPriority enum
   * @returns Promise that resolves when the request is attempted.
   */
  async requestConnectionPriority(priority: ConnectionPriority): Promise<void> {
    if (!this.device) {
      console.warn('Cannot request connection priority: Device not connected.');
      return Promise.reject(new Error('Device not connected'));
    }

    if (Platform.OS === 'android') {
      try {
        // Pass the numeric value of the enum to the native function
        await this.device.requestConnectionPriority(priority);
        console.log(`Requested connection priority: ${priority}`);
      } catch (error) {
        console.error('Failed to request connection priority:', error);
        // Optionally re-throw or let the caller decide how to handle
        return Promise.reject(error);
      }
    } else {
      console.log('Connection priority request is an Android-specific feature and was not attempted on this platform.');
      // Resolve promise for non-Android platforms as it's a no-op
      return Promise.resolve();
    }
  }
}
