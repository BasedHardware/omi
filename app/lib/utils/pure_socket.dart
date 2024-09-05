import 'dart:async';
import 'dart:convert';
import 'dart:math';

import 'package:flutter/material.dart';
import 'package:friend_private/backend/preferences.dart';
import 'package:friend_private/backend/schema/transcript_segment.dart';
import 'package:friend_private/env/env.dart';
import 'package:friend_private/services/notification_service.dart';
import 'package:instabug_flutter/instabug_flutter.dart';
import 'package:internet_connection_checker_plus/internet_connection_checker_plus.dart';
import 'package:web_socket_channel/io.dart';
import 'package:web_socket_channel/status.dart' as status;
import 'package:web_socket_channel/web_socket_channel.dart';

enum PureSocketStatus { notConnected, connecting, connected, disconnected }

abstract class IPureSocketListener {
  void onMessage(dynamic message);
  void onClosed();
  void onError(Object err, StackTrace trace);

  void onInternetConnectionFailed() {}

  void onMaxRetriesReach() {}
}

abstract class IPureSocket {
  Future<bool> connect();
  void disconnect();
  void send(dynamic message);

  void onInternetSatusChanged(InternetStatus status);

  void onMessage(dynamic message);
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
      customCheckOptions: [
        InternetCheckOption(
            uri: Uri.parse(Env.apiBaseUrl!),
            timeout: const Duration(
              seconds: 5,
            )),
      ],
    );
  }
}

class PureSocket implements IPureSocket {
  StreamSubscription<InternetStatus>? _internetStatusListener;
  InternetStatus? _internetStatus;
  Timer? _internetLostDelayTimer;

  WebSocketChannel? _channel;
  PureSocketStatus _status = PureSocketStatus.notConnected;
  IPureSocketListener? _listener;

  int _retries = 0;

  String url;

  PureSocket(this.url) {
    _internetStatusListener = PureCore().internetConnection.onStatusChange.listen((InternetStatus status) {
      onInternetSatusChanged(status);
    });
  }

  WebSocketChannel get channel {
    if (_channel == null) {
      throw Exception('Socket is not connected');
    }
    return _channel!;
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
      pingInterval: const Duration(seconds: 10),
      connectTimeout: const Duration(seconds: 30),
    );
    if (_channel?.ready == null) {
      return false;
    }

    _status = PureSocketStatus.connecting;
    await _channel?.ready;
    _status = PureSocketStatus.connected;
    _retries = 0;

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
  void disconnect() {
    _status = PureSocketStatus.disconnected;
    _cleanUp();
  }

  Future _cleanUp() async {
    _internetLostDelayTimer?.cancel();
    _internetStatusListener?.cancel();
    await _channel?.sink.close(status.goingAway);
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
  void send(message) {
    _channel?.sink.add(message);
  }

  void _reconnect() async {
    const int initialBackoffTimeMs = 1000; // 1 second
    const double multiplier = 1.5;
    const int maxRetries = 7;

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
    if (_retries >= maxRetries) {
      debugPrint("[Socket] Reach max retries $maxRetries");
      _listener?.onMaxRetriesReach();
      return;
    }
    _reconnect();
  }

  @override
  void onInternetSatusChanged(InternetStatus status) {
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
        _internetLostDelayTimer = Timer(const Duration(seconds: 60), () {
          if (_internetStatus != InternetStatus.disconnected) {
            return;
          }

          that.disconnect();
          _listener?.onInternetConnectionFailed();
        });

        break;
    }
  }
}

abstract interface class ITransctipSegmentSocketServiceListener {
  void onSegmentReceived(List<TranscriptSegment> segments);
  void onError(Object err);
}

class TranscripSegmentSocketService implements IPureSocketListener {
  late PureSocket _socket;
  final Map<Object, ITransctipSegmentSocketServiceListener> _listeners = {};

  int sampleRate;
  String codec;
  bool includeSpeechProfile;

  factory TranscripSegmentSocketService() {
    if (_instance == null) {
      throw Exception("TranscripSegmentSocketService is not initiated");
    }

    return _instance!;
  }

  /// The singleton instance of [TranscripSegmentSocketService].
  static TranscripSegmentSocketService? _instance;

  TranscripSegmentSocketService.create(
    this.sampleRate,
    this.codec,
    this.includeSpeechProfile,
  ) {
    final recordingsLanguage = SharedPreferencesUtil().recordingsLanguage;
    var params =
        '?language=$recordingsLanguage&sample_rate=$sampleRate&codec=$codec&uid=${SharedPreferencesUtil().uid}&include_speech_profile=$includeSpeechProfile';
    String url = '${Env.apiBaseUrl!.replaceAll('https', 'wss')}listen$params';

    _socket = PureSocket(url);
    _socket.setListener(this);
  }

  TranscripSegmentSocketService.createInstance(
    this.sampleRate,
    this.codec,
    this.includeSpeechProfile,
  ) {
    _instance = TranscripSegmentSocketService.createInstance(sampleRate, codec, includeSpeechProfile);
  }

  void subscribe(Object context, ITransctipSegmentSocketServiceListener listener) {
    if (_listeners.containsKey(context)) {
      _listeners.remove(context);
    }
    _listeners.putIfAbsent(context, () => listener);
  }

  void unsubscribe(Object context) {
    if (_listeners.containsKey(context)) {
      _listeners.remove(context);
    }
  }

  void start() {
    _socket.connect();
  }

  void stop() {
    _socket.disconnect();
    _listeners.clear();
  }

  @override
  void onClosed() {}

  @override
  void onError(Object err, StackTrace trace) {
    _listeners.forEach((k, v) {
      v.onError(err);
    });
  }

  @override
  void onMessage(event) {
    // ping
    if (event == 'ping') return;

    // segments
    final jsonSegements = jsonDecode(event);
    if (jsonSegements is List) {
      if (jsonSegements.isEmpty) return;
      var segments = jsonSegements.map((e) => TranscriptSegment.fromJson(e)).toList();

      // forward
      _listeners.forEach((k, v) {
        v.onSegmentReceived(segments);
      });
      return;
    }

    debugPrint(event.toString());
  }

  @override
  void onInternetConnectionFailed() {
    debugPrint("onInternetConnectionFailed");

    // Send notification
    NotificationService.instance.clearNotification(3);
    NotificationService.instance.createNotification(
      notificationId: 3,
      title: 'Internet Connection Lost',
      body: 'Your device is offline. Transcription is paused until connection is restored.',
    );
  }

  @override
  void onMaxRetriesReach() {
    debugPrint("onMaxRetriesReach");

    // Send notification
    NotificationService.instance.clearNotification(2);
    NotificationService.instance.createNotification(
      notificationId: 2,
      title: 'Connection Issue 🚨',
      body: 'Unable to connect to the transcript service.'
          ' Please restart the app or contact support if the problem persists.',
    );
  }
}
