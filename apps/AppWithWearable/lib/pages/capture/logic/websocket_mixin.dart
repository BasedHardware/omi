import 'dart:async';

import 'package:flutter/material.dart';
import 'package:friend_private/backend/database/transcript_segment.dart';
import 'package:friend_private/backend/schema/bt_device.dart';
import 'package:friend_private/utils/audio/wav_bytes.dart';
import 'package:friend_private/utils/ble/communication.dart';
import 'package:friend_private/utils/other/notifications.dart';
import 'package:friend_private/utils/websockets.dart';
import 'package:tuple/tuple.dart';
import 'package:web_socket_channel/io.dart';

mixin WebSocketMixin {
  WebsocketConnectionStatus wsConnectionState = WebsocketConnectionStatus.notConnected;
  bool websocketReconnecting = false;
  IOWebSocketChannel? _wsChannel;
  int _reconnectionAttempts = 0;

  Future<Tuple3<IOWebSocketChannel?, StreamSubscription?, WavBytesUtil>> initWebSocket({
    required Function onConnectionSuccess,
    required Function(dynamic) onConnectionFailed,
    required Function(int?, String?) onConnectionClosed,
    required Function(dynamic) onConnectionError,
    required Function(List<TranscriptSegment>) onMessageReceived,
    required BTDeviceStruct btDevice,
    required BleAudioCodec audioCodec,
  }) async {
    Tuple3<IOWebSocketChannel?, StreamSubscription?, WavBytesUtil> data = await streamingTranscript(
      btDevice: btDevice,
      deviceCodec: audioCodec,
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
        _reconnectWebSocket(
          onConnectionSuccess: onConnectionSuccess,
          onConnectionFailed: onConnectionFailed,
          onConnectionClosed: onConnectionClosed,
          onConnectionError: onConnectionError,
          onMessageReceived: onMessageReceived,
          btDevice: btDevice,
          audioCodec: audioCodec,
        );
      },
      onWebsocketConnectionClosed: (int? closeCode, String? closeReason) {
        wsConnectionState = WebsocketConnectionStatus.closed;
        onConnectionClosed(closeCode, closeReason);
        if (closeCode != 1000) {
          _reconnectWebSocket(
            onConnectionSuccess: onConnectionSuccess,
            onConnectionFailed: onConnectionFailed,
            onConnectionClosed: onConnectionClosed,
            onConnectionError: onConnectionError,
            onMessageReceived: onMessageReceived,
            btDevice: btDevice,
            audioCodec: audioCodec,
          );
        }
      },
      onWebsocketConnectionError: (err) {
        wsConnectionState = WebsocketConnectionStatus.error;
        websocketReconnecting = false;
        onConnectionError(err);
        _reconnectWebSocket(
          onConnectionSuccess: onConnectionSuccess,
          onConnectionFailed: onConnectionFailed,
          onConnectionClosed: onConnectionClosed,
          onConnectionError: onConnectionError,
          onMessageReceived: onMessageReceived,
          btDevice: btDevice,
          audioCodec: audioCodec,
        );
      },
      onMessageReceived: onMessageReceived,
    );

    _wsChannel = data.item1;
    return data;
  }

  //  Future<void> _reconnectWebSocket() async {
  //     // TODO: fix function
  //     // - we are closing so that this triggers a new reconnect, but maybe it shouldn't, as this will trigger error sometimes, and close
  //     //   causing 4 up to 5 reconnect attempts, double notification, double memory creation and so on.
  //     // if (websocketReconnecting) return;
  //
  //     if (_reconnectionAttempts >= 3) {
  //       setState(() => websocketReconnecting = false);
  //       // TODO: reset here to 0? or not, this could cause infinite loop if it's called in parallel from 2 distinct places
  //       debugPrint('Max reconnection attempts reached');
  //       clearNotification(2);
  //       createNotification(
  //         notificationId: 2,
  //         title: 'Error Generating Transcription',
  //         body: 'Check your internet connection and try again. If the problem persists, restart the app.',
  //       );
  //       resetState(restartBytesProcessing: false); // Should trigger this only once, and then disconnects websocket
  //
  //       return;
  //     }
  //     setState(() {
  //       websocketReconnecting = true;
  //     });
  //     _reconnectionAttempts++;
  //     await Future.delayed(const Duration(seconds: 3)); // Reconnect delay
  //     debugPrint('Attempting to reconnect $_reconnectionAttempts time');
  //     // _wsChannel?.
  //     _bleBytesStream?.cancel();
  //     _wsChannel?.sink.close(); // trigger one more reconnectWebSocket call
  //     await initiateBytesStreamingProcessing();
  //   }

  Future<void> _reconnectWebSocket({
    required Function onConnectionSuccess,
    required Function(dynamic) onConnectionFailed,
    required Function(int?, String?) onConnectionClosed,
    required Function(dynamic) onConnectionError,
    required Function(List<TranscriptSegment>) onMessageReceived,
    required BTDeviceStruct btDevice,
    required BleAudioCodec audioCodec,
  }) async {
    if (_reconnectionAttempts >= 3) {
      websocketReconnecting = false;
      debugPrint('Max reconnection attempts reached');
      clearNotification(2);
      createNotification(
        notificationId: 2,
        title: 'Error Generating Transcription',
        body: 'Check your internet connection and try again. If the problem persists, restart the app.',
      );
      return;
    }

    websocketReconnecting = true;
    _reconnectionAttempts++;
    await Future.delayed(const Duration(seconds: 3));
    debugPrint('Attempting to reconnect $_reconnectionAttempts time');
    _wsChannel?.sink.close();
    await initWebSocket(
      onConnectionSuccess: onConnectionSuccess,
      onConnectionFailed: onConnectionFailed,
      onConnectionClosed: onConnectionClosed,
      onConnectionError: onConnectionError,
      onMessageReceived: onMessageReceived,
      btDevice: btDevice,
      audioCodec: audioCodec,
    );
  }

  void closeWebSocket() {
    _wsChannel?.sink.close(1000);
  }
}
