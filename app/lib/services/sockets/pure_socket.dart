import 'dart:async';
import 'dart:io';
import 'dart:math';

import 'package:flutter/material.dart';
import 'package:instabug_flutter/instabug_flutter.dart';
import 'package:internet_connection_checker_plus/internet_connection_checker_plus.dart';
import 'package:web_socket_channel/io.dart';
import 'package:web_socket_channel/status.dart' as socket_channel_status;
import 'package:web_socket_channel/web_socket_channel.dart';
import 'package:friend_private/backend/http/shared.dart';

enum PureSocketStatus { notConnected, connecting, connected, disconnected }

abstract class IPureSocketListener {
  void onConnected();
  void onMessage(dynamic message);
  void onClosed();
  void onError(Object err, StackTrace trace);

  void onInternetConnectionFailed() {}

  void onMaxRetriesReach() {}
}

abstract class IPureSocket {
  Future<bool> connect();
  Future disconnect();
  void send(dynamic message);

  void onInternetSatusChanged(InternetStatus status);

  void onMessage(dynamic message);
  void onConnected();
  void onClosed();
  void onError(Object err, StackTrace trace);
}

class PureSocketMessage {
  String? raw;
}

class PureCore {
  late InternetConnection internetConnection;

  factory PureCore() => _instance;

  /// The singleton instance of [PureCore].
  static final _instance = PureCore.createInstance();

  PureCore.createInstance() {
    internetConnection = InternetConnection.createInstance(
        /*
      customCheckOptions: [
        InternetCheckOption(
          uri: Uri.parse(Env.apiBaseUrl!),
          timeout: const Duration(
            seconds: 30,
          ),
          responseStatusFn: (resp) {
            return resp.statusCode < 500;
          },
        ),
      ],
		*/
        );
  }
}

class PureSocket implements IPureSocket {
  StreamSubscription<InternetStatus>? _internetStatusListener;
  InternetStatus? _internetStatus;
  Timer? _internetLostDelayTimer;

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
    _internetStatusListener = PureCore().internetConnection.onStatusChange.listen((InternetStatus status) {
      onInternetSatusChanged(status);
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
    if (_status == PureSocketStatus.connecting || _status == PureSocketStatus.connected) {
      return false;
    }

    _channel = IOWebSocketChannel.connect(
      url,
      headers: {
        'Authorization': await getAuthHeader(),
      },
      pingInterval: const Duration(seconds: 10),
      connectTimeout: const Duration(seconds: 30),
    );
    if (_channel?.ready == null) {
      return false;
    }

    _status = PureSocketStatus.connecting;
    dynamic err;
    try {
      await channel.ready;
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
        that.onMessage(message);
      },
      onError: (err, trace) {
        that.onError(err, trace);
      },
      onDone: () {
        that.onClosed();
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
    onClosed();
  }

  Future _cleanUp() async {
    _internetLostDelayTimer?.cancel();
    _internetStatusListener?.cancel();
  }

  Future stop() async {
    await disconnect();
    await _cleanUp();
  }

  @override
  void onClosed() {
    _status = PureSocketStatus.disconnected;
    debugPrint("Socket closed");
    _listener?.onClosed();
  }

  @override
  void onError(Object err, StackTrace trace) {
    _status = PureSocketStatus.disconnected;
    print("Error: ${err}");
    debugPrintStack(stackTrace: trace);

    _listener?.onError(err, trace);

    CrashReporting.reportHandledCrash(err, trace, level: NonFatalExceptionLevel.error);
  }

  @override
  void onMessage(dynamic message) {
    debugPrint("[Socket] Message $message");
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
    _retries++;
    if (_retries > maxRetries) {
      debugPrint("[Socket] Reach max retries $maxRetries");
      _listener?.onMaxRetriesReach();
      return;
    }
    _reconnect();
  }

  @override
  void onInternetSatusChanged(InternetStatus status) {
    debugPrint("[Socket] Internet connection changed $status socket $_status");
    _internetStatus = status;
    switch (status) {
      case InternetStatus.connected:
        if (_status == PureSocketStatus.connected || _status == PureSocketStatus.connecting) {
          return;
        }
        _reconnect();
        break;
      case InternetStatus.disconnected:
        var that = this;
        _internetLostDelayTimer?.cancel();
        _internetLostDelayTimer = Timer(const Duration(seconds: 60), () async {
          if (_internetStatus != InternetStatus.disconnected) {
            return;
          }

          await that.disconnect();
          _listener?.onInternetConnectionFailed();
        });

        break;
    }
  }
}
