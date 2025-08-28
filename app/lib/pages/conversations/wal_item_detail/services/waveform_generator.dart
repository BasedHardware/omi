import 'dart:math';
import 'dart:math' as math;
import 'dart:typed_data';
import 'dart:io';
import 'package:flutter/material.dart';
import 'package:omi/services/wals.dart';
import 'package:omi/backend/schema/bt_device/bt_device.dart';
import 'package:opus_dart/opus_dart.dart';

class WaveformGenerator {
  Future<List<double>> generateFromWal(Wal wal) async {
    try {
      // Get audio file path
      String? audioFilePath = await _getAudioFilePath(wal);
      if (audioFilePath == null) {
        return _generateFallbackWaveform();
      }

      // Read and process audio data
      final file = File(audioFilePath);
      if (!file.existsSync()) {
        return _generateFallbackWaveform();
      }

      final audioData = await file.readAsBytes();
      List<double> samples = [];

      if (wal.codec.isOpusSupported()) {
        samples = await _extractSamplesFromOpus(audioData, wal);
      } else {
        samples = await _extractSamplesFromPcm(audioData, wal);
      }

      // Generate waveform from samples
      return _generateWaveformFromSamples(samples);
    } catch (e) {
      debugPrint('Error extracting waveform: $e');
      return _generateFallbackWaveform();
    }
  }

  Future<String?> _getAudioFilePath(Wal wal) async {
    // If WAL already has a file path, use it
    if (wal.filePath != null && wal.filePath!.isNotEmpty) {
      final file = File(wal.filePath!);
      if (file.existsSync()) {
        return wal.filePath!;
      }
    }

    // If WAL has data in memory, create a temporary file
    if (wal.data.isNotEmpty) {
      return await _createTempFileFromMemoryData(wal);
    }

    return null;
  }

  Future<String?> _createTempFileFromMemoryData(Wal wal) async {
    try {
      final tempDir = Directory.systemTemp;
      final tempFilePath = '${tempDir.path}/temp_waveform_${wal.id}_${DateTime.now().millisecondsSinceEpoch}.bin';

      List<int> data = [];
      for (int i = 0; i < wal.data.length; i++) {
        var frame = wal.data[i].sublist(3); // Remove the 3-byte header

        // Format: <length>|<data> ; bytes: 4 | n
        final byteFrame = ByteData(frame.length);
        for (int j = 0; j < frame.length; j++) {
          byteFrame.setUint8(j, frame[j]);
        }
        data.addAll(Uint32List.fromList([frame.length]).buffer.asUint8List());
        data.addAll(byteFrame.buffer.asUint8List());
      }

      final file = File(tempFilePath);
      await file.writeAsBytes(data);
      return tempFilePath;
    } catch (e) {
      debugPrint('Error creating temp file from memory data: $e');
      return null;
    }
  }

  Future<List<double>> _extractSamplesFromOpus(Uint8List opusData, Wal wal) async {
    try {
      // Parse the custom format: <length>|<data> for each frame
      List<Uint8List> opusFrames = [];
      int offset = 0;

      while (offset < opusData.length - 4) {
        // Read frame length (4 bytes)
        final lengthBytes = opusData.sublist(offset, offset + 4);
        final length = ByteData.sublistView(Uint8List.fromList(lengthBytes)).getUint32(0, Endian.little);
        offset += 4;

        if (offset + length > opusData.length) break;

        // Read frame data
        final frameData = opusData.sublist(offset, offset + length);
        opusFrames.add(Uint8List.fromList(frameData));
        offset += length;
      }

      if (opusFrames.isEmpty) {
        return [];
      }

      // Initialize opus decoder
      final decoder = SimpleOpusDecoder(
        sampleRate: wal.sampleRate,
        channels: wal.channel,
      );

      // Decode frames and extract samples
      List<double> allSamples = [];
      for (final opusFrame in opusFrames) {
        try {
          final pcmFrame = decoder.decode(input: opusFrame);
          if (pcmFrame != null) {
            // Convert Int16List to double samples (normalize to -1.0 to 1.0)
            for (int i = 0; i < pcmFrame.length; i++) {
              allSamples.add(pcmFrame[i] / 32768.0);
            }
          }
        } catch (e) {
          debugPrint('Error decoding opus frame: $e');
          // Continue with other frames
        }
      }

      return allSamples;
    } catch (e) {
      debugPrint('Error extracting samples from opus: $e');
      return [];
    }
  }

  Future<List<double>> _extractSamplesFromPcm(Uint8List pcmData, Wal wal) async {
    try {
      // Parse the custom format: <length>|<data> for each frame
      List<Uint8List> pcmFrames = [];
      int offset = 0;

      while (offset < pcmData.length - 4) {
        // Read frame length (4 bytes)
        final lengthBytes = pcmData.sublist(offset, offset + 4);
        final length = ByteData.sublistView(Uint8List.fromList(lengthBytes)).getUint32(0, Endian.little);
        offset += 4;

        if (offset + length > pcmData.length) break;

        // Read frame data
        final frameData = pcmData.sublist(offset, offset + length);
        pcmFrames.add(Uint8List.fromList(frameData));
        offset += length;
      }

      if (pcmFrames.isEmpty) {
        return [];
      }

      // Combine all PCM frames
      final totalLength = pcmFrames.fold<int>(0, (sum, frame) => sum + frame.length);
      final combinedPcm = Uint8List(totalLength);
      int writeOffset = 0;
      for (final frame in pcmFrames) {
        combinedPcm.setRange(writeOffset, writeOffset + frame.length, frame);
        writeOffset += frame.length;
      }

      // Convert PCM bytes to samples
      List<double> samples = [];
      if (wal.codec == BleAudioCodec.pcm16) {
        // 16-bit PCM
        for (int i = 0; i < combinedPcm.length - 1; i += 2) {
          final sample = ByteData.sublistView(combinedPcm, i, i + 2).getInt16(0, Endian.little);
          samples.add(sample / 32768.0); // Normalize to -1.0 to 1.0
        }
      } else {
        // 8-bit PCM
        for (int i = 0; i < combinedPcm.length; i++) {
          final sample = combinedPcm[i] - 128; // Convert unsigned to signed
          samples.add(sample / 128.0); // Normalize to -1.0 to 1.0
        }
      }

      return samples;
    } catch (e) {
      debugPrint('Error extracting samples from PCM: $e');
      return [];
    }
  }

  List<double> _generateWaveformFromSamples(List<double> samples) {
    if (samples.isEmpty) {
      return _generateFallbackWaveform();
    }

    const int targetBars = 100; // Number of bars in waveform
    final int samplesPerBar = (samples.length / targetBars).ceil();

    List<double> waveformData = [];

    for (int i = 0; i < targetBars; i++) {
      final startIdx = i * samplesPerBar;
      final endIdx = math.min(startIdx + samplesPerBar, samples.length);

      if (startIdx >= samples.length) {
        waveformData.add(0.0);
        continue;
      }

      // Calculate RMS (Root Mean Square) for this segment
      double sum = 0.0;
      int count = 0;
      for (int j = startIdx; j < endIdx; j++) {
        sum += samples[j] * samples[j];
        count++;
      }

      final rms = count > 0 ? math.sqrt(sum / count) : 0.0;
      waveformData.add(rms);
    }

    // Normalize waveform data to 0.0-1.0 range
    if (waveformData.isNotEmpty) {
      final maxValue = waveformData.reduce(math.max);
      if (maxValue > 0) {
        waveformData = waveformData.map((value) => value / maxValue).toList();
      }
    }

    return waveformData;
  }

  List<double> _generateFallbackWaveform() {
    // Generate a fallback waveform using random data (similar to original)
    final random = Random(42); // Fixed seed for consistency
    return List.generate(100, (index) => random.nextDouble() * 0.7 + 0.1);
  }
}
