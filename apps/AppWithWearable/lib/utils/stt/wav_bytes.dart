import 'dart:async';
import 'dart:io';
import 'dart:typed_data';
import 'package:path_provider/path_provider.dart';
import 'package:flutter/material.dart';
import '/flutter_flow/flutter_flow_util.dart';

const int sampleRate = 8000;
const int channelCount = 1;
const int sampleWidth = 2;

class WavBytesUtil {
  // List to hold audio data in bytes
  final List<int> _audioBytes = [];

  get audioBytes => _audioBytes;

  // Method to add audio bytes (now accepts List<int> instead of Uint8List)
  void addAudioBytes(List<int> bytes) {
    _audioBytes.addAll(bytes);
  }

  // Method to clear audio bytes
  void clearAudioBytes() {
    _audioBytes.clear();
    debugPrint('Cleared audio bytes');
  }

  void cleanAudioBytes() {
    // Assuming empty audio bytes mean zeros
    _audioBytes.removeWhere((byte) => byte == 0);
  }

  // Method to clean out the silent parts based on a given threshold
  // void removeSilentSegments({int silenceThreshold = 10}) {
  //   // Identify segments with sound (above the silenceThreshold)
  //   List<int> cleanedBytes = [];
  //   for (int byte in _audioBytes) {
  //     if (byte.abs() > silenceThreshold) {
  //       cleanedBytes.add(byte);
  //     }
  //   }
  //   _audioBytes
  //     ..clear()
  //     ..addAll(cleanedBytes);
  //   debugPrint('Cleaned silent segments');
  // }

  // Method to create a WAV file from the stored audio bytes
  static Future<File> createWavFile(List<int> audioBytes) async {
    // TODO: remove empty sounds without words
    // removeSilentSegments();
    final timestamp = DateFormat('yyyyMMdd_HHmmss').format(DateTime.now());
    final wavHeader = buildWavHeader(audioBytes.length * 2);
    final wavBytes = Uint8List.fromList(wavHeader + convertToLittleEndianBytes(audioBytes));
    final filename = 'recording-$timestamp.wav';

    final directory = await getApplicationDocumentsDirectory();
    final file = File('${directory.path}/$filename');
    await file.writeAsBytes(wavBytes);
    debugPrint('WAV file created: ${file.path}');
    return file;
  }

  // Utility to convert audio data to little-endian format
  static Uint8List convertToLittleEndianBytes(List<int> audioData) {
    final byteData = ByteData(2 * audioData.length);
    for (int i = 0; i < audioData.length; i++) {
      byteData.setUint16(i * 2, audioData[i], Endian.little);
    }
    return byteData.buffer.asUint8List();
  }

  static Uint8List buildWavHeader(int dataLength) {
    final byteData = ByteData(44);
    final size = dataLength + 36;

    // RIFF chunk
    byteData.setUint8(0, 0x52); // 'R'
    byteData.setUint8(1, 0x49); // 'I'
    byteData.setUint8(2, 0x46); // 'F'
    byteData.setUint8(3, 0x46); // 'F'
    byteData.setUint32(4, size, Endian.little);
    byteData.setUint8(8, 0x57); // 'W'
    byteData.setUint8(9, 0x41); // 'A'
    byteData.setUint8(10, 0x56); // 'V'
    byteData.setUint8(11, 0x45); // 'E'

    // fmt chunk
    byteData.setUint8(12, 0x66); // 'f'
    byteData.setUint8(13, 0x6D); // 'm'
    byteData.setUint8(14, 0x74); // 't'
    byteData.setUint8(15, 0x20); // ' '
    byteData.setUint32(16, 16, Endian.little);
    byteData.setUint16(20, 1, Endian.little); // Audio format (1 = PCM)
    byteData.setUint16(22, channelCount, Endian.little);
    byteData.setUint32(24, sampleRate, Endian.little);
    byteData.setUint32(28, sampleRate * channelCount * sampleWidth, Endian.little);
    byteData.setUint16(32, channelCount * sampleWidth, Endian.little);
    byteData.setUint16(34, sampleWidth * 8, Endian.little);

    // data chunk
    byteData.setUint8(36, 0x64); // 'd'
    byteData.setUint8(37, 0x61); // 'a'
    byteData.setUint8(38, 0x74); // 't'
    byteData.setUint8(39, 0x61); // 'a'
    byteData.setUint32(40, dataLength, Endian.little);

    return byteData.buffer.asUint8List();
  }
}
