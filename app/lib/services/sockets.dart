import 'dart:async';

import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/bt_device/bt_device.dart';
import 'package:omi/models/custom_stt_config.dart';
import 'package:omi/services/sockets/transcription_service.dart';
import 'package:omi/utils/debug_log_manager.dart';
import 'package:omi/utils/logger.dart';
import 'package:omi/utils/mutex.dart';

export 'package:omi/services/freemium_transcription_service.dart';

abstract class ISocketService {
  void start();

  void stop();

  Future<void> stopSpeechProfile();

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

typedef SpeechProfileSocketFactory = TranscriptSegmentSocketService Function(
  int sampleRate,
  BleAudioCodec codec,
  String language, {
  String? source,
});

class SocketServicePool extends ISocketService {
  SocketServicePool({SpeechProfileSocketFactory? speechProfileFactory, Mutex? mutex})
      : _speechProfileFactory = speechProfileFactory ?? _createSpeechProfileSocket,
        _mutex = mutex ?? Mutex();

  TranscriptSegmentSocketService? _socket;
  TranscriptSegmentSocketService? _speechProfileSocket;
  final SpeechProfileSocketFactory _speechProfileFactory;

  @override
  void start() {}

  @override
  void stop() async {
    await _socket?.stop();
    await _speechProfileSocket?.stop();
  }

  final Mutex _mutex;

  static TranscriptSegmentSocketService _createSpeechProfileSocket(
    int sampleRate,
    BleAudioCodec codec,
    String language, {
    String? source,
  }) {
    return SpeechProfileTranscriptSegmentSocketService.create(
      sampleRate,
      codec,
      language,
      source: source,
      onboardingMode: true,
    );
  }

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
      final persistedConfig = SharedPreferencesUtil().customSttConfig;
      final persistedSttConfigId = persistedConfig.isEnabled ? persistedConfig.sttConfigId : 'omi:default';
      if (sttConfigId != persistedSttConfigId) {
        Logger.debug('Dropping stale transcription socket request after STT policy changed');
        return null;
      }

      // Check if we can reuse existing socket (same codec, sample rate, config, and connected)
      if (!force &&
          _socket?.codec == codec &&
          _socket?.sampleRate == sampleRate &&
          _socket?.state == SocketServiceState.connected &&
          _socket?.sttConfigId == sttConfigId) {
        Logger.debug("Reusing existing socket connection");
        return _socket;
      }

      Logger.debug(
        "_connect force=$force state=${_socket?.state} configChanged=${_socket?.sttConfigId != sttConfigId}",
      );

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
        _socket = TranscriptSocketServiceFactory.createDefault(
          sampleRate,
          codec,
          language,
          source: source,
          sttConfigId: sttConfigId,
        );
      }

      await _socket?.start();
      if (_socket?.state != SocketServiceState.connected) {
        return null;
      }

      final latestConfig = SharedPreferencesUtil().customSttConfig;
      final latestSttConfigId = latestConfig.isEnabled ? latestConfig.sttConfigId : 'omi:default';
      if (sttConfigId != latestSttConfigId) {
        final staleSocket = _socket;
        _socket = null;
        await staleSocket?.stop(reason: 'STT policy changed while socket was connecting');
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
    Logger.debug(
      "socket conversation > $codec $sampleRate $force source: $source customStt: ${customSttConfig?.provider}",
    );
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
    Logger.debug("socket speech profile > $codec $sampleRate $force source: $source");

    // Speech-profile onboarding is a separate Omi transcription egress path.
    // Keep localOnly independent of that backend as well.
    final customSttConfig = SharedPreferencesUtil().customSttConfig;
    if (customSttConfig.isLocalOnlyPolicy) {
      Logger.debug("socket speech profile > blocked: localOnly policy active");
      DebugLogManager.logWarning('speech_profile_socket_blocked_local_only', {'reason': 'local_only_policy'});
      return null;
    }

    await _mutex.acquire();
    try {
      // The caller may have waited while settings changed. Re-read policy
      // while still holding the same mutex used for socket creation so a
      // localOnly transition cannot race into a new speech-profile socket.
      final currentConfig = SharedPreferencesUtil().customSttConfig;
      if (currentConfig.isLocalOnlyPolicy) {
        Logger.debug("socket speech profile > blocked after mutex: localOnly policy active");
        DebugLogManager.logWarning('speech_profile_socket_blocked_local_only', {'reason': 'local_only_policy'});
        return null;
      }

      // Use separate socket for speech profile to avoid conflicts with conversation socket
      await _speechProfileSocket?.stop();

      final stoppedConfig = SharedPreferencesUtil().customSttConfig;
      if (stoppedConfig.isLocalOnlyPolicy) {
        Logger.debug("socket speech profile > blocked after stop: localOnly policy active");
        DebugLogManager.logWarning('speech_profile_socket_blocked_local_only', {'reason': 'local_only_policy'});
        return null;
      }

      _speechProfileSocket = _speechProfileFactory(
        sampleRate,
        codec,
        language,
        source: source,
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

  @override
  Future<void> stopSpeechProfile() async {
    await _mutex.acquire();
    try {
      final socket = _speechProfileSocket;
      _speechProfileSocket = null;
      await socket?.stop(reason: 'localOnly policy transition');
    } finally {
      _mutex.release();
    }
  }
}
