import 'dart:typed_data';

import 'package:flutter/material.dart';

import 'package:opus_dart/opus_dart.dart';

import 'package:omi/backend/schema/bt_device/bt_device.dart';
import 'package:omi/utils/audio/wav_bytes.dart';
import 'package:omi/utils/logger.dart';

abstract class IAudioTranscoder {
  Uint8List transcode(Uint8List audioData);
  Uint8List transcodeFrames(List<Uint8List> frames);
  String get outputFormat;
  String get mimeType;
  String get fileExtension;
}

class PassThroughTranscoder implements IAudioTranscoder {
  final String format;

  PassThroughTranscoder({this.format = 'wav'});

  @override
  Uint8List transcode(Uint8List data) => data;

  @override
  Uint8List transcodeFrames(List<Uint8List> frames) {
    final totalLength = frames.fold<int>(0, (sum, frame) => sum + frame.length);
    final result = Uint8List(totalLength);
    int offset = 0;
    for (final frame in frames) {
      result.setRange(offset, offset + frame.length, frame);
      offset += frame.length;
    }
    return result;
  }

  @override
  String get outputFormat => format;

  @override
  String get mimeType => 'audio/$format';

  @override
  String get fileExtension => format;
}

class PcmToWavTranscoder implements IAudioTranscoder {
  final int sampleRate;
  final int bitsPerSample;
  final int channels;

  PcmToWavTranscoder({
    this.sampleRate = 16000,
    this.bitsPerSample = 16,
    this.channels = 1,
  });

  @override
  Uint8List transcode(Uint8List pcmData) {
    return WavBytes.fromPcm(
      pcmData,
      sampleRate: sampleRate,
      numChannels: channels,
    ).asBytes();
  }

  @override
  Uint8List transcodeFrames(List<Uint8List> frames) {
    final totalLength = frames.fold<int>(0, (sum, frame) => sum + frame.length);
    final pcmData = Uint8List(totalLength);
    int offset = 0;
    for (final frame in frames) {
      pcmData.setRange(offset, offset + frame.length, frame);
      offset += frame.length;
    }
    return transcode(pcmData);
  }

  @override
  String get outputFormat => 'wav';

  @override
  String get mimeType => 'audio/wav';

  @override
  String get fileExtension => 'wav';
}

class OpusToWavTranscoder implements IAudioTranscoder {
  final int sampleRate;
  final int channels;
  final SimpleOpusDecoder _decoder;

  OpusToWavTranscoder({
    this.sampleRate = 16000,
    this.channels = 1,
  }) : _decoder = SimpleOpusDecoder(sampleRate: sampleRate, channels: channels);

  @override
  Uint8List transcode(Uint8List opusData) {
    final pcmSamples = _decoder.decode(input: opusData);
    return WavBytesUtil.getUInt8ListBytes(pcmSamples.toList(), sampleRate);
  }

  @override
  Uint8List transcodeFrames(List<Uint8List> frames) {
    final List<int> allPcmSamples = [];
    for (final frame in frames) {
      try {
        final pcmSamples = _decoder.decode(input: frame);
        allPcmSamples.addAll(pcmSamples);
      } catch (e) {
        Logger.debug('[OpusToWav] Failed to decode frame: $e');
      }
    }
    return WavBytesUtil.getUInt8ListBytes(allPcmSamples, sampleRate);
  }

  @override
  String get outputFormat => 'wav';

  @override
  String get mimeType => 'audio/wav';

  @override
  String get fileExtension => 'wav';
}

/// Transcoder that outputs raw PCM bytes (no WAV header)
/// Used for streaming WebSocket APIs that expect raw audio
class RawPcmTranscoder implements IAudioTranscoder {
  final int sampleRate;
  final int channels;

  RawPcmTranscoder({
    this.sampleRate = 16000,
    this.channels = 1,
  });

  @override
  Uint8List transcode(Uint8List pcmData) => pcmData;

  @override
  Uint8List transcodeFrames(List<Uint8List> frames) {
    final totalLength = frames.fold<int>(0, (sum, frame) => sum + frame.length);
    final result = Uint8List(totalLength);
    int offset = 0;
    for (final frame in frames) {
      result.setRange(offset, offset + frame.length, frame);
      offset += frame.length;
    }
    return result;
  }

  @override
  String get outputFormat => 'pcm';

  @override
  String get mimeType => 'audio/pcm';

  @override
  String get fileExtension => 'pcm';
}

/// Transcoder that decodes Opus to raw PCM bytes (no WAV header)
/// Used for streaming WebSocket APIs that expect raw audio
class OpusToRawPcmTranscoder implements IAudioTranscoder {
  final int sampleRate;
  final int channels;
  final SimpleOpusDecoder _decoder;

  OpusToRawPcmTranscoder({
    this.sampleRate = 16000,
    this.channels = 1,
  }) : _decoder = SimpleOpusDecoder(sampleRate: sampleRate, channels: channels);

  @override
  Uint8List transcode(Uint8List opusData) {
    final pcmSamples = _decoder.decode(input: opusData);
    // Convert Int16List to Uint8List (little-endian)
    final bytes = Uint8List(pcmSamples.length * 2);
    final byteData = ByteData.view(bytes.buffer);
    for (int i = 0; i < pcmSamples.length; i++) {
      byteData.setInt16(i * 2, pcmSamples[i], Endian.little);
    }
    return bytes;
  }

  @override
  Uint8List transcodeFrames(List<Uint8List> frames) {
    final List<int> allPcmSamples = [];
    for (final frame in frames) {
      try {
        final pcmSamples = _decoder.decode(input: frame);
        allPcmSamples.addAll(pcmSamples);
      } catch (e) {
        Logger.debug('[OpusToRawPcm] Failed to decode frame: $e');
      }
    }
    // Convert to bytes (little-endian 16-bit)
    final bytes = Uint8List(allPcmSamples.length * 2);
    final byteData = ByteData.view(bytes.buffer);
    for (int i = 0; i < allPcmSamples.length; i++) {
      byteData.setInt16(i * 2, allPcmSamples[i], Endian.little);
    }
    return bytes;
  }

  @override
  String get outputFormat => 'pcm';

  @override
  String get mimeType => 'audio/pcm';

  @override
  String get fileExtension => 'pcm';
}

class OpusFramesToWavTranscoder implements IAudioTranscoder {
  final int sampleRate;
  final int channels;
  final int frameSizeBytes;
  final SimpleOpusDecoder _decoder;

  OpusFramesToWavTranscoder({
    this.sampleRate = 16000,
    this.channels = 1,
    this.frameSizeBytes = 80,
  }) : _decoder = SimpleOpusDecoder(sampleRate: sampleRate, channels: channels);

  @override
  Uint8List transcode(Uint8List opusFramesData) {
    final List<int> allPcmSamples = [];

    int offset = 0;
    while (offset + frameSizeBytes <= opusFramesData.length) {
      final frame = opusFramesData.sublist(offset, offset + frameSizeBytes);
      try {
        final pcmSamples = _decoder.decode(input: Uint8List.fromList(frame));
        allPcmSamples.addAll(pcmSamples);
      } catch (e) {
        Logger.debug('[OpusFramesToWav] Failed to decode frame at offset $offset: $e');
      }
      offset += frameSizeBytes;
    }

    if (offset < opusFramesData.length) {
      final remainingFrame = opusFramesData.sublist(offset);
      try {
        final pcmSamples = _decoder.decode(input: Uint8List.fromList(remainingFrame));
        allPcmSamples.addAll(pcmSamples);
      } catch (e) {
        Logger.debug('[OpusFramesToWav] Failed to decode remaining frame: $e');
      }
    }

    return WavBytesUtil.getUInt8ListBytes(allPcmSamples, sampleRate);
  }

  @override
  Uint8List transcodeFrames(List<Uint8List> frames) {
    final List<int> allPcmSamples = [];
    for (final frame in frames) {
      try {
        final pcmSamples = _decoder.decode(input: frame);
        allPcmSamples.addAll(pcmSamples);
      } catch (e) {
        Logger.debug('[OpusFramesToWav] Failed to decode frame: $e');
      }
    }
    return WavBytesUtil.getUInt8ListBytes(allPcmSamples, sampleRate);
  }

  @override
  String get outputFormat => 'wav';

  @override
  String get mimeType => 'audio/wav';

  @override
  String get fileExtension => 'wav';
}

class AudioTranscoderFactory {
  static IAudioTranscoder createToWav({
    required BleAudioCodec sourceCodec,
    required int sampleRate,
    int channels = 1,
  }) {
    switch (sourceCodec) {
      case BleAudioCodec.pcm8:
        return PcmToWavTranscoder(sampleRate: 8000, channels: channels);
      case BleAudioCodec.pcm16:
        return PcmToWavTranscoder(sampleRate: sampleRate, channels: channels);
      case BleAudioCodec.opus:
      case BleAudioCodec.opusFS320:
        return OpusToWavTranscoder(sampleRate: sampleRate, channels: channels);
      default:
        return PcmToWavTranscoder(sampleRate: sampleRate, channels: channels);
    }
  }

  /// Creates transcoder that outputs raw PCM bytes (no WAV header)
  /// Used for streaming WebSocket APIs that expect raw audio
  static IAudioTranscoder createToRawPcm({
    required BleAudioCodec sourceCodec,
    required int sampleRate,
    int channels = 1,
  }) {
    switch (sourceCodec) {
      case BleAudioCodec.pcm8:
      case BleAudioCodec.pcm16:
        return RawPcmTranscoder(sampleRate: sampleRate, channels: channels);
      case BleAudioCodec.opus:
      case BleAudioCodec.opusFS320:
        return OpusToRawPcmTranscoder(sampleRate: sampleRate, channels: channels);
      default:
        return RawPcmTranscoder(sampleRate: sampleRate, channels: channels);
    }
  }
}
