import 'dart:async';
import 'dart:math';

import 'package:flutter/material.dart';
import 'package:friend_private/backend/database/transcript_segment.dart';
import 'package:friend_private/backend/schema/bt_device.dart';
import 'package:friend_private/services/notification_service.dart';
import 'package:friend_private/utils/websockets.dart';
import 'package:internet_connection_checker_plus/internet_connection_checker_plus.dart';
import 'package:web_socket_channel/io.dart';

mixin WebSocketMixin {
  WebsocketConnectionStatus wsConnectionState = WebsocketConnectionStatus.notConnected;
  bool websocketReconnecting = false;
  IOWebSocketChannel? websocketChannel;
  int _reconnectionAttempts = 0;
  Timer? _reconnectionTimer;
  StreamSubscription<InternetStatus>? _internetListener;
  InternetStatus _internetStatus = InternetStatus.connected;

  final int _initialReconnectDelay = 1;
  final int _maxReconnectDelay = 60;
  bool _isConnecting = false;

  bool _hasNotifiedUser = false;
  bool _internetListenerSetup = false;
  Timer? internetLostNotificationDelay;

  Future<void> initWebSocket({
    required Function onConnectionSuccess,
    required Function(dynamic) onConnectionFailed,
    required Function(int?, String?) onConnectionClosed,
    required Function(dynamic) onConnectionError,
    required Function(List<TranscriptSegment>) onMessageReceived,
    required BleAudioCodec codec,
    required int sampleRate,
    required bool includeSpeechProfile,
  }) async {
    if (_isConnecting) return;
    _isConnecting = true;

    debugPrint('initWebSocket ${codec} ${sampleRate}');
    if (!_internetListenerSetup) {
      _setupInternetListener(
        onConnectionSuccess: onConnectionSuccess,
        onConnectionFailed: onConnectionFailed,
        onConnectionClosed: onConnectionClosed,
        onConnectionError: onConnectionError,
        onMessageReceived: onMessageReceived,
        codec: codec,
        sampleRate: sampleRate,
        includeSpeechProfile: includeSpeechProfile,
      );
      _internetListenerSetup = true;
    }

    if (_internetStatus == InternetStatus.disconnected) {
      debugPrint('No internet connection. Waiting for connection to be restored.');
      _isConnecting = false;
      return;
    }

    try {
      websocketChannel = await streamingTranscript(
        onWebsocketConnectionSuccess: () {
          debugPrint('WebSocket connected successfully');
          wsConnectionState = WebsocketConnectionStatus.connected;
          websocketReconnecting = false;
          _reconnectionAttempts = 0;
          _isConnecting = false;
          onConnectionSuccess();
          NotificationService.instance.clearNotification(2);
        },
        onWebsocketConnectionFailed: (err) {
          debugPrint('WebSocket connection failed: $err');
          wsConnectionState = WebsocketConnectionStatus.failed;
          websocketReconnecting = false;
          _isConnecting = false;
          onConnectionFailed(err);
          _scheduleReconnection(
            onConnectionSuccess: onConnectionSuccess,
            onConnectionFailed: onConnectionFailed,
            onConnectionClosed: onConnectionClosed,
            onConnectionError: onConnectionError,
            onMessageReceived: onMessageReceived,
            codec: codec,
            sampleRate: sampleRate,
            includeSpeechProfile: includeSpeechProfile,
          );
        },
        onWebsocketConnectionClosed: (int? closeCode, String? closeReason) {
          debugPrint('WebSocket connection closed: code ~ $closeCode, reason ~ $closeReason');
          wsConnectionState = WebsocketConnectionStatus.closed;
          _isConnecting = false;
          onConnectionClosed(closeCode, closeReason);
          if (closeCode != 1000 && !websocketReconnecting) {
            _scheduleReconnection(
              onConnectionSuccess: onConnectionSuccess,
              onConnectionFailed: onConnectionFailed,
              onConnectionClosed: onConnectionClosed,
              onConnectionError: onConnectionError,
              onMessageReceived: onMessageReceived,
              codec: codec,
              sampleRate: sampleRate,
              includeSpeechProfile: includeSpeechProfile,
            );
          }
        },
        onWebsocketConnectionError: (err) {
          debugPrint('WebSocket connection error: $err');
          wsConnectionState = WebsocketConnectionStatus.error;
          websocketReconnecting = false;
          _isConnecting = false;
          onConnectionError(err);
          _scheduleReconnection(
            onConnectionSuccess: onConnectionSuccess,
            onConnectionFailed: onConnectionFailed,
            onConnectionClosed: onConnectionClosed,
            onConnectionError: onConnectionError,
            onMessageReceived: onMessageReceived,
            codec: codec,
            sampleRate: sampleRate,
            includeSpeechProfile: includeSpeechProfile,
          );
        },
        onMessageReceived: onMessageReceived,
        codec: codec,
        sampleRate: sampleRate,
        includeSpeechProfile: includeSpeechProfile,

      );
    } catch (e) {
      debugPrint('Error in initWebSocket: $e');
      _isConnecting = false;
      onConnectionFailed(e);
    }
  }

  void _setupInternetListener({
    required Function onConnectionSuccess,
    required Function(dynamic) onConnectionFailed,
    required Function(int?, String?) onConnectionClosed,
    required Function(dynamic) onConnectionError,
    required Function(List<TranscriptSegment>) onMessageReceived,
    required BleAudioCodec codec,
    required int sampleRate,
    required bool includeSpeechProfile,
  }) {
    _internetListener?.cancel();
    _internetListener = InternetConnection().onStatusChange.listen((InternetStatus status) {
      _internetStatus = status;
      switch (status) {
        case InternetStatus.connected:
          if (wsConnectionState != WebsocketConnectionStatus.connected && !_isConnecting) {
            debugPrint('Internet connection restored. Attempting to reconnect WebSocket.');
            internetLostNotificationDelay?.cancel();
            _reconnectionTimer?.cancel();
            _reconnectionAttempts = 0;
            _attemptReconnection(
              onConnectionSuccess: onConnectionSuccess,
              onConnectionFailed: onConnectionFailed,
              onConnectionClosed: onConnectionClosed,
              onConnectionError: onConnectionError,
              onMessageReceived: onMessageReceived,
              codec: codec,
              sampleRate: sampleRate,
              includeSpeechProfile: includeSpeechProfile,
            );
          }
          break;
        case InternetStatus.disconnected:
          debugPrint('Internet connection lost. Disconnecting WebSocket.');
          internetLostNotificationDelay?.cancel();
          internetLostNotificationDelay = Timer(const Duration(seconds: 60), () => _notifyInternetLost());
          websocketChannel?.sink.close(1000, 'Internet connection lost');
          _reconnectionTimer?.cancel();
          wsConnectionState = WebsocketConnectionStatus.notConnected;
          onConnectionClosed(1000, 'Internet connection lost');
          break;
      }
    });
  }

  void _scheduleReconnection({
    required Function onConnectionSuccess,
    required Function(dynamic) onConnectionFailed,
    required Function(int?, String?) onConnectionClosed,
    required Function(dynamic) onConnectionError,
    required Function(List<TranscriptSegment>) onMessageReceived,
    required BleAudioCodec codec,
    required int sampleRate,
    required bool includeSpeechProfile,
  }) {
    if (websocketReconnecting || _internetStatus == InternetStatus.disconnected || _isConnecting) return;

    websocketReconnecting = true;
    _reconnectionAttempts++;

    // if reconnection limits
    // if (_reconnectionAttempts > _maxReconnectionAttempts) {
    //   debugPrint('Max reconnection attempts reached');
    //   _notifyReconnectionFailure();
    //   websocketReconnecting = false;
    //   return;
    // }

    int delaySeconds = _calculateReconnectDelay();
    debugPrint('Scheduling reconnection attempt $_reconnectionAttempts in $delaySeconds seconds');

    _reconnectionTimer?.cancel();
    _reconnectionTimer = Timer(Duration(seconds: delaySeconds), () {
      _attemptReconnection(
        onConnectionSuccess: onConnectionSuccess,
        onConnectionFailed: onConnectionFailed,
        onConnectionClosed: onConnectionClosed,
        onConnectionError: onConnectionError,
        onMessageReceived: onMessageReceived,
        codec: codec,
        sampleRate: sampleRate,
        includeSpeechProfile: includeSpeechProfile,
      );
    });
    if (_reconnectionAttempts == 6 && !_hasNotifiedUser) {
      _notifyReconnectionFailure();
      _hasNotifiedUser = true;
    }
  }

  int _calculateReconnectDelay() {
    int delay = _initialReconnectDelay * pow(2, _reconnectionAttempts - 1).toInt();
    return min(delay, _maxReconnectDelay);
  }

  Future<void> _attemptReconnection({
    required Function onConnectionSuccess,
    required Function(dynamic) onConnectionFailed,
    required Function(int?, String?) onConnectionClosed,
    required Function(dynamic) onConnectionError,
    required Function(List<TranscriptSegment>) onMessageReceived,
    required BleAudioCodec codec,
    required int sampleRate,
    required bool includeSpeechProfile,
  }) async {
    if (_internetStatus == InternetStatus.disconnected) {
      debugPrint('Cannot attempt reconnection: No internet connection');
      return;
    }

    debugPrint('Attempting reconnection');
    websocketChannel?.sink.close(1000);
    await initWebSocket(
      onConnectionSuccess: onConnectionSuccess,
      onConnectionFailed: onConnectionFailed,
      onConnectionClosed: onConnectionClosed,
      onConnectionError: onConnectionError,
      onMessageReceived: onMessageReceived,
      codec: codec,
      sampleRate: sampleRate,
      includeSpeechProfile: includeSpeechProfile,
    );
  }

  void _notifyReconnectionFailure() {
    NotificationService.instance.clearNotification(2);
    NotificationService.instance.createNotification(
      notificationId: 2,
      title: 'Connection Issue 🚨',
      body: 'Unable to connect to the transcript service.'
          ' Please restart the app or contact support if the problem persists.',
    );
  } // TODO: should trigger a connection restored? as with internet?

  void _notifyInternetLost() {
    NotificationService.instance.clearNotification(3);
    NotificationService.instance.createNotification(
      notificationId: 3,
      title: 'Internet Connection Lost',
      body: 'Your device is offline. Transcription is paused until connection is restored.',
    );
  }

  void closeWebSocket() {
    _reconnectionTimer?.cancel();
    _internetListener?.cancel();
    internetLostNotificationDelay?.cancel();
    websocketChannel?.sink.close(1000);
    // TODO: once closed, it reconnects, at least happens on speaker_profile/page
  }
}
