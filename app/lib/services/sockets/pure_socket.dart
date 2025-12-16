import 'dart:async';
import 'dart:io';
import 'dart:math';

import 'package:flutter/material.dart';
import 'package:web_socket_channel/io.dart';
import 'package:web_socket_channel/status.dart' as socket_channel_status;
import 'package:web_socket_channel/web_socket_channel.dart';
import 'package:omi/backend/http/shared.dart';
import 'package:omi/services/connectivity_service.dart';
import 'package:omi/utils/debug_log_manager.dart';
import 'package:omi/utils/platform/platform_manager.dart';

enum PureSocketStatus { notConnected, connecting, connected, disconnected }

abstract class IPureSocketListener {
  void onConnected();
  void onMessage(dynamic message);
  void onClosed([int? closeCode]);
  void onError(Object err, StackTrace trace);

  void onInternetConnectionFailed() {}

  void onMaxRetriesReach() {}
}

abstract class IPureSocket {
  PureSocketStatus get status;

  Future<bool> connect();
  Future disconnect();
  Future stop();
  void send(dynamic message);

  void setListener(IPureSocketListener listener);

  void onConnectionStateChanged(bool isConnected);

  void onMessage(dynamic message);
  void onConnected();
  void onClosed();
  void onError(Object err, StackTrace trace);
}

class PureSocketMessage {
  String? raw;
}

class PureSocket implements IPureSocket {
  StreamSubscription<bool>? _connectionStateListener;
  bool _isConnected = ConnectivityService().isConnected;
  Timer? _internetLostDelayTimer;
  bool _stopped = false; // Prevents reconnects after stop() is called

  WebSocketChannel? _channel;
  WebSocketChannel get channel {
    if (_channel == null) {
      throw Exception('Socket is not connected');
    }
    return _channel!;
  }

  PureSocketStatus _status = PureSocketStatus.notConnected;
  PureSocketStatus get status => _status;

  IPureSocketListener? _listener;

  int _retries = 0;

  String url;

  PureSocket(this.url) {
    _connectionStateListener = ConnectivityService().onConnectionChange.listen((bool isConnected) {
      onConnectionStateChanged(isConnected);
    });
  }

  void setListener(IPureSocketListener listener) {
    _listener = listener;
  }

  @override
  Future<bool> connect() async {
    return await _connect();
  }

  Future<bool> _connect() async {
    if (_stopped) {
      debugPrint("[Socket] Connect ignored - socket was stopped");
      return false;
    }
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
    _retries = 0;
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

  Future _cleanUp() async {
    _internetLostDelayTimer?.cancel();
    _connectionStateListener?.cancel();
  }

  Future stop() async {
    _stopped = true; // Prevent any further reconnect attempts
    DebugLogManager.logEvent('pure_socket_stopping', {
      'url': url,
    });
    await disconnect();
    await _cleanUp();
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

  void _reconnect() async {
    if (_stopped) {
      debugPrint("[Socket] Reconnect skipped - socket was stopped");
      DebugLogManager.logEvent('pure_socket_reconnect_skipped_stopped', {
        'url': url,
      });
      return;
    }
    debugPrint("[Socket] reconnect...${_retries + 1}...");
    DebugLogManager.logEvent('pure_socket_reconnect_attempt', {
      'url': url,
      'attempt': _retries + 1,
      'max_retries': 8,
    });
    const int initialBackoffTimeMs = 1000; // 1 second
    const double multiplier = 1.5;
    const int maxRetries = 8;

    if (_status == PureSocketStatus.connecting || _status == PureSocketStatus.connected) {
      debugPrint("[Socket] Can not reconnect, because socket is $_status");
      return;
    }

    await _cleanUp();

    var ok = await _connect();
    if (ok) {
      return;
    }

    // retry
    int waitInMilliseconds = pow(multiplier, _retries).toInt() * initialBackoffTimeMs;
    await Future.delayed(Duration(milliseconds: waitInMilliseconds));

    // Double-check stopped flag after delay
    if (_stopped) {
      debugPrint("[Socket] Reconnect aborted after delay - socket was stopped");
      return;
    }

    _retries++;
    if (_retries > maxRetries) {
      debugPrint("[Socket] Reach max retries $maxRetries");
      DebugLogManager.logWarning('pure_socket_max_retries', {
        'url': url,
        'max_retries': maxRetries,
      });
      _listener?.onMaxRetriesReach();
      return;
    }
    _reconnect();
  }

  @override
  void onConnectionStateChanged(bool isConnected) {
    debugPrint("[Socket] Internet connection changed $isConnected socket $_status");
    DebugLogManager.logEvent('pure_socket_connection_state_changed', {
      'url': url,
      'is_connected': isConnected,
      'socket_status': _status.toString(),
    });
    _isConnected = isConnected;
    if (isConnected) {
      if (_status == PureSocketStatus.connected || _status == PureSocketStatus.connecting) {
        return;
      }
      _reconnect();
    } else {
      var that = this;
      _internetLostDelayTimer?.cancel();
      _internetLostDelayTimer = Timer(const Duration(seconds: 60), () async {
        if (_isConnected) {
          return;
        }

        DebugLogManager.logWarning('pure_socket_internet_lost_timeout', {
          'url': url,
          'timeout_seconds': 60,
        });
        await that.disconnect();
        _listener?.onInternetConnectionFailed();
      });
    }
  }
}
