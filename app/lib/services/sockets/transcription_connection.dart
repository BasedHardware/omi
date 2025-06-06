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

abstract interface class ITransctipSegmentSocketServiceListener {
  void onMessageEventReceived(ServerMessageEvent event);

  void onSegmentReceived(List<TranscriptSegment> segments);

  void onError(Object err);

  void onConnected();

  void onClosed();
}

class SpeechProfileTranscriptSegmentSocketService
    extends TranscriptSegmentSocketService {
  SpeechProfileTranscriptSegmentSocketService.create(
    super.sampleRate,
    super.codec,
    super.language, {
    String? sttServerType,
    String? wyomingServerIp,
  }) : super.create(
          includeSpeechProfile: false,
          sttServerType: sttServerType,
          wyomingServerIp: wyomingServerIp,
        );
}

class ConversationTranscriptSegmentSocketService
    extends TranscriptSegmentSocketService {
  ConversationTranscriptSegmentSocketService.create(
    super.sampleRate,
    super.codec,
    super.language, {
    String? sttServerType,
    String? wyomingServerIp,
  }) : super.create(
          includeSpeechProfile: true,
          sttServerType: sttServerType,
          wyomingServerIp: wyomingServerIp,
        );
}

enum SocketServiceState {
  connected,
  disconnected,
}

class TranscriptSegmentSocketService implements IPureSocketListener {
  late PureSocket _socket;
  final Map<Object, ITransctipSegmentSocketServiceListener> _listeners = {};

  SocketServiceState get state => _socket.status == PureSocketStatus.connected
      ? SocketServiceState.connected
      : SocketServiceState.disconnected;

  int sampleRate;
  BleAudioCodec codec;
  String language;
  bool includeSpeechProfile;

  TranscriptSegmentSocketService.create(
    this.sampleRate,
    this.codec,
    this.language, {
    this.includeSpeechProfile = false,
    String? sttServerType,
    String? wyomingServerIp,
  }) {
    // Get STT settings from SharedPreferences if not provided
    final prefs = SharedPreferencesUtil();
    sttServerType ??= prefs.sttServerType;
    wyomingServerIp ??= prefs.wyomingServerIp;

    // Debug: Print all URL building steps
    String backendUrl = _getCurrentBackendUrl();
    debugPrint('[TranscriptionService] Initial backend URL: $backendUrl');

    // Clean backend URL - ensure no trailing slash
    if (backendUrl.endsWith('/')) {
      backendUrl = backendUrl.substring(0, backendUrl.length - 1);
      debugPrint('[TranscriptionService] Removed trailing slash: $backendUrl');
    }

    // Build parameters
    var params =
        '?language=$language&sample_rate=$sampleRate&codec=$codec&uid=${prefs.uid}'
        '&include_speech_profile=$includeSpeechProfile';

    if (sttServerType == 'wyoming') {
      params += '&stt_service=$sttServerType&wyoming_server=$wyomingServerIp';
    }

    debugPrint('[TranscriptionService] URL parameters: $params');

    // Convert to WebSocket URL
    String wsUrl;
    if (backendUrl.startsWith('https://')) {
      wsUrl = backendUrl.replaceFirst('https://', 'wss://');
      debugPrint('[TranscriptionService] Converted HTTPS to WSS: $wsUrl');
    } else if (backendUrl.startsWith('http://')) {
      wsUrl = backendUrl.replaceFirst('http://', 'ws://');
      debugPrint('[TranscriptionService] Converted HTTP to WS: $wsUrl');
    } else {
      // Handle URLs without protocol
      if (backendUrl.contains('localhost') ||
          backendUrl.startsWith('10.') ||
          backendUrl.startsWith('192.168.')) {
        wsUrl = 'ws://$backendUrl';
        debugPrint(
            '[TranscriptionService] Added WS protocol for local network: $wsUrl');
      } else {
        wsUrl = 'wss://$backendUrl';
        debugPrint(
            '[TranscriptionService] Added WSS protocol for remote network: $wsUrl');
      }
    }

    // Ensure no trailing slash before adding path
    if (wsUrl.endsWith('/')) {
      wsUrl = wsUrl.substring(0, wsUrl.length - 1);
    }

    String finalUrl = '$wsUrl/v4/listen$params';
    debugPrint('[TranscriptionService] Final WebSocket URL: $finalUrl');
    debugPrint('[TranscriptionService] STT Service Type: $sttServerType');
    if (sttServerType == 'wyoming') {
      debugPrint('[TranscriptionService] Wyoming Server IP: $wyomingServerIp');
    }

    _socket = PureSocket(finalUrl);
    _socket.setListener(this);
  }

  String _getCurrentBackendUrl() {
    final prefs = SharedPreferencesUtil();

    // Check for custom API URL first
    final customUrl = prefs.getString('custom_api_base_url');
    if (customUrl != null && customUrl.isNotEmpty) {
      debugPrint('[TranscriptionService] Using custom backend URL: $customUrl');
      return customUrl;
    }

    // Fall back to environment default
    final defaultUrl = Env.apiBaseUrl;
    if (defaultUrl != null && defaultUrl.isNotEmpty) {
      debugPrint(
          '[TranscriptionService] Using default backend URL: $defaultUrl');
      return defaultUrl;
    }

    // Last resort fallback
    debugPrint(
        '[TranscriptionService] No backend URL configured, using localhost');
    return 'http://localhost:8000';
  }

  String _buildWebSocketUrl(String params) {
    String backendUrl = _getCurrentBackendUrl();

    // Convert HTTP(S) to WebSocket protocol
    String wsUrl;
    if (backendUrl.startsWith('https://')) {
      wsUrl = backendUrl.replaceFirst('https://', 'wss://');
    } else if (backendUrl.startsWith('http://')) {
      wsUrl = backendUrl.replaceFirst('http://', 'ws://');
    } else if (backendUrl.startsWith('ws://') ||
        backendUrl.startsWith('wss://')) {
      // Already a WebSocket URL
      wsUrl = backendUrl;
    } else {
      // Assume HTTP and convert to WebSocket
      wsUrl = 'ws://$backendUrl';
    }

    // Ensure no trailing slash before adding path
    if (wsUrl.endsWith('/')) {
      wsUrl = wsUrl.substring(0, wsUrl.length - 1);
    }

    return '${wsUrl}/v4/listen$params';
  }

  void subscribe(
      Object context, ITransctipSegmentSocketServiceListener listener) {
    _listeners.remove(context.hashCode);
    _listeners.putIfAbsent(context.hashCode, () => listener);
  }

  void unsubscribe(Object context) {
    _listeners.remove(context.hashCode);
  }

  Future start() async {
    bool ok = await _socket.connect();
    if (!ok) {
      debugPrint("[TranscriptionService] Failed to connect to websocket");
    } else {
      debugPrint(
          "[TranscriptionService] Successfully connected to transcription service");
    }
  }

  Future stop({String? reason}) async {
    await _socket.stop();
    _listeners.clear();

    if (reason != null) {
      debugPrint('[TranscriptionService] Socket stopped: $reason');
    }
  }

  Future send(dynamic message) async {
    _socket.send(message);
    return;
  }

  @override
  void onClosed() {
    debugPrint('[TranscriptionService] WebSocket connection closed');
    _listeners.forEach((k, v) {
      v.onClosed();
    });
  }

  @override
  void onError(Object err, StackTrace trace) {
    debugPrint('[TranscriptionService] WebSocket error: $err');
    _listeners.forEach((k, v) {
      v.onError(err);
    });
  }

  @override
  void onMessage(event) {
    // Decode json
    dynamic jsonEvent;
    try {
      jsonEvent = jsonDecode(event);
    } on FormatException catch (e) {
      debugPrint('[TranscriptionService] JSON decode error: ${e.toString()}');
    }
    if (jsonEvent == null) {
      debugPrint(
          "[TranscriptionService] Failed to decode message event JSON: $event");
      return;
    }

    // Transcript segments
    if (jsonEvent is List) {
      var segments = jsonEvent;
      if (segments.isEmpty) {
        return;
      }
      debugPrint(
          '[TranscriptionService] Received ${segments.length} transcript segments');
      _listeners.forEach((k, v) {
        v.onSegmentReceived(
            segments.map((e) => TranscriptSegment.fromJson(e)).toList());
      });
      return;
    }

    // Message event
    if (jsonEvent.containsKey("type")) {
      var event = ServerMessageEvent.fromJson(jsonEvent);
      debugPrint(
          '[TranscriptionService] Received message event: ${event.type}');
      _listeners.forEach((k, v) {
        v.onMessageEventReceived(event);
      });
      return;
    }

    debugPrint(
        '[TranscriptionService] Unknown message format: ${event.toString()}');
  }

  @override
  void onInternetConnectionFailed() {
    debugPrint("[TranscriptionService] Internet connection failed");

    // Send notification
    NotificationService.instance.clearNotification(3);
    NotificationService.instance.createNotification(
      notificationId: 3,
      title: 'Internet Connection Lost',
      body:
          'Your device is offline. Transcription is paused until connection is restored.',
    );
  }

  @override
  void onMaxRetriesReach() {
    debugPrint("[TranscriptionService] Maximum connection retries reached");

    // Send notification
    NotificationService.instance.clearNotification(2);
    NotificationService.instance.createNotification(
      notificationId: 2,
      title: 'Connection Issue',
      body: 'Unable to connect to the transcript service.'
          ' Please restart the app or contact support if the problem persists.',
    );
  }

  @override
  void onConnected() {
    debugPrint('[TranscriptionService] WebSocket connected successfully');
    _listeners.forEach((k, v) {
      v.onConnected();
    });
  }
}
