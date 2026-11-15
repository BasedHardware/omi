import 'dart:io';
import 'dart:typed_data';

import 'package:omi/utils/logger.dart';
import 'package:omi/utils/audio/pcm_wav_header.dart';

class WavMetadata {
  final int sampleRate;
  final int channels;
  final int bitsPerSample;
  final int dataSize;

  WavMetadata({required this.sampleRate, required this.channels, required this.bitsPerSample, required this.dataSize});
}

class WavCombiner {
  static Future<File> combineWavFiles(List<File> wavFiles, String outputPath) async {
    if (wavFiles.isEmpty) {
      throw Exception('No WAV files to combine');
    }

    // Skip parts that aren't valid WAV so one corrupt artifact doesn't fail the
    // whole export; combine the parts that do parse.
    final validFiles = <File>[];
    final metadataList = <WavMetadata>[];
    for (final file in wavFiles) {
      try {
        metadataList.add(await getMetadata(file));
        validFiles.add(file);
      } catch (e) {
        Logger.debug('Skipping unreadable WAV part ${file.path}: $e');
      }
    }

    if (validFiles.isEmpty) {
      throw Exception('No valid WAV files to combine');
    }

    if (!await validateCompatibility(metadataList)) {
      throw Exception('WAV files have incompatible formats');
    }
    final first = metadataList.first;
    final size = metadataList.fold<int>(0, (sum, metadata) => sum + metadata.dataSize);
    final header = pcmWavHeader(
      sampleRate: first.sampleRate,
      channels: first.channels,
      bitsPerSample: first.bitsPerSample,
      dataSize: size,
    );
    // Publish only after every stream and close succeeds. Failure never truncates a previous
    // complete export; staging is beside the destination so rename stays on one filesystem.
    final staging = await File(outputPath).parent.createTemp('.omi-wav-');
    try {
      final file = File('${staging.path}/complete.wav');
      if (validFiles.length == 1) {
        await validFiles.first.copy(file.path);
      } else {
        final sink = file.openWrite();
        try {
          sink.add(header);
          for (var i = 0; i < validFiles.length; i++) {
            await sink.addStream(validFiles[i].openRead(44, 44 + metadataList[i].dataSize));
          }
        } finally {
          await sink.close();
        }
      }
      return await file.rename(outputPath);
    } finally {
      await staging.delete(recursive: true);
    }
  }

  static Future<WavMetadata> getMetadata(File file) async {
    final handle = await file.open();
    late Uint8List bytes;
    late int fileSize;
    try {
      bytes = await handle.read(44);
      fileSize = await handle.length();
    } finally {
      await handle.close();
    }

    if (bytes.length < 44) {
      throw Exception('Invalid WAV file: too small');
    }

    final riffHeader = String.fromCharCodes(bytes.sublist(0, 4));
    if (riffHeader != 'RIFF') {
      throw Exception('Invalid WAV file: missing RIFF header');
    }

    final waveHeader = String.fromCharCodes(bytes.sublist(8, 12));
    if (waveHeader != 'WAVE') {
      throw Exception('Invalid WAV file: missing WAVE header');
    }

    final channels = _readUint16(bytes, 22);
    final sampleRate = _readUint32(bytes, 24);
    final bitsPerSample = _readUint16(bytes, 34);
    final dataSize = _readUint32(bytes, 40);

    if (dataSize > fileSize - 44) throw const FormatException('Truncated WAV payload');
    return WavMetadata(sampleRate: sampleRate, channels: channels, bitsPerSample: bitsPerSample, dataSize: dataSize);
  }

  static Future<bool> validateCompatibility(List<WavMetadata> metadataList) async {
    if (metadataList.isEmpty) return false;
    if (metadataList.length == 1) return true;

    final first = metadataList.first;

    for (final metadata in metadataList.skip(1)) {
      if (metadata.sampleRate != first.sampleRate) {
        Logger.debug('Incompatible sample rates: ${metadata.sampleRate} vs ${first.sampleRate}');
        return false;
      }
      if (metadata.channels != first.channels) {
        Logger.debug('Incompatible channels: ${metadata.channels} vs ${first.channels}');
        return false;
      }
      if (metadata.bitsPerSample != first.bitsPerSample) {
        Logger.debug('Incompatible bits per sample: ${metadata.bitsPerSample} vs ${first.bitsPerSample}');
        return false;
      }
    }

    return true;
  }

  static int _readUint16(Uint8List bytes, int offset) {
    return bytes[offset] | (bytes[offset + 1] << 8);
  }

  static int _readUint32(Uint8List bytes, int offset) {
    return bytes[offset] | (bytes[offset + 1] << 8) | (bytes[offset + 2] << 16) | (bytes[offset + 3] << 24);
  }
}
