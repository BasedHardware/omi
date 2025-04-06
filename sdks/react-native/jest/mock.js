// Mock implementation for the Omi React Native SDK
const mock = {
  // Connection methods
  OmiConnection: jest.fn().mockImplementation(() => ({
    scanForDevices: jest.fn(() => jest.fn()),
    connect: jest.fn(() => Promise.resolve(true)),
    disconnect: jest.fn(() => Promise.resolve()),
    isConnected: jest.fn(() => true),
    getAudioCodec: jest.fn(() => Promise.resolve('pcm8')),
    startAudioBytesListener: jest.fn(() => Promise.resolve({ remove: jest.fn() })),
    stopAudioBytesListener: jest.fn(() => Promise.resolve()),
    getBatteryLevel: jest.fn(() => Promise.resolve(100)),
    connectedDeviceId: 'test-device-id',
  })),

  // Utility functions
  echo: jest.fn((word) => `Hello from Omi SDK! You said: ${word}`),
  VERSION: '1.0.1',

  // Enums
  BleAudioCodec: {
    PCM16: 'pcm16',
    PCM8: 'pcm8',
    OPUS: 'opus',
    UNKNOWN: 'unknown',
  },

  DeviceConnectionState: {
    CONNECTED: 'connected',
    DISCONNECTED: 'disconnected',
    CONNECTING: 'connecting',
    DISCONNECTING: 'disconnecting',
  },

  // Codec utilities
  mapCodecIdToEnum: jest.fn((codecId) => {
    switch (codecId) {
      case 0: return 'pcm16';
      case 1: return 'pcm8';
      case 20: return 'opus';
      default: return 'unknown';
    }
  }),

  mapCodecToName: jest.fn((codec) => {
    switch (codec) {
      case 'pcm16': return 'PCM 16-bit';
      case 'pcm8': return 'PCM 8-bit';
      case 'opus': return 'Opus';
      default: return 'Unknown';
    }
  }),
};

export default mock;
