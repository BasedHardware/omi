import 'dart:async';
import 'dart:io';

import 'package:flutter/material.dart';
import 'package:web_socket_channel/io.dart';
import 'package:web_socket_channel/status.dart' as socket_channel_status;
import 'package:web_socket_channel/web_socket_channel.dart';
import 'package:omi/backend/http/shared.dart';
import 'package:omi/utils/debug_log_manager.dart';
import 'package:omi/utils/platform/platform_manager.dart';

enum PureSocketStatus { notConnected, connecting, connected, disconnected }

abstract class IPureSocketListener {
  void onConnected();
  void onMessage(dynamic message);
  void onClosed([int? closeCode]);
  void onError(Object err, StackTrace trace);
}

abstract class IPureSocket {
  PureSocketStatus get status;

  Future<bool> connect();
  Future disconnect();
  Future stop();
  void send(dynamic message);

  void setListener(IPureSocketListener listener);

  void onMessage(dynamic message);
  void onConnected();
  void onClosed();
  void onError(Object err, StackTrace trace);
}

class PureSocketMessage {
  String? raw;
}

class PureSocket implements IPureSocket {
  WebSocketChannel? _channel;
  WebSocketChannel get channel {
    if (_channel == null) {
      throw Exception('Socket is not connected');
    }
    return _channel!;
  }

  PureSocketStatus _status = PureSocketStatus.notConnected;
  @override
  PureSocketStatus get status => _status;

  IPureSocketListener? _listener;

  String url;

  PureSocket(this.url);

  void setListener(IPureSocketListener listener) {
    _listener = listener;
  }

  @override
  Future<bool> connect() async {
    if (_status == PureSocketStatus.connecting || _status == PureSocketStatus.connected) {
      return false;
    }

    debugPrint("request wss ${url}");
    final headers = await buildHeaders(requireAuthCheck: true);

    _channel = IOWebSocketChannel.connect(
      url,
      headers: headers,
      pingInterval: const Duration(seconds: 20),
      connectTimeout: const Duration(seconds: 15),
    );
    if (_channel?.ready == null) {
      return false;
    }

    _status = PureSocketStatus.connecting;
    dynamic err;
    try {
      await channel.ready;
    } on TimeoutException catch (e) {
      err = e;
      DebugLogManager.logWarning('pure_socket_connect_timeout', {
        'url': url,
        'error': e.toString(),
      });
    } on SocketException catch (e) {
      err = e;
      DebugLogManager.logWarning('pure_socket_connect_socket_error', {
        'url': url,
        'error': e.toString(),
      });
    } on WebSocketChannelException catch (e) {
      err = e;
      DebugLogManager.logWarning('pure_socket_connect_websocket_error', {
        'url': url,
        'error': e.toString(),
      });
    }
    if (err != null) {
      debugPrint("[Socket] Connect error: $err");
      _status = PureSocketStatus.notConnected;
      return false;
    }
    _status = PureSocketStatus.connected;
    DebugLogManager.logEvent('pure_socket_connected', {
      'url': url,
    });
    onConnected();

    final that = this;

    _channel?.stream.listen(
      (message) {
        if (message == "ping") {
          // debugPrint(message);
          // Pong frame added manually https://www.rfc-editor.org/rfc/rfc6455#section-5.5.2
          _channel?.sink.add([0x8A, 0x00]);
          return;
        }
        that.onMessage(message);
      },
      onError: (err, trace) {
        that.onError(err, trace);
      },
      onDone: () {
        debugPrint("onDone with close code: ${_channel?.closeCode}");
        that.onClosed(_channel?.closeCode);
      },
      cancelOnError: true,
    );

    return true;
  }

  @override
  Future disconnect() async {
    DebugLogManager.logEvent('pure_socket_disconnecting', {
      'url': url,
      'current_status': _status.toString(),
    });
    if (_status == PureSocketStatus.connected) {
      // Warn: should not use await cause dead end by socket closed.
      _channel?.sink.close(socket_channel_status.normalClosure);
    }
    _status = PureSocketStatus.disconnected;
    debugPrint("[Socket] disconnect");
    onClosed(_channel?.closeCode);
  }

  @override
  Future stop() async {
    DebugLogManager.logEvent('pure_socket_stopping', {
      'url': url,
    });
    await disconnect();
  }

  @override
  void onClosed([int? closeCode]) {
    _status = PureSocketStatus.disconnected;
    final closeReason = _getCloseCodeReason(closeCode);
    debugPrint("Socket closed with code: $closeCode ($closeReason)");

    DebugLogManager.logEvent('pure_socket_closed', {
      'close_code': closeCode ?? -1,
      'close_reason': closeReason,
      'url': url,
    });

    _listener?.onClosed(closeCode);
  }

  String _getCloseCodeReason(int? code) {
    switch (code) {
      case 1000:
        return 'normal_closure';
      case 1001:
        return 'going_away_os_or_background';
      case 1006:
        return 'abnormal_closure';
      case 1011:
        return 'server_error';
      default:
        return 'unknown';
    }
  }

  @override
  void onError(Object err, StackTrace trace) {
    _status = PureSocketStatus.disconnected;
    debugPrint("[Socket] Error: $err");
    debugPrintStack(stackTrace: trace);

    DebugLogManager.logError(err, trace, 'pure_socket_error', {
      'url': url,
    });

    _listener?.onError(err, trace);
    PlatformManager.instance.crashReporter.reportCrash(err, trace);
  }

  @override
  void onMessage(dynamic message) {
    // debugPrint("[Socket] Message $message");
    _listener?.onMessage(message);
  }

  @override
  void onConnected() {
    _listener?.onConnected();
  }

  @override
  void send(message) {
    _channel?.sink.add(message);
  }
}
