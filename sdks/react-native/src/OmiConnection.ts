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
    console.log("thinh:yo");
    this.bleManager.startDeviceScan(
      null,
      null,
      (error, device) => {
        if (error) {
          console.error('Scan error:', error);
          return;
        }

        console.log("thinh:hey");

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

      // Read the codec value
      const codecValue = await codecCharacteristic.read();
      const codecBytes = Buffer.from(codecValue.value || '', 'base64');
      
      if (codecBytes.length === 0) {
        return BleAudioCodec.PCM8; // Default codec
      }

      const codecId = codecBytes[0];
      
      // Map codec ID to enum
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
          console.warn(`Unknown codec ID: ${codecId}`);
          return BleAudioCodec.UNKNOWN;
      }
    } catch (error) {
      console.error('Error getting audio codec:', error);
      return BleAudioCodec.PCM8; // Default codec on error
    }
  }
}
