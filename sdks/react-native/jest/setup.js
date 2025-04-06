// Mock the native modules
jest.mock('react-native', () => {
  const RN = jest.requireActual('react-native');
  
  RN.NativeModules.OmiModule = {
    connect: jest.fn(() => Promise.resolve()),
    disconnect: jest.fn(() => Promise.resolve()),
    isConnected: jest.fn(() => Promise.resolve(false)),
    getAudioCodec: jest.fn(() => Promise.resolve(1)),
    startAudioBytesNotifications: jest.fn(() => Promise.resolve()),
    stopAudioBytesNotifications: jest.fn(() => Promise.resolve()),
    getBatteryLevel: jest.fn(() => Promise.resolve(100)),
    startScan: jest.fn(() => Promise.resolve()),
    stopScan: jest.fn(() => Promise.resolve()),
  };

  return RN;
});

// Mock the BLE library
jest.mock('react-native-ble-plx', () => {
  return {
    BleManager: jest.fn().mockImplementation(() => {
      return {
        startDeviceScan: jest.fn(),
        stopDeviceScan: jest.fn(),
        connectToDevice: jest.fn(() => Promise.resolve({
          id: 'test-device-id',
          name: 'Test Device',
          discoverAllServicesAndCharacteristics: jest.fn(() => Promise.resolve()),
          services: jest.fn(() => Promise.resolve([])),
          cancelConnection: jest.fn(() => Promise.resolve()),
          onDisconnected: jest.fn(() => ({ remove: jest.fn() })),
        })),
        state: jest.fn(() => Promise.resolve('PoweredOn')),
      };
    }),
    Subscription: jest.fn(),
    Device: jest.fn(),
  };
});

// Mock base-64
jest.mock('base-64', () => ({
  decode: jest.fn((str) => str),
}));
