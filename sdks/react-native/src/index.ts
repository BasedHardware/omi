/**
 * Omi SDK for React Native
 * TypeScript implementation for interacting with Omi devices
 */

// Export types and classes
export { OmiConnection } from './OmiConnection';
export { BleAudioCodec } from './types';
export { 
  DeviceConnectionState
} from './types';
export type { 
  OmiDevice, 
  OmiNativeModule,
  AudioProcessingOptions,
  AudioDataEvent,
  ConnectionStateEvent
} from './types';
export { mapCodecToName } from './codecs';

/**
 * Version of the Omi React Native SDK
 */
export const VERSION = '1.0.1';

/**
 * Echo function that returns a greeting with the provided word
 * @param word - The word to echo back
 * @returns A greeting string with the provided word
 */
export const echo = (word: string): string => {
  console.log('Omi SDK: Echo function called');
  return `Hello from Omi SDK! You said: ${word}`;
};
