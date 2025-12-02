import 'dart:async';
import 'dart:io';
import 'dart:math';

import 'package:flutter/material.dart';
import 'package:web_socket_channel/io.dart';
import 'package:web_socket_channel/status.dart' as socket_channel_status;
import 'package:web_socket_channel/web_socket_channel.dart';
import 'package:omi/backend/http/shared.dart';
import 'package:omi/services/connectivity_service.dart';
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
  bool _stopped = false;  // Prevents reconnects after stop() is called

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
    } on SocketException catch (e) {
      err = e;
    } on WebSocketChannelException catch (e) {
      err = e;
    }
    if (err != null) {
      print("Error: $err");
      _status = PureSocketStatus.notConnected;
      return false;
    }
    _status = PureSocketStatus.connected;
    _retries = 0;
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
    if (_status == PureSocketStatus.connected) {
      // Warn: should not use await cause dead end by socket closed.
      _channel?.sink.close(socket_channel_status.normalClosure);
    }
    _status = PureSocketStatus.disconnected;
    debugPrint("disconnect");
    onClosed(_channel?.closeCode);
  }

  Future _cleanUp() async {
    _internetLostDelayTimer?.cancel();
    _connectionStateListener?.cancel();
  }

  Future stop() async {
    _stopped = true;  // Prevent any further reconnect attempts
    await disconnect();
    await _cleanUp();
  }

  @override
  void onClosed([int? closeCode]) {
    _status = PureSocketStatus.disconnected;
    debugPrint("Socket closed with code: $closeCode");
    _listener?.onClosed(closeCode);
  }

  @override
  void onError(Object err, StackTrace trace) {
    _status = PureSocketStatus.disconnected;
    print("Error: ${err}");
    debugPrintStack(stackTrace: trace);

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
      return;
    }
    debugPrint("[Socket] reconnect...${_retries + 1}...");
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
      _listener?.onMaxRetriesReach();
      return;
    }
    _reconnect();
  }

  @override
  void onConnectionStateChanged(bool isConnected) {
    debugPrint("[Socket] Internet connection changed $isConnected socket $_status");
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

        await that.disconnect();
        _listener?.onInternetConnectionFailed();
      });
    }
  }
}
