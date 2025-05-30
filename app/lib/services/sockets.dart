import 'package:flutter/material.dart';
import 'package:omi/backend/schema/bt_device/bt_device.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/services/sockets/transcription_connection.dart';

abstract class ISocketService {
  void start();

  void stop();

  Future<TranscriptSegmentSocketService?> conversation({
    required BleAudioCodec codec,
    required int sampleRate,
    required String language,
    bool force = false,
    String? sttServerType,
    String? wyomingServerIp,
  });

  Future<TranscriptSegmentSocketService?> speechProfile(
      {required BleAudioCodec codec,
      required int sampleRate,
      required String language,
      bool force = false});
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
    String? sttServerType,
    String? wyomingServerIp,
  }) async {
    while (mutex) {
      await Future.delayed(const Duration(milliseconds: 50));
    }
    mutex = true;

    try {
      // Check if we need to reconnect due to STT settings or other changes
      bool needsReconnection = force ||
          _socket?.codec != codec ||
          _socket?.sampleRate != sampleRate ||
          _socket?.language != language ||
          _socket?.state != SocketServiceState.connected;

      if (!needsReconnection) {
        debugPrint("🔄 Reusing existing socket connection");
        return _socket;
      }

      debugPrint(
          "🔗 Creating new socket - force: $force, state: ${_socket?.state}");
      debugPrint(
          "📡 STT Settings - Type: $sttServerType, Wyoming IP: $wyomingServerIp");

      // Stop existing socket
      await _socket?.stop();

      // Create new socket with STT settings
      _socket = ConversationTranscriptSegmentSocketService.create(
        sampleRate,
        codec,
        language,
        sttServerType: sttServerType, // Pass STT settings
        wyomingServerIp: wyomingServerIp, // Pass Wyoming IP
      );

      await _socket?.start();

      if (_socket?.state != SocketServiceState.connected) {
        debugPrint("❌ Failed to connect to transcription service");
        return null;
      }

      debugPrint("✅ Successfully connected to transcription service");
      return _socket;
    } finally {
      mutex = false;
    }
  }

  @override
  Future<TranscriptSegmentSocketService?> conversation({
    required BleAudioCodec codec,
    required int sampleRate,
    required String language,
    bool force = false,
    String? sttServerType,
    String? wyomingServerIp,
  }) async {
    debugPrint("socket conversation > $codec $sampleRate $force");

    // If STT settings not provided, get them from SharedPreferences
    if (sttServerType == null || wyomingServerIp == null) {
      final prefs = SharedPreferencesUtil();
      sttServerType ??= prefs.getString('stt_server_type') ?? 'traditional';
      wyomingServerIp ??=
          prefs.getString('wyoming_server_ip') ?? 'localhost:10300';
    }

    return await socket(
      codec: codec,
      sampleRate: sampleRate,
      language: language,
      force: force,
      sttServerType: sttServerType,
      wyomingServerIp: wyomingServerIp,
    );
  }

  @override
  Future<TranscriptSegmentSocketService?> speechProfile(
      {required BleAudioCodec codec,
      required int sampleRate,
      required String language,
      bool force = false}) async {
    debugPrint("socket speech profile > $codec $sampleRate $force");

    // Speech profile also uses STT settings
    final prefs = SharedPreferencesUtil();
    final sttServerType = prefs.getString('stt_server_type') ?? 'traditional';
    final wyomingServerIp =
        prefs.getString('wyoming_server_ip') ?? 'localhost:10300';

    return await socket(
      codec: codec,
      sampleRate: sampleRate,
      language: language,
      force: force,
      sttServerType: sttServerType,
      wyomingServerIp: wyomingServerIp,
    );
  }
}
