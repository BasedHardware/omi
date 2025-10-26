import 'dart:async';

import 'package:flutter/material.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/bt_device/bt_device.dart';
import 'package:omi/utils/mutex.dart';
import 'package:omi/services/sockets/transcription_connection.dart';
import 'package:omi/services/sockets/webhook_only_socket_service.dart';

abstract class ISocketService {
  void start();

  void stop();

  Future<ITranscriptSegmentSocketService?> conversation(
      {required BleAudioCodec codec, required int sampleRate, required String language, bool force = false});

  Future<ITranscriptSegmentSocketService?> speechProfile(
      {required BleAudioCodec codec, required int sampleRate, required String language, bool force = false});
}

abstract interface class ISocketServiceSubsciption {}

class SocketServicePool extends ISocketService {
  dynamic _socket;

  @override
  void start() {}

  @override
  void stop() async {
    await _socket?.stop();
  }

  // Warn: Should use a better solution to prevent race conditions
  final Mutex _mutex = Mutex();

  Future<ITranscriptSegmentSocketService?> socket({
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

      // Check if webhook-only mode is enabled
      final prefs = SharedPreferencesUtil();
      debugPrint('[SOCKET] Webhook-only mode enabled: ${prefs.webhookOnlyModeEnabled}');
      debugPrint('[SOCKET] Webhook URL: ${prefs.webhookAudioBytes}');
      debugPrint('[SOCKET] User UID: ${prefs.uid}');

      if (prefs.webhookOnlyModeEnabled) {
        if (prefs.webhookAudioBytes.isEmpty) {
          debugPrint('[SOCKET] ❌ Webhook-only mode enabled but no URL configured. Cannot connect.');
          return null;
        }
        debugPrint('[SOCKET] ✅ Using webhook-only mode (bypassing Omi servers)');
        debugPrint('[SOCKET] Creating WebhookOnlySocketService with codec=$codec sampleRate=$sampleRate');
        _socket = WebhookOnlySocketService.create(sampleRate, codec, language);
        await _socket?.start();
        debugPrint('[SOCKET] ✅ WebhookOnlySocketService started');
        return _socket;
      }

      // Standard Omi server mode
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
  Future<ITranscriptSegmentSocketService?> conversation(
      {required BleAudioCodec codec, required int sampleRate, required String language, bool force = false}) async {
    debugPrint("socket conversation > $codec $sampleRate $force");
    return await socket(codec: codec, sampleRate: sampleRate, language: language, force: force);
  }

  @override
  Future<ITranscriptSegmentSocketService?> speechProfile(
      {required BleAudioCodec codec, required int sampleRate, required String language, bool force = false}) async {
    debugPrint("socket speech profile > $codec $sampleRate $force");
    return await socket(codec: codec, sampleRate: sampleRate, language: language, force: force);
  }
}
