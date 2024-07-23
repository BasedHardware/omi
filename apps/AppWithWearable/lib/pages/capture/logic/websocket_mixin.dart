import 'dart:async';
import 'dart:math';

import 'package:flutter/material.dart';
import 'package:friend_private/backend/database/transcript_segment.dart';
import 'package:friend_private/utils/other/notifications.dart';
import 'package:friend_private/utils/websockets.dart';
import 'package:internet_connection_checker_plus/internet_connection_checker_plus.dart';
import 'package:web_socket_channel/io.dart';

mixin WebSocketMixin {
  WebsocketConnectionStatus wsConnectionState = WebsocketConnectionStatus.notConnected;
  bool websocketReconnecting = false;
  IOWebSocketChannel? websocketChannel;
  int _reconnectionAttempts = 0;
  Timer? _reconnectionTimer;
  late StreamSubscription<InternetStatus> _internetListener;
  InternetStatus _internetStatus = InternetStatus.connected;

  final int _initialReconnectDelay = 1;
  final int _maxReconnectDelay = 60;
  final int _maxReconnectionAttempts = 3;

  Future<void> initWebSocket({
    required Function onConnectionSuccess,
    required Function(dynamic) onConnectionFailed,
    required Function(int?, String?) onConnectionClosed,
    required Function(dynamic) onConnectionError,
    required Function(List<TranscriptSegment>) onMessageReceived,
  }) async {
    _setupInternetListener(
      onConnectionSuccess: onConnectionSuccess,
      onConnectionFailed: onConnectionFailed,
      onConnectionClosed: onConnectionClosed,
      onConnectionError: onConnectionError,
      onMessageReceived: onMessageReceived,
    );

    if (_internetStatus == InternetStatus.disconnected) {
      debugPrint('No internet connection. Waiting for connection to be restored.');
      return;
    }

    websocketChannel = await streamingTranscript(
      onWebsocketConnectionSuccess: () {
        wsConnectionState = WebsocketConnectionStatus.connected;
        websocketReconnecting = false;
        _reconnectionAttempts = 0;
        onConnectionSuccess();
      },
      onWebsocketConnectionFailed: (err) {
        wsConnectionState = WebsocketConnectionStatus.failed;
        websocketReconnecting = false;
        onConnectionFailed(err);
        _scheduleReconnection(
          onConnectionSuccess: onConnectionSuccess,
          onConnectionFailed: onConnectionFailed,
          onConnectionClosed: onConnectionClosed,
          onConnectionError: onConnectionError,
          onMessageReceived: onMessageReceived,
        );
      },
      onWebsocketConnectionClosed: (int? closeCode, String? closeReason) {
        wsConnectionState = WebsocketConnectionStatus.closed;
        onConnectionClosed(closeCode, closeReason);
        if (closeCode != 1000) {
          _scheduleReconnection(
            onConnectionSuccess: onConnectionSuccess,
            onConnectionFailed: onConnectionFailed,
            onConnectionClosed: onConnectionClosed,
            onConnectionError: onConnectionError,
            onMessageReceived: onMessageReceived,
          );
        }
      },
      onWebsocketConnectionError: (err) {
        wsConnectionState = WebsocketConnectionStatus.error;
        websocketReconnecting = false;
        onConnectionError(err);
        _scheduleReconnection(
          onConnectionSuccess: onConnectionSuccess,
          onConnectionFailed: onConnectionFailed,
          onConnectionClosed: onConnectionClosed,
          onConnectionError: onConnectionError,
          onMessageReceived: onMessageReceived,
        );
      },
      onMessageReceived: onMessageReceived,
    );
  }

  void _setupInternetListener({
    required Function onConnectionSuccess,
    required Function(dynamic) onConnectionFailed,
    required Function(int?, String?) onConnectionClosed,
    required Function(dynamic) onConnectionError,
    required Function(List<TranscriptSegment>) onMessageReceived,
  }) {
    _internetListener = InternetConnection().onStatusChange.listen((InternetStatus status) {
      _internetStatus = status;
      switch (status) {
        case InternetStatus.connected:
          debugPrint('Internet connection restored. Attempting to reconnect WebSocket.');
          _reconnectionTimer?.cancel();
          _reconnectionAttempts = 0; // Reset attempts when internet is restored
          _attemptReconnection(
            onConnectionSuccess: onConnectionSuccess,
            onConnectionFailed: onConnectionFailed,
            onConnectionClosed: onConnectionClosed,
            onConnectionError: onConnectionError,
            onMessageReceived: onMessageReceived,
          );
          break;
        case InternetStatus.disconnected:
          debugPrint('Internet connection lost. Disconnecting WebSocket.');
          websocketChannel?.sink.close(1000, 'Internet connection lost');
          _reconnectionTimer?.cancel();
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
  }) {
    if (websocketReconnecting || _internetStatus == InternetStatus.disconnected) return;

    websocketReconnecting = true;
    _reconnectionAttempts++;

    if (_reconnectionAttempts > _maxReconnectionAttempts) {
      debugPrint('Max reconnection attempts reached');
      _notifyReconnectionFailure();
      return;
    }

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
      );
    });
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
    );
  }

  void _notifyReconnectionFailure() {
    clearNotification(2);
    createNotification(
      notificationId: 2,
      title: 'Connection Issue',
      body:
          'Unable to connect to the transcription service. Please check your internet connection and restart the app if the problem persists.',
    );
  }

  void closeWebSocket() {
    websocketChannel?.sink.close(1000);
    _reconnectionTimer?.cancel();
    _internetListener.cancel();
  }
}
