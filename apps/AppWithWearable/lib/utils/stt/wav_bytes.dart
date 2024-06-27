import 'dart:async';
import 'dart:io';
import 'dart:math';
import 'dart:typed_data';

import 'package:flutter/material.dart';
import 'package:intl/intl.dart';
import 'package:opus_dart/opus_dart.dart';
import 'package:path_provider/path_provider.dart';
import 'package:tuple/tuple.dart';

const int sampleRate = 8000;
const int channelCount = 1;
const int sampleWidth = 2;

class WavBytesUtil {
  // List to hold audio data in bytes
  final List<int> _audioBytes = [];

  List<int> get audioBytes => _audioBytes;

  // Method to add audio bytes (now accepts List<int> instead of Uint8List)
  void addAudioBytes(List<int> bytes) {
    _audioBytes.addAll(bytes);
  }

  void insertAudioBytes(List<int> bytes) {
    _audioBytes.insertAll(0, bytes);
  }

  // Method to clear audio bytes
  void clearAudioBytes() {
    _audioBytes.clear();
    debugPrint('Cleared audio bytes');
  }

  void clearAudioBytesSegment({required int remainingSeconds}) {
    _audioBytes.removeRange(0, (_audioBytes.length) - (remainingSeconds * 8000));
  }

  // Method to create a WAV file from the stored audio bytes
  static Future<File> createWavFile(List<int> audioBytes, {String? filename}) async {
    debugPrint('Creating WAV file...');
    // TODO: include VAD somewhere onnx pico-voice

    if (filename == null) {
      final timestamp = DateFormat('yyyyMMdd_HHmmss').format(DateTime.now());
      filename = 'recording-$timestamp.wav';
    }

    final wavBytes = getUInt8ListBytes(audioBytes);

    final directory = await getApplicationDocumentsDirectory();
    final file = File('${directory.path}/$filename');
    await file.writeAsBytes(wavBytes);
    debugPrint('WAV file created: ${file.path}');
    return file;
  }

  static Uint8List getUInt8ListBytes(List<int> audioBytes) {
    final wavHeader = buildWavHeader(audioBytes.length * 2);
    return Uint8List.fromList(wavHeader + convertToLittleEndianBytes(audioBytes));
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

class WavBytesUtil2 {
  int lastPacketIndex = -1;
  int lastFrameId = -1;
  List<int> pending = [];
  List<List<int>> frames = [];
  int lost = 0;
  final SimpleOpusDecoder opusDecoder = SimpleOpusDecoder(sampleRate: 48000, channels: 1);

  // TODO: initialize with opus or PCM
  // TODO: create wav file differently if using opus
  // TODO: try pcm again but 16k sample rate

  void storeBytes(value) {
    int index = value[0] + (value[1] << 8);
    int internal = value[2];
    List<int> content = value.sublist(3);
    // debugPrint('Received: $index ($internal) - ${content.length} bytes');

    // Start of a new frame
    if (lastPacketIndex == -1 && internal == 0) {
      lastPacketIndex = index;
      lastFrameId = internal;
      pending = content;
      return;
    }

    if (lastPacketIndex == -1) return;

    // Lost frame - reset state
    if (index != lastPacketIndex + 1 || (internal != 0 && internal != lastFrameId + 1)) {
      debugPrint('Lost frame');
      lastPacketIndex = -1;
      pending = [];
      lost += 1;
      return;
    }

    // Start of a new frame
    if (internal == 0) {
      frames.add(pending); // Save frame
      pending = content; // Start new frame
      lastFrameId = internal; // Update internal frame id
      lastPacketIndex = index; // Update packet id
      // debugPrint('Frames received: ${frames.length} && Lost: $lost');
      return;
    }

    // Continue frame
    pending.addAll(content);
    lastFrameId = internal; // Update internal frame id
    lastPacketIndex = index; // Update packet id
  }

  Future<Tuple2<File, List<List<int>>>> createWavFile({String? filename}) async {
    Int16List samples;
    var format = 'pcm';
    if (format == 'pcm') {
      samples = getSamples();
    } else if (format == 'opus') {
      samples = await decodeOpusFrames();
      debugPrint('Decoded samples: ${samples.length}');
    } else {
      throw Exception('Invalid format');
    }
    var framesCopy = List<List<int>>.from(frames);
    trimFrames(untilSecond: frames.length ~/ 100); // basically clearing them all
    File file = await WavBytesUtil.createWavFile(samples, filename: filename);
    return Tuple2(file, framesCopy);
  }

  Int16List getSamples() {
    int totalLength = frames.fold(0, (sum, frame) => sum + frame.length);

    // Create an Int16List to store the samples
    Int16List samples = Int16List(totalLength ~/ 2);
    int sampleIndex = 0;

    // Iterate through each frame and each byte in the frame
    for (int i = 0; i < frames.length; i++) {
      for (int j = 0; j < frames[i].length; j += 2) {
        int byte1 = frames[i][j];
        int byte2 = frames[i][j + 1];
        int sample = (byte2 << 8) | byte1;
        samples[sampleIndex++] = sample;
      }
    }
    return samples;
  }

  trimFrames({required int untilSecond}) {
    frames.removeRange(0, min(untilSecond * 100, frames.length));
  }

  void insertAudioBytes(List<List<int>> bytes) {
    frames.insertAll(0, bytes);
    debugPrint('insertAudioBytes: ${frames.length} frames');
  }

  void clearAudioBytes() {
    frames.clear();
  }

  /// OPUS

  Future<Int16List> decodeOpusFrames() async {
    List<int> decodedSamples = [];
    for (var frame in frames) {
      var decoded = opusDecoder.decode(input: Uint8List.fromList(frame));
      decodedSamples.addAll(decoded);
    }
    return Int16List.fromList(decodedSamples);
  }
}
