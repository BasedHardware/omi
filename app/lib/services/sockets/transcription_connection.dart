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

  TranscriptSegmentSocketService.create(
    this.sampleRate,
    this.codec,
    this.language, {
    this.includeSpeechProfile = false,
  }) {
    var params = '?language=$language&sample_rate=$sampleRate&codec=$codec&uid=${SharedPreferencesUtil().uid}'
        '&include_speech_profile=$includeSpeechProfile&stt_service=${SharedPreferencesUtil().transcriptionModel}';

    String url = '${Env.apiBaseUrl!.replaceAll('https', 'wss')}v4/listen$params';

    _socket = PureSocket(url);
    _socket.setListener(this);
  }

  void subscribe(Object context, ITransctipSegmentSocketServiceListener listener) {
    _listeners.remove(context.hashCode);
    _listeners.putIfAbsent(context.hashCode, () => listener);
  }

  void unsubscribe(Object context) {
    _listeners.remove(context.hashCode);
  }

  Future start() async {
    bool ok = await _socket.connect();
    if (!ok) {
      debugPrint("Can not connect to websocket");
      await DebugLogManager.logWarning('transcription_socket_connect_failed', {
        'url': Env.apiBaseUrl?.replaceAll('https', 'wss') ?? 'null',
        'sample_rate': sampleRate,
        'codec': codec.toString(),
        'language': language,
      });
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
    });
  }
}
