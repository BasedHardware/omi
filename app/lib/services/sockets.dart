import 'package:flutter/material.dart';
import 'package:friend_private/backend/schema/bt_device/bt_device.dart';
import 'package:friend_private/services/sockets/transcription_connection.dart';

abstract class ISocketService {
  void start();
  void stop();

  Future<TranscripSegmentSocketService?> memory(
      {required BleAudioCodec codec, required int sampleRate, bool force = false});
  Future<TranscripSegmentSocketService?> speechProfile(
      {required BleAudioCodec codec, required int sampleRate, bool force = false});
}

abstract interface class ISocketServiceSubsciption {}

class SocketServicePool extends ISocketService {
  TranscripSegmentSocketService? _socket;

  @override
  void start() {
    // TODO: implement start
  }

  @override
  void stop() async {
    await _socket?.stop();
  }

  // Warn: Should use a better solution to prevent race conditions
  bool mutex = false;
  Future<TranscripSegmentSocketService?> socket(
      {required BleAudioCodec codec, required int sampleRate, bool force = false}) async {
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

      _socket = MemoryTranscripSegmentSocketService.create(sampleRate, codec);
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
  Future<TranscripSegmentSocketService?> memory(
      {required BleAudioCodec codec, required int sampleRate, bool force = false}) async {
    debugPrint("socket memory > $codec $sampleRate $force");
    return await socket(codec: codec, sampleRate: sampleRate, force: force);
  }

  @override
  Future<TranscripSegmentSocketService?> speechProfile(
      {required BleAudioCodec codec, required int sampleRate, bool force = false}) async {
    debugPrint("socket speech profile > $codec $sampleRate $force");
    return await socket(codec: codec, sampleRate: sampleRate, force: force);
  }
}
