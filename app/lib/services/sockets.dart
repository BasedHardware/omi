import 'package:flutter/material.dart';
import 'package:friend_private/backend/schema/bt_device/bt_device.dart';
import 'package:friend_private/services/sockets/transcription_connection.dart';

const defaultLanguage = "en";

abstract class ISocketService {
  void start();

  void stop();

  Future<TranscriptSegmentSocketService?> memory(
      {required BleAudioCodec codec, required int sampleRate, String language = defaultLanguage, bool force = false});

  Future<TranscriptSegmentSocketService?> speechProfile(
      {required BleAudioCodec codec, required int sampleRate, String language = defaultLanguage, bool force = false});
}

abstract interface class ISocketServiceSubsciption {}

class SocketServicePool extends ISocketService {
  TranscriptSegmentSocketService? _socket;

  @override
  void start() {}

  @override
  void stop() async {
    await _socket?.stop();
  }

  // Warn: Should use a better solution to prevent race conditions
  bool mutex = false;

  Future<TranscriptSegmentSocketService?> socket({
    required BleAudioCodec codec,
    required int sampleRate,
    required String language,
    bool force = false,
  }) async {
    while (mutex) {
      await Future.delayed(const Duration(milliseconds: 50));
    }
    mutex = true;

    try {
      if (!force &&
          _socket?.codec == codec &&
          _socket?.sampleRate == sampleRate &&
          _socket?.state == SocketServiceState.connected) {
        return _socket;
      }

      // new socket
      await _socket?.stop();

      _socket = MemoryTranscriptSegmentSocketService.create(sampleRate, codec, language);
      await _socket?.start();
      if (_socket?.state != SocketServiceState.connected) {
        return null;
      }

      return _socket;
    } finally {
      mutex = false;
    }

    return null;
  }

  @override
  Future<TranscriptSegmentSocketService?> memory(
      {required BleAudioCodec codec,
      required int sampleRate,
      String language = defaultLanguage,
      bool force = false}) async {
    debugPrint("socket memory > $codec $sampleRate $force");
    return await socket(codec: codec, sampleRate: sampleRate, language: language, force: force);
  }

  @override
  Future<TranscriptSegmentSocketService?> speechProfile(
      {required BleAudioCodec codec,
      required int sampleRate,
      String language = defaultLanguage,
      bool force = false}) async {
    debugPrint("socket speech profile > $codec $sampleRate $force");
    return await socket(codec: codec, sampleRate: sampleRate, language: language, force: force);
  }
}
