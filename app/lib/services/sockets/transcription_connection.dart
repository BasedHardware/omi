import 'dart:async';
import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/bt_device/bt_device.dart';
import 'package:omi/backend/schema/message_event.dart';
import 'package:omi/backend/schema/transcript_segment.dart';
import 'package:omi/env/env.dart';
import 'package:omi/services/notifications.dart';
import 'package:omi/services/sockets/pure_socket.dart';
import 'package:omi/utils/debug_log_manager.dart';

abstract interface class ITransctipSegmentSocketServiceListener {
  void onMessageEventReceived(MessageEvent event);

  void onSegmentReceived(List<TranscriptSegment> segments);

  void onError(Object err);

  void onConnected();

  void onClosed([int? closeCode]);
}

class SpeechProfileTranscriptSegmentSocketService extends TranscriptSegmentSocketService {
  SpeechProfileTranscriptSegmentSocketService.create(super.sampleRate, super.codec, super.language)
      : super.create(includeSpeechProfile: false);
}

class ConversationTranscriptSegmentSocketService extends TranscriptSegmentSocketService {
  ConversationTranscriptSegmentSocketService.create(super.sampleRate, super.codec, super.language)
      : super.create(includeSpeechProfile: true);
}

enum SocketServiceState {
  connected,
  disconnected,
}

class TranscriptSegmentSocketService implements IPureSocketListener {
  late PureSocket _socket;
  final Map<Object, ITransctipSegmentSocketServiceListener> _listeners = {};

  SocketServiceState get state =>
      _socket.status == PureSocketStatus.connected ? SocketServiceState.connected : SocketServiceState.disconnected;

  int sampleRate;
  BleAudioCodec codec;
  String language;
  bool includeSpeechProfile;
  String _sttService = '';
  late final List<String> _candidateServices;
  final Set<String> _attemptedServices = <String>{};
  bool _fallbackInProgress = false;

  TranscriptSegmentSocketService.create(
    this.sampleRate,
    this.codec,
    this.language, {
    this.includeSpeechProfile = false,
  }) {
    final prefModel = SharedPreferencesUtil().transcriptionModel.trim();
    if (prefModel.isNotEmpty) {
      _sttService = prefModel.toLowerCase();
      _attemptedServices.add(_sttService);
    }
    _candidateServices = _buildCandidateServices();
    _createSocket();
  }

  String _buildUrl() {
    final params =
        '?language=$language&sample_rate=$sampleRate&codec=$codec&uid=${SharedPreferencesUtil().uid}'
        '&include_speech_profile=$includeSpeechProfile&stt_service=${_sttService}'
        '&conversation_timeout=${SharedPreferencesUtil().conversationSilenceDuration}';

    final base = Env.apiBaseUrl!
        .replaceFirst('https://', 'wss://')
        .replaceFirst('http://', 'ws://');

    return '$base' 'v4/listen$params';
  }

  List<String> _buildCandidateServices() {
    const orderedFallbacks = ['elevenlabs', 'soniox', 'deepgram', 'speechmatics'];
    final seen = <String>{};
    final result = <String>[];

    void add(String? value) {
      if (value == null || value.isEmpty) return;
      final normalized = value.toLowerCase();
      if (seen.add(normalized)) {
        result.add(normalized);
      }
    }

    if (_sttService.isNotEmpty) {
      add(_sttService);
    }
    for (final fallback in orderedFallbacks) {
      add(fallback);
    }

    return result;
  }

  void _createSocket() {
    final url = _buildUrl();
    _socket = PureSocket(url);
    _socket.setListener(this);
  }

  String? _nextFallback() {
    for (final candidate in _candidateServices) {
      if (!_attemptedServices.contains(candidate)) {
        return candidate;
      }
    }
    return null;
  }

  void _scheduleFallback(String reason) {
    if (_fallbackInProgress) return;
    Future.microtask(() => _attemptFallback(reason));
  }

  Future<void> _attemptFallback(String reason) async {
    if (_fallbackInProgress) return;
    _fallbackInProgress = true;
    try {
      while (true) {
        final next = _nextFallback();
        if (next == null) {
          await DebugLogManager.logWarning('transcription_socket_fallback_exhausted', {
            'attempted': _attemptedServices.join(','),
            'language': language,
            'sample_rate': sampleRate,
            'codec': codec.toString(),
            'reason': reason,
          });
          break;
        }
        final connected = await _reconnectWithSttService(next, reason: reason);
        if (connected) {
          break;
        }
      }
    } finally {
      _fallbackInProgress = false;
    }
  }

  Future<bool> _reconnectWithSttService(String next, {required String reason}) async {
    if (next == _sttService) return false;
    final prev = _sttService;
    _sttService = next;
    _attemptedServices.add(next);
    await _socket.stop();
    _createSocket();
    final ok = await _socket.connect();
    await DebugLogManager.logEvent('transcription_socket_fallback', {
      'from': prev,
      'to': next,
      'sample_rate': sampleRate,
      'codec': codec.toString(),
      'language': language,
      'reason': reason,
      'success': ok,
    });
    if (!ok) {
      await DebugLogManager.logWarning('transcription_socket_fallback_failed', {
        'from': prev,
        'to': next,
        'sample_rate': sampleRate,
        'codec': codec.toString(),
        'language': language,
        'reason': reason,
      });
    }
    return ok;
  }

  void subscribe(Object context, ITransctipSegmentSocketServiceListener listener) {
    _listeners.remove(context.hashCode);
    _listeners.putIfAbsent(context.hashCode, () => listener);
  }

  void unsubscribe(Object context) {
    _listeners.remove(context.hashCode);
  }

  Future start() async {
    final ok = await _socket.connect();
    if (!ok) {
      debugPrint("Can not connect to websocket");
      await DebugLogManager.logWarning('transcription_socket_connect_failed', {
        'url': Env.apiBaseUrl?.replaceAll('https', 'wss') ?? 'null',
        'sample_rate': sampleRate,
        'codec': codec.toString(),
        'language': language,
        'stt_service': _sttService,
      });
      await _attemptFallback('connect_failed');
    }
  }

  Future stop({String? reason}) async {
    await _socket.stop();
    _listeners.clear();

    if (reason != null) {
      debugPrint(reason);
      await DebugLogManager.logInfo('transcription_socket_stopped', {'reason': reason});
    }
  }

  Future send(dynamic message) async {
    _socket.send(message);
    return;
  }

  @override
  void onClosed([int? closeCode]) {
    _listeners.forEach((k, v) {
      v.onClosed(closeCode);
    });
    DebugLogManager.logEvent('transcription_socket_closed', {
      'close_code': closeCode ?? -1,
    });
  }

  @override
  void onError(Object err, StackTrace trace) {
    _listeners.forEach((k, v) {
      v.onError(err);
    });
    DebugLogManager.logError(err, trace, 'transcription_socket_error');
  }

  @override
  void onMessage(event) {
    // Decode json
    dynamic jsonEvent;
    try {
      jsonEvent = jsonDecode(event);
    } on FormatException catch (e) {
      debugPrint(e.toString());
      DebugLogManager.logWarning('transcription_socket_parse_error', {'error': e.toString()});
    }
    if (jsonEvent == null) {
      debugPrint("Can not decode message event json $event");
      return;
    }

    // Transcript segments
    if (jsonEvent is List) {
      var segments = jsonEvent;
      if (segments.isEmpty) {
        return;
      }
      _listeners.forEach((k, v) {
        v.onSegmentReceived(segments.map((e) => TranscriptSegment.fromJson(e)).toList());
      });
      return;
    }

    // Message event
    if (jsonEvent.containsKey("type")) {
      // Simple fallback trigger on backend service error status
      try {
        final type = jsonEvent['type']?.toString();
        if (type == r'$service_status') {
          final status = jsonEvent['status']?.toString() ?? '';
          final message = jsonEvent['message']?.toString() ?? '';
          if (status.toLowerCase() == 'error' ||
              message.contains('API_KEY') ||
              message.contains('not set')) {
            _scheduleFallback('service_status_error');
          }
        }
      } catch (_) {}
      var event = MessageEvent.fromJson(jsonEvent);
      _listeners.forEach((k, v) {
        v.onMessageEventReceived(event);
      });
      return;
    }

    debugPrint(event.toString());
    DebugLogManager.logInfo('transcription_socket_unhandled_message: ${event.toString()}');
  }

  @override
  void onInternetConnectionFailed() {
    debugPrint("onInternetConnectionFailed");

    // Send notification
    NotificationService.instance.clearNotification(3);
    NotificationService.instance.createNotification(
      notificationId: 3,
      title: 'Internet Connection Lost',
      body: 'Your device is offline. Transcription is paused until connection is restored.',
    );
    DebugLogManager.logEvent('internet_connection_lost', {});
  }

  @override
  void onMaxRetriesReach() {
    debugPrint("onMaxRetriesReach");

    // Send notification
    NotificationService.instance.clearNotification(2);
    NotificationService.instance.createNotification(
      notificationId: 2,
      title: 'Connection Issue 🚨',
      body: 'Unable to connect to the transcript service.'
          ' Please restart the app or contact support if the problem persists.',
    );
    DebugLogManager.logEvent('transcription_socket_max_retries', {});
  }

  @override
  void onConnected() {
    _listeners.forEach((k, v) {
      v.onConnected();
    });
    DebugLogManager.logEvent('transcription_socket_connected', {
      'sample_rate': sampleRate,
      'codec': codec.toString(),
      'language': language,
      'include_speech_profile': includeSpeechProfile,
      'stt_service': _sttService,
    });
  }
}
