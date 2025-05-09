import 'dart:async';
import 'dart:io';
import 'dart:math';

import 'package:flutter/material.dart';
import 'package:instabug_flutter/instabug_flutter.dart';
import 'package:internet_connection_checker_plus/internet_connection_checker_plus.dart';
import 'package:web_socket_channel/io.dart';
import 'package:web_socket_channel/status.dart' as socket_channel_status;
import 'package:web_socket_channel/web_socket_channel.dart';
import 'package:omi/backend/http/shared.dart';
import 'package:omi/utils/logger.dart';

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
      useDefaultOptions: false,
      customCheckOptions: [
        InternetCheckOption(
          uri: Uri.parse('https://one.one.one.one'),
          timeout: const Duration(seconds: 12),
        ),
        InternetCheckOption(
          uri: Uri.parse('https://icanhazip.com/'),
          timeout: const Duration(seconds: 12),
        ),
        InternetCheckOption(
          uri: Uri.parse('https://jsonplaceholder.typicode.com/todos/1'),
          timeout: const Duration(seconds: 12),
        ),
        InternetCheckOption(
          uri: Uri.parse('https://reqres.in/api/users/1'),
          timeout: const Duration(seconds: 12),
        ),
      ],
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
    Logger.debug('🔌 Socket initializing for URL: $url');
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
    if (_status == PureSocketStatus.connected || _status == PureSocketStatus.connecting) {
      Logger.debug('🔌 Socket already connected or connecting to: $url');
      return true;
    }

    Logger.debug('🔌 Socket attempting to connect to: $url');
    _status = PureSocketStatus.connecting;

    try {
      Map<String, String> headers = {};
      String tokenString = await getAuthHeader();
      headers['Authorization'] = tokenString;

      _channel = IOWebSocketChannel.connect(
        Uri.parse(url),
        headers: headers,
      );

      _channel!.stream.listen(
        (data) => onMessage(data),
        onDone: onClosed,
        onError: onError,
        cancelOnError: true,
      );

      _status = PureSocketStatus.connected;
      onConnected();
      _retries = 0;
      Logger.debug('🔌 Socket successfully connected to: $url');
      return true;
    } catch (e, trace) {
      Logger.debug('🔌 Socket connection failed to: $url - error: $e');
      onError(e, trace);
      return false;
    }
  }

  @override
  Future disconnect() async {
    Logger.debug('🔌 Socket disconnecting from: $url');
    try {
      await _channel?.sink.close(socket_channel_status.normalClosure);
      _status = PureSocketStatus.disconnected;
    } catch (e, trace) {
      debugPrint('Error closing socket: $e');
      CrashReporting.reportHandledCrash(e, trace);
    }
    return;
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
  void send(dynamic message) {
    try {
      Logger.debug('🔌 Socket sending message to: $url');
      channel.sink.add(message);
    } catch (e, trace) {
      debugPrint('Failed to send message: $e');
      CrashReporting.reportHandledCrash(e, trace);
    }
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
