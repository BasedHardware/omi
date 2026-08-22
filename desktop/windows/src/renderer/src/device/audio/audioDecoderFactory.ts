/**
 * Decoder dispatch — Windows port of the AudioDecoderFactory in macOS
 * Audio/AudioCodecDecoder.swift. Only 'unknown' is unsupported; LC3 counts as
 * supported but not fully supported, which downgrades quality rather than
 * refusing the session.
 */

import type { BleAudioCodec } from '../protocol/deviceTypes'
import {
  Lc3SilenceDecoder,
  MuLawDecoder,
  PcmDecoder,
  type AudioDecoder,
  type AudioDecoderSinks
} from './audioCodecDecoder'
import { OpusFrameDecoder } from './opusFrameDecoder'
import { AacFrameDecoder } from './aacFrameDecoder'

export const isCodecSupported = (codec: BleAudioCodec): boolean => codec !== 'unknown'

export const hasFullCodecSupport = (codec: BleAudioCodec): boolean =>
  codec !== 'unknown' && codec !== 'lc3FS1030'

export const createAudioDecoder = (
  codec: BleAudioCodec,
  sinks: AudioDecoderSinks
): AudioDecoder | null => {
  switch (codec) {
    case 'pcm8':
    case 'pcm16':
      return new PcmDecoder(codec)
    case 'mulaw8':
    case 'mulaw16':
      return new MuLawDecoder(codec)
    case 'opus':
    case 'opusFS320':
      return new OpusFrameDecoder(codec)
    case 'aac':
      return new AacFrameDecoder(sinks)
    case 'lc3FS1030':
      return new Lc3SilenceDecoder()
    case 'unknown':
      return null
  }
}
