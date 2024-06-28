import 'dart:async';
import 'dart:io';
import 'dart:math';
import 'dart:typed_data';

import 'package:flutter/material.dart';
import 'package:friend_private/utils/ble/communication.dart';
import 'package:intl/intl.dart';
import 'package:opus_dart/opus_dart.dart';
import 'package:path_provider/path_provider.dart';
import 'package:tuple/tuple.dart';

class WavBytesUtil {
  BleAudioCodec codec;
  List<List<int>> frames = [];
  final SimpleOpusDecoder opusDecoder = SimpleOpusDecoder(sampleRate: 16000, channels: 1);

  WavBytesUtil({this.codec = BleAudioCodec.pcm8});

  // needed variables for `storeFramePacket`
  int lastPacketIndex = -1;
  int lastFrameId = -1;
  List<int> pending = [];
  int lost = 0;

  void storeFramePacket(value) {
    int index = value[0] + (value[1] << 8);
    int internal = value[2];
    List<int> content = value.sublist(3);

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

  void trimFrames({required int untilSecond}) => frames.removeRange(0, min(untilSecond * 100, frames.length));

  void insertAudioBytes(List<List<int>> bytes) => frames.insertAll(0, bytes);

  void clearAudioBytes() => frames.clear();

  bool hasFrames() => frames.isNotEmpty;

  Future<Tuple2<File, List<List<int>>>> createWavFile({String? filename}) async {
    File file = await createWavByCodec(filename: filename);
    var framesCopy = List<List<int>>.from(frames);
    trimFrames(untilSecond: frames.length ~/ 100);
    return Tuple2(file, framesCopy);
  }

  /// OPUS

  Future<File> createWavByCodec({String? filename}) async {
    Uint8List wavBytes;
    if (codec == BleAudioCodec.opus) {
      List<int> decodedSamples = [];
      for (var frame in frames) {
        decodedSamples.addAll(opusDecoder.decode(input: Uint8List.fromList(frame)));
      }
      wavBytes = getUInt8ListBytes(decodedSamples);
    } else {
      Int16List samples = getPcm8Samples(frames);
      wavBytes = getUInt8ListBytes(samples);
    }
    return createWav(wavBytes, filename: filename);
  }

  Future<File> createWav(Uint8List wavBytes, {String? filename}) async {
    final directory = await getApplicationDocumentsDirectory();
    if (filename == null) {
      final timestamp = DateFormat('yyyyMMdd_HHmmss').format(DateTime.now());
      filename = 'recording-$timestamp.wav';
    }
    final file = File('${directory.path}/$filename');
    await file.writeAsBytes(wavBytes);
    debugPrint('WAV file created: ${file.path}');
    return file;
  }

  Uint8List getUInt8ListBytes(List<int> audioBytes) {
    Uint8List wavHeader;
    if (codec == BleAudioCodec.opus) {
      // TODO: how to determine this values? sample rate can't be higher?
      // TODO: where is bit rate parameter in here?
      // TODO: what is sample width for?
      wavHeader = getWavHeader(audioBytes.length * 2, 16000, sampleWidth: 2);
    } else {
      wavHeader = getWavHeader(audioBytes.length * 2, 8000, sampleWidth: 2);
    }
    return Uint8List.fromList(wavHeader + WavBytesUtil.convertToLittleEndianBytes(audioBytes));
  }

  // Utility to convert audio data to little-endian format
  static Uint8List convertToLittleEndianBytes(List<int> audioData) {
    final byteData = ByteData(2 * audioData.length);
    for (int i = 0; i < audioData.length; i++) {
      byteData.setUint16(i * 2, audioData[i], Endian.little);
    }
    return byteData.buffer.asUint8List();
  }

  static Uint8List getWavHeader(int dataLength, int sampleRate, {int sampleWidth = 2}) {
    int channelCount = 1;

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

  Int16List getPcm8Samples(List<List<int>> frames) {
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
}
