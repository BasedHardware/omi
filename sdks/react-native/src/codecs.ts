/**
 * Codec utility functions for the Omi React Native SDK
 */

import { BleAudioCodec } from './types';

/**
 * Maps a BleAudioCodec enum value to its string representation
 * @param codec The BleAudioCodec enum value
 * @returns The string representation of the codec
 */
export function mapCodecToName(codec: BleAudioCodec): string {
  switch (codec) {
    case BleAudioCodec.PCM16:
      return 'PCM 16-bit';
    case BleAudioCodec.PCM8:
      return 'PCM 8-bit';
    case BleAudioCodec.OPUS:
      return 'Opus';
    default:
      return 'Unknown';
  }
}
