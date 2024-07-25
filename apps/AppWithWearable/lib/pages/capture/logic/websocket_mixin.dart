import 'dart:async';
import 'dart:math';

import 'package:flutter/material.dart';
import 'package:friend_private/backend/database/transcript_segment.dart';
import 'package:friend_private/utils/ble/communication.dart';
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
  bool _isConnecting = false;

  // final int _maxReconnectionAttempts = 3;
  bool _hasNotifiedUser = false;
  bool _internetListenerSetup = false;

  Future<void> initWebSocket({
    required Function onConnectionSuccess,
    required Function(dynamic) onConnectionFailed,
    required Function(int?, String?) onConnectionClosed,
    required Function(dynamic) onConnectionError,
    required Function(List<TranscriptSegment>) onMessageReceived,
    BleAudioCodec codec = BleAudioCodec.pcm8,
    int? sampleRate,
  }) async {
    if (_isConnecting) return;
    _isConnecting = true;

    if (!_internetListenerSetup) {
      _setupInternetListener(
        onConnectionSuccess: onConnectionSuccess,
        onConnectionFailed: onConnectionFailed,
        onConnectionClosed: onConnectionClosed,
        onConnectionError: onConnectionError,
        onMessageReceived: onMessageReceived,
        codec: codec,
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
        codec: codec,
        onWebsocketConnectionSuccess: () {
          debugPrint('WebSocket connected successfully');
          wsConnectionState = WebsocketConnectionStatus.connected;
          websocketReconnecting = false;
          _reconnectionAttempts = 0;
          _isConnecting = false;
          onConnectionSuccess();
          clearNotification(2); // clear connection server conn issue?
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
          );
        },
        onWebsocketConnectionClosed: (int? closeCode, String? closeReason) {
          debugPrint('WebSocket connection closed: $closeCode, $closeReason');
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
          );
        },
        onMessageReceived: onMessageReceived,
        sampleRate: sampleRate ?? (codec == BleAudioCodec.opus ? 16000 : 8000),
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
  }) {
    _internetListener = InternetConnection().onStatusChange.listen((InternetStatus status) {
      _internetStatus = status;
      switch (status) {
        case InternetStatus.connected:
          if (wsConnectionState != WebsocketConnectionStatus.connected && !_isConnecting) {
            debugPrint('Internet connection restored. Attempting to reconnect WebSocket.');
            _notifyInternetRestored();
            _reconnectionTimer?.cancel();
            _reconnectionAttempts = 0;
            _attemptReconnection(
              onConnectionSuccess: onConnectionSuccess,
              onConnectionFailed: onConnectionFailed,
              onConnectionClosed: onConnectionClosed,
              onConnectionError: onConnectionError,
              onMessageReceived: onMessageReceived,
              codec: codec,
            );
          }
          break;
        case InternetStatus.disconnected:
          debugPrint('Internet connection lost. Disconnecting WebSocket.');
          _notifyInternetLost();
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
      );
    });
    if (_reconnectionAttempts == 4 && !_hasNotifiedUser) {
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
    );
  }

  void _notifyReconnectionFailure() {
    clearNotification(2);
    createNotification(
      notificationId: 2,
      title: 'Connection Issue 🚨',
      body: 'Unable to connect to the transcript service.'
          ' Please restart the app or contact support if the problem persists.',
    );
  } // TODO: should trigger a connection restored? as with internet?

  void _notifyInternetLost() {
    clearNotification(3);
    createNotification(
      notificationId: 3,
      title: 'Internet Connection Lost',
      body: 'Your device is offline. Transcription is paused until connection is restored.',
    );
  }

  void _notifyInternetRestored() {
    clearNotification(3);
    createNotification(
      notificationId: 3,
      title: 'Internet Connection Restored',
      body: 'Your device is back online. Transcription will resume shortly.',
    );
  }

  void closeWebSocket() {
    websocketChannel?.sink.close(1000);
    _reconnectionTimer?.cancel();
    _internetListener.cancel();
  }
}
