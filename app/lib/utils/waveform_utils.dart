import 'dart:io';
import 'dart:math' as math;
import 'dart:typed_data';
import 'package:flutter/foundation.dart';

class WavInfo {
  final int sampleRate;
  final int channels;
  final int bitsPerSample;
  final int dataOffset;
  final int dataSize;

  WavInfo({
    required this.sampleRate,
    required this.channels,
    required this.bitsPerSample,
    required this.dataOffset,
    required this.dataSize,
  });
}

class WaveformUtils {
  static final Map<String, List<double>> _waveformCache = {};

  static Future<List<double>?> generateWaveform(String cacheKey, String? wavFilePath) async {
    debugPrint('Generating waveform for key $cacheKey');

    if (_waveformCache.containsKey(cacheKey)) {
      return _waveformCache[cacheKey];
    }

    if (wavFilePath == null) {
      return _generateFallbackWaveform();
    }

    try {
      final waveformData = await _generateWaveformFromWavFile(wavFilePath);
      _waveformCache[cacheKey] = waveformData;
      return waveformData;
    } catch (e) {
      debugPrint('Error generating waveform for key $cacheKey: $e');
      return _generateFallbackWaveform();
    }
  }

  static Future<List<double>> _generateWaveformFromWavFile(String wavFilePath) async {
    debugPrint('Generating waveform from WAV file: $wavFilePath');

    final file = File(wavFilePath);
    if (!file.existsSync()) {
      debugPrint('WAV file does not exist');
      return _generateFallbackWaveform();
    }

    final wavData = await file.readAsBytes();
    final wavInfo = _parseWavHeader(wavData);

    if (wavInfo == null) {
      debugPrint('Failed to parse WAV header');
      return _generateFallbackWaveform();
    }

    debugPrint(
        'WAV Info: ${wavInfo.sampleRate}Hz, ${wavInfo.channels} channels, ${wavInfo.bitsPerSample} bits, data size: ${wavInfo.dataSize}');

    final pcmData = wavData.sublist(wavInfo.dataOffset, wavInfo.dataOffset + wavInfo.dataSize);
    final samples = _extractSamples(pcmData, wavInfo);

    if (samples.isEmpty) {
      return _generateFallbackWaveform();
    }

    debugPrint('Extracted ${samples.length} samples from WAV file');
    return _generateWaveformFromSamples(samples);
  }

  static List<double> _extractSamples(Uint8List pcmData, WavInfo wavInfo) {
    List<double> samples = [];

    switch (wavInfo.bitsPerSample) {
      case 16:
        for (int i = 0; i < pcmData.length - 1; i += 2) {
          int sample = pcmData[i] | (pcmData[i + 1] << 8);
          if (sample > 32767) sample = sample - 65536;
          samples.add(sample / 32768.0);
        }
        break;
      case 8:
        for (int i = 0; i < pcmData.length; i++) {
          int sample = pcmData[i] - 128;
          samples.add(sample / 128.0);
        }
        break;
      case 24:
        for (int i = 0; i < pcmData.length - 2; i += 3) {
          int sample = pcmData[i] | (pcmData[i + 1] << 8) | (pcmData[i + 2] << 16);
          if (sample > 8388607) sample = sample - 16777216;
          samples.add(sample / 8388608.0);
        }
        break;
      case 32:
        for (int i = 0; i < pcmData.length - 3; i += 4) {
          int sample = pcmData[i] | (pcmData[i + 1] << 8) | (pcmData[i + 2] << 16) | (pcmData[i + 3] << 24);
          samples.add(sample / 2147483648.0);
        }
        break;
      default:
        debugPrint('Unsupported bits per sample: ${wavInfo.bitsPerSample}');
        return [];
    }

    // Handle multi-channel audio by taking only the first channel
    if (wavInfo.channels > 1) {
      List<double> monoSamples = [];
      for (int i = 0; i < samples.length; i += wavInfo.channels) {
        monoSamples.add(samples[i]);
      }
      samples = monoSamples;
    }

    return samples;
  }

  static WavInfo? _parseWavHeader(Uint8List wavData) {
    if (wavData.length < 44) {
      debugPrint('WAV file too small');
      return null;
    }

    final riffHeader = String.fromCharCodes(wavData.sublist(0, 4));
    if (riffHeader != 'RIFF') {
      debugPrint('Invalid RIFF header: $riffHeader');
      return null;
    }

    final waveFormat = String.fromCharCodes(wavData.sublist(8, 12));
    if (waveFormat != 'WAVE') {
      debugPrint('Invalid WAVE format: $waveFormat');
      return null;
    }

    int offset = 12;
    int fmtChunkSize = 0;
    int sampleRate = 0;
    int channels = 0;
    int bitsPerSample = 0;

    while (offset < wavData.length - 8) {
      final chunkId = String.fromCharCodes(wavData.sublist(offset, offset + 4));
      final chunkSize = ByteData.sublistView(wavData, offset + 4, offset + 8).getUint32(0, Endian.little);

      if (chunkId == 'fmt ') {
        fmtChunkSize = chunkSize;
        final audioFormat = ByteData.sublistView(wavData, offset + 8, offset + 10).getUint16(0, Endian.little);
        channels = ByteData.sublistView(wavData, offset + 10, offset + 12).getUint16(0, Endian.little);
        sampleRate = ByteData.sublistView(wavData, offset + 12, offset + 16).getUint32(0, Endian.little);
        bitsPerSample = ByteData.sublistView(wavData, offset + 22, offset + 24).getUint16(0, Endian.little);

        if (audioFormat != 1) {
          debugPrint('Unsupported audio format: $audioFormat (only PCM supported)');
          return null;
        }
        break;
      }

      offset += 8 + chunkSize;
      if (chunkSize % 2 == 1) offset++;
    }

    if (fmtChunkSize == 0) {
      debugPrint('fmt chunk not found');
      return null;
    }

    // Find data chunk
    offset = 12;
    while (offset < wavData.length - 8) {
      final chunkId = String.fromCharCodes(wavData.sublist(offset, offset + 4));
      final chunkSize = ByteData.sublistView(wavData, offset + 4, offset + 8).getUint32(0, Endian.little);

      if (chunkId == 'data') {
        return WavInfo(
          sampleRate: sampleRate,
          channels: channels,
          bitsPerSample: bitsPerSample,
          dataOffset: offset + 8,
          dataSize: chunkSize,
        );
      }

      offset += 8 + chunkSize;
      if (chunkSize % 2 == 1) offset++;
    }

    debugPrint('data chunk not found');
    return null;
  }

  static List<double> _generateWaveformFromSamples(List<double> samples) {
    if (samples.isEmpty) {
      return _generateFallbackWaveform();
    }

    const int targetBars = 100;
    final int samplesPerWindow = (samples.length / targetBars).ceil();

    List<double> waveformData = [];

    for (int i = 0; i < targetBars; i++) {
      final startIdx = i * samplesPerWindow;
      final endIdx = math.min(startIdx + samplesPerWindow, samples.length);

      if (startIdx >= samples.length) break;

      double rms = 0.0;
      int count = 0;
      for (int j = startIdx; j < endIdx; j++) {
        rms += samples[j] * samples[j];
        count++;
      }

      if (count > 0) {
        rms = math.sqrt(rms / count);
      }

      final level = math.pow(rms, 0.6).toDouble().clamp(0.02, 1.0);
      waveformData.add(level);
    }

    return waveformData;
  }

  static List<double> _generateFallbackWaveform() {
    return [];
  }

  static void clearCache() {
    _waveformCache.clear();
  }
}
