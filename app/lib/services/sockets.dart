import 'dart:async';

import 'package:flutter/material.dart';
import 'package:omi/backend/schema/bt_device/bt_device.dart';
import 'package:omi/utils/mutex.dart';
import 'package:omi/services/sockets/transcription_connection.dart';

abstract class ISocketService {
  void start();

  void stop();

  Future<TranscriptSegmentSocketService?> conversation(
      {required BleAudioCodec codec, required int sampleRate, required String language, bool force = false});

  Future<TranscriptSegmentSocketService?> speechProfile(
      {required BleAudioCodec codec, required int sampleRate, required String language, bool force = false});
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
  final Mutex _mutex = Mutex();

  Future<TranscriptSegmentSocketService?> socket({
    required BleAudioCodec codec,
    required int sampleRate,
    required String language,
    bool force = false,
  }) async {
    await _mutex.acquire();
    try {
      if (!force &&
          _socket?.codec == codec &&
          _socket?.sampleRate == sampleRate &&
          _socket?.state == SocketServiceState.connected) {
        return _socket;
      }

      debugPrint("_connect force ${force} state ${_socket?.state}");

      // new socket
      await _socket?.stop();

      _socket = ConversationTranscriptSegmentSocketService.create(sampleRate, codec, language);
      await _socket?.start();
      if (_socket?.state != SocketServiceState.connected) {
        return null;
      }

      return _socket;
    } finally {
      _mutex.release();
    }

    return null;
  }

  @override
  Future<TranscriptSegmentSocketService?> conversation(
      {required BleAudioCodec codec, required int sampleRate, required String language, bool force = false}) async {
    debugPrint("socket conversation > $codec $sampleRate $force");
    return await socket(codec: codec, sampleRate: sampleRate, language: language, force: force);
  }

  @override
  Future<TranscriptSegmentSocketService?> speechProfile(
      {required BleAudioCodec codec, required int sampleRate, required String language, bool force = false}) async {
    debugPrint("socket speech profile > $codec $sampleRate $force");
    return await socket(codec: codec, sampleRate: sampleRate, language: language, force: force);
  }
}
