import 'dart:async';

import 'package:flutter/material.dart';
export 'package:omi/services/freemium_transcription_service.dart';
import 'package:omi/backend/schema/bt_device/bt_device.dart';
import 'package:omi/models/custom_stt_config.dart';
import 'package:omi/utils/mutex.dart';
import 'package:omi/services/sockets/transcription_service.dart';

abstract class ISocketService {
  void start();

  void stop();

  Future<TranscriptSegmentSocketService?> conversation({
    required BleAudioCodec codec,
    required int sampleRate,
    required String language,
    bool force = false,
    String? source,
    CustomSttConfig? customSttConfig,
  });

  Future<TranscriptSegmentSocketService?> speechProfile({
    required BleAudioCodec codec,
    required int sampleRate,
    required String language,
    bool force = false,
    String? source,
  });
}

abstract interface class ISocketServiceSubsciption {}

class SocketServicePool extends ISocketService {
  TranscriptSegmentSocketService? _socket;
  TranscriptSegmentSocketService? _speechProfileSocket;

  @override
  void start() {}

  @override
  void stop() async {
    await _socket?.stop();
    await _speechProfileSocket?.stop();
  }

  // Warn: Should use a better solution to prevent race conditions
  final Mutex _mutex = Mutex();

  Future<TranscriptSegmentSocketService?> socket({
    required BleAudioCodec codec,
    required int sampleRate,
    required String language,
    bool force = false,
    String? source,
    CustomSttConfig? customSttConfig,
  }) async {
    await _mutex.acquire();
    try {
      final sttConfigId = customSttConfig?.sttConfigId ?? 'omi:default';

      // Check if we can reuse existing socket (same codec, sample rate, config, and connected)
      if (!force &&
          _socket?.codec == codec &&
          _socket?.sampleRate == sampleRate &&
          _socket?.state == SocketServiceState.connected &&
          _socket?.sttConfigId == sttConfigId) {
        debugPrint("Reusing existing socket connection");
        return _socket;
      }

      debugPrint("_connect force=$force state=${_socket?.state} configChanged=${_socket?.sttConfigId != sttConfigId}");

      // new socket
      await _socket?.stop();

      if (customSttConfig != null && customSttConfig.isEnabled) {
        _socket = TranscriptSocketServiceFactory.createFromCustomConfig(
          sampleRate,
          codec,
          language,
          customSttConfig,
          source: source,
        );
      } else {
        _socket = TranscriptSocketServiceFactory.createDefault(sampleRate, codec, language, source: source, sttConfigId: sttConfigId);
      }

      await _socket?.start();
      if (_socket?.state != SocketServiceState.connected) {
        return null;
      }

      return _socket;
    } finally {
      _mutex.release();
    }
  }

  @override
  Future<TranscriptSegmentSocketService?> conversation({
    required BleAudioCodec codec,
    required int sampleRate,
    required String language,
    bool force = false,
    String? source,
    CustomSttConfig? customSttConfig,
  }) async {
    debugPrint("socket conversation > $codec $sampleRate $force source: $source customStt: ${customSttConfig?.provider}");
    return await socket(
      codec: codec,
      sampleRate: sampleRate,
      language: language,
      force: force,
      source: source,
      customSttConfig: customSttConfig,
    );
  }

  @override
  Future<TranscriptSegmentSocketService?> speechProfile({
    required BleAudioCodec codec,
    required int sampleRate,
    required String language,
    bool force = false,
    String? source,
  }) async {
    debugPrint("socket speech profile > $codec $sampleRate $force source: $source");
    
    await _mutex.acquire();
    try {
      // Use separate socket for speech profile to avoid conflicts with conversation socket
      await _speechProfileSocket?.stop();
      
      _speechProfileSocket = SpeechProfileTranscriptSegmentSocketService.create(
        sampleRate,
        codec,
        language,
        source: source,
        onboardingMode: true,
      );
      
      await _speechProfileSocket?.start();
      if (_speechProfileSocket?.state != SocketServiceState.connected) {
        return null;
      }
      
      return _speechProfileSocket;
    } finally {
      _mutex.release();
    }
  }
}
