import 'package:flutter/material.dart';
import 'package:friend_private/backend/schema/bt_device.dart';
import 'package:friend_private/utils/pure_socket.dart';

abstract class ISocketService {
  void start();
  void stop();

  Future<TranscripSegmentSocketService?> memory(
      {required BleAudioCodec codec, required int sampleRate, bool force = false});
  TranscripSegmentSocketService speechProfile();
}

abstract interface class ISocketServiceSubsciption {}

class SocketServicePool extends ISocketService {
  TranscripSegmentSocketService? _memory;
  TranscripSegmentSocketService? _speechProfile;

  @override
  void start() {
    // TODO: implement start
  }

  @override
  void stop() async {
    await _memory?.stop();
    await _speechProfile?.stop();
  }

  // Warn: Should use a better solution to prevent race conditions
  bool memoryMutex = false;
  @override
  Future<TranscripSegmentSocketService?> memory(
      {required BleAudioCodec codec, required int sampleRate, bool force = false}) async {
    while (memoryMutex) {
      await Future.delayed(const Duration(milliseconds: 50));
    }
    memoryMutex = true;

    debugPrint("socket memory > $codec $sampleRate $force");

    try {
      if (!force &&
          _memory?.codec == codec &&
          _memory?.sampleRate == sampleRate &&
          _memory?.state == SocketServiceState.connected) {
        return _memory;
      }

      // new socket
      await _memory?.stop();

      _memory = MemoryTranscripSegmentSocketService.create(sampleRate, codec);
      await _memory?.start();
      if (_memory?.state != SocketServiceState.connected) {
        return null;
      }

      return _memory;
    } finally {
      memoryMutex = false;
    }

    return null;
  }

  @override
  TranscripSegmentSocketService speechProfile() {
    // TODO: implement speechProfile
    throw UnimplementedError();
  }
}
