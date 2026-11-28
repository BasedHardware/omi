import 'dart:async';

import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/bt_device/bt_device.dart';
import 'package:omi/backend/schema/geolocation.dart';
import 'package:omi/models/custom_stt_config.dart';
import 'package:omi/services/auth_service.dart';
import 'package:omi/services/sockets/transcription_service.dart';
import 'package:omi/utils/logger.dart';
import 'package:omi/utils/mutex.dart';

export 'package:omi/services/freemium_transcription_service.dart';

abstract class ISocketService {
  void start();

  void stop();

  Future<TranscriptSegmentSocketService?> conversation({
    required BleAudioCodec codec,
    required int sampleRate,
    required String language,
    bool force = false,
    String? source,
    String? clientConversationId,
    CustomSttConfig? customSttConfig,
    Geolocation? geolocation,
    bool localPreview = false,
  });

  /// [customSttConfig] switches the session to on-device transcription
  /// (see TranscriptSocketServiceFactory.createSpeechProfileOnDevice); null
  /// uses the backend's streaming STT.
  Future<TranscriptSegmentSocketService?> speechProfile({
    required BleAudioCodec codec,
    required int sampleRate,
    required String language,
    bool force = false,
    String? source,
    bool speechProfileRedo = false,
    CustomSttConfig? customSttConfig,
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
    String? clientConversationId,
    CustomSttConfig? customSttConfig,
    Geolocation? geolocation,
    bool localPreview = false,
  }) async {
    final uid = SharedPreferencesUtil().uid;
    final customConfig = customSttConfig?.isEnabled == true ? customSttConfig : null;
    final custodyOwner = customConfig != null ? null : TranscriptSegmentSocketService.captureListenOwner(uid);
    bool ownerIsCurrent() =>
        SharedPreferencesUtil().uid == uid &&
        (custodyOwner == null || AuthService.instance.isSessionSnapshotCurrent(custodyOwner));

    await _mutex.acquire();
    try {
      if (!ownerIsCurrent()) return null;
      final sttConfigId = customSttConfig?.sttConfigId ?? 'omi:default';

      // Check if we can reuse existing socket (same codec, sample rate, config, and connected)
      if (!force &&
          _socket?.codec == codec &&
          _socket?.sampleRate == sampleRate &&
          _socket?.language == language &&
          _socket?.state == SocketServiceState.connected &&
          _socket?.sttConfigId == sttConfigId &&
          // Geolocation is a session snapshot. A later location refresh does
          // not justify replacing a healthy live socket and interrupting audio.
          _socket?.clientConversationId == clientConversationId &&
          _socket?.localPreview == localPreview &&
          (custodyOwner == null ? _socket?.audioCustodyEnabled != true : _socket?.hasCurrentListenOwner(uid) == true)) {
        Logger.debug("Reusing existing socket connection");
        return _socket;
      }

      Logger.debug(
        "_connect force=$force state=${_socket?.state} configChanged=${_socket?.sttConfigId != sttConfigId}",
      );

      // new socket
      await _socket?.stop();
      if (!ownerIsCurrent()) return null;

      if (customConfig != null) {
        _socket = TranscriptSocketServiceFactory.createFromCustomConfig(
          sampleRate,
          codec,
          language,
          customConfig,
          source: source,
          geolocation: geolocation,
          clientConversationId: clientConversationId,
        );
      } else {
        _socket = TranscriptSocketServiceFactory.createDefault(
          sampleRate,
          codec,
          language,
          source: source,
          sttConfigId: sttConfigId,
          geolocation: geolocation,
          clientConversationId: clientConversationId,
          // Custom STT never declares it: the server refuses it there anyway.
          localPreview: localPreview,
          custodyOwner: custodyOwner,
        );
      }

      await _socket?.start();
      if (!ownerIsCurrent()) {
        await _socket?.stop(reason: 'stale Listen owner');
        return null;
      }
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
    String? clientConversationId,
    CustomSttConfig? customSttConfig,
    Geolocation? geolocation,
    bool localPreview = false,
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
      clientConversationId: clientConversationId,
      customSttConfig: customSttConfig,
      geolocation: geolocation,
      localPreview: localPreview,
    );
  }

  @override
  Future<TranscriptSegmentSocketService?> speechProfile({
    required BleAudioCodec codec,
    required int sampleRate,
    required String language,
    bool force = false,
    String? source,
    bool speechProfileRedo = false,
    CustomSttConfig? customSttConfig,
  }) async {
    Logger.debug(
      "socket speech profile > $codec $sampleRate $force source: $source localStt: ${customSttConfig?.provider.name}",
    );

    await _mutex.acquire();
    try {
      // Use separate socket for speech profile to avoid conflicts with conversation socket
      await _speechProfileSocket?.stop();

      _speechProfileSocket = customSttConfig != null
          ? TranscriptSocketServiceFactory.createSpeechProfileOnDevice(
              sampleRate,
              codec,
              language,
              customSttConfig,
              source: source,
              speechProfileRedo: speechProfileRedo,
            )
          : SpeechProfileTranscriptSegmentSocketService.create(
              sampleRate,
              codec,
              language,
              source: source,
              onboardingMode: true,
              speechProfileRedo: speechProfileRedo,
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
