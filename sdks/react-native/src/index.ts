/**
 * Omi SDK for React Native
 */

/**
 * Echo function that returns a greeting with the provided word
 * @param word - The word to echo back
 * @returns A greeting string with the provided word
 */
export const echo = (word: string): string => {
  console.log('Omi SDK: Echo function called');
  return `Hello from Omi SDK! You said: ${word}`;
};

// Export types and classes
export { OmiConnection } from './OmiConnection';
export { BleAudioCodec, DeviceConnectionState } from './types';
export type { OmiDevice } from './types';
