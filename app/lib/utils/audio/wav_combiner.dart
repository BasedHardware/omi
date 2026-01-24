import 'dart:io';
import 'dart:typed_data';

import 'package:omi/utils/logger.dart';

class WavMetadata {
  final int sampleRate;
  final int channels;
  final int bitsPerSample;
  final int dataSize;

  WavMetadata({
    required this.sampleRate,
    required this.channels,
    required this.bitsPerSample,
    required this.dataSize,
  });
}

class WavCombiner {
  static Future<File> combineWavFiles(List<File> wavFiles, String outputPath) async {
    if (wavFiles.isEmpty) {
      throw Exception('No WAV files to combine');
    }

    if (wavFiles.length == 1) {
      final outputFile = File(outputPath);
      await wavFiles.first.copy(outputPath);
      return outputFile;
    }

    final metadataList = <WavMetadata>[];
    for (final file in wavFiles) {
      final metadata = await getMetadata(file);
      metadataList.add(metadata);
    }

    final isCompatible = await validateCompatibility(metadataList);
    if (!isCompatible) {
      throw Exception('WAV files have incompatible formats');
    }

    final firstMetadata = metadataList.first;
    final combinedDataSize = metadataList.fold<int>(0, (sum, metadata) => sum + metadata.dataSize);

    final outputFile = File(outputPath);
    final sink = outputFile.openWrite();

    try {
      final header = _createWavHeader(
        sampleRate: firstMetadata.sampleRate,
        channels: firstMetadata.channels,
        bitsPerSample: firstMetadata.bitsPerSample,
        dataSize: combinedDataSize,
      );
      sink.add(header);

      for (final file in wavFiles) {
        final stream = file.openRead(44);
        await sink.addStream(stream);
      }
    } finally {
      await sink.close();
    }

    return outputFile;
  }

  static Future<WavMetadata> getMetadata(File file) async {
    final bytes = await file.readAsBytes();

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

    return WavMetadata(
      sampleRate: sampleRate,
      channels: channels,
      bitsPerSample: bitsPerSample,
      dataSize: dataSize,
    );
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

  static Uint8List _createWavHeader({
    required int sampleRate,
    required int channels,
    required int bitsPerSample,
    required int dataSize,
  }) {
    final byteRate = sampleRate * channels * (bitsPerSample ~/ 8);
    final blockAlign = channels * (bitsPerSample ~/ 8);
    final fileSize = 36 + dataSize;

    final header = ByteData(44);

    header.setUint8(0, 'R'.codeUnitAt(0));
    header.setUint8(1, 'I'.codeUnitAt(0));
    header.setUint8(2, 'F'.codeUnitAt(0));
    header.setUint8(3, 'F'.codeUnitAt(0));

    header.setUint32(4, fileSize, Endian.little);

    header.setUint8(8, 'W'.codeUnitAt(0));
    header.setUint8(9, 'A'.codeUnitAt(0));
    header.setUint8(10, 'V'.codeUnitAt(0));
    header.setUint8(11, 'E'.codeUnitAt(0));

    header.setUint8(12, 'f'.codeUnitAt(0));
    header.setUint8(13, 'm'.codeUnitAt(0));
    header.setUint8(14, 't'.codeUnitAt(0));
    header.setUint8(15, ' '.codeUnitAt(0));

    header.setUint32(16, 16, Endian.little);

    header.setUint16(20, 1, Endian.little);

    header.setUint16(22, channels, Endian.little);

    header.setUint32(24, sampleRate, Endian.little);

    header.setUint32(28, byteRate, Endian.little);

    header.setUint16(32, blockAlign, Endian.little);

    header.setUint16(34, bitsPerSample, Endian.little);

    header.setUint8(36, 'd'.codeUnitAt(0));
    header.setUint8(37, 'a'.codeUnitAt(0));
    header.setUint8(38, 't'.codeUnitAt(0));
    header.setUint8(39, 'a'.codeUnitAt(0));

    header.setUint32(40, dataSize, Endian.little);

    return header.buffer.asUint8List();
  }

  static int _readUint16(Uint8List bytes, int offset) {
    return bytes[offset] | (bytes[offset + 1] << 8);
  }

  static int _readUint32(Uint8List bytes, int offset) {
    return bytes[offset] | (bytes[offset + 1] << 8) | (bytes[offset + 2] << 16) | (bytes[offset + 3] << 24);
  }
}
