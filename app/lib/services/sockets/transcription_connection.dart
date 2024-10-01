import 'dart:async';
import 'dart:convert';
import 'dart:io';
import 'dart:math';

import 'package:flutter/material.dart';
import 'package:friend_private/backend/preferences.dart';
import 'package:friend_private/backend/schema/message_event.dart';
import 'package:friend_private/backend/schema/bt_device/bt_device.dart';
import 'package:friend_private/backend/schema/transcript_segment.dart';
import 'package:friend_private/env/env.dart';
import 'package:friend_private/services/notifications.dart';
import 'package:instabug_flutter/instabug_flutter.dart';
import 'package:internet_connection_checker_plus/internet_connection_checker_plus.dart';
import 'package:web_socket_channel/io.dart';
import 'package:web_socket_channel/status.dart' as socket_channel_status;
import 'package:web_socket_channel/web_socket_channel.dart';

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
    _listener?.onConnected();
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
  void send(message) {
    _channel?.sink.add(message);
  }

  void _reconnect() async {
    debugPrint("[Socket] reconnect...${_retries + 1}...");
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

abstract interface class ITransctipSegmentSocketServiceListener {
  void onMessageEventReceived(ServerMessageEvent event);
  void onSegmentReceived(List<TranscriptSegment> segments);
  void onError(Object err);
  void onConnected();
  void onClosed();
}

class SpeechProfileTranscriptSegmentSocketService extends TranscripSegmentSocketService {
  SpeechProfileTranscriptSegmentSocketService.create(super.sampleRate, super.codec)
      : super.create(includeSpeechProfile: false, newMemoryWatch: false);
}

class MemoryTranscripSegmentSocketService extends TranscripSegmentSocketService {
  MemoryTranscripSegmentSocketService.create(super.sampleRate, super.codec)
      : super.create(includeSpeechProfile: true, newMemoryWatch: true);
}

enum SocketServiceState {
  connected,
  disconnected,
}

class TranscripSegmentSocketService implements IPureSocketListener {
  late PureSocket _socket;
  final Map<Object, ITransctipSegmentSocketServiceListener> _listeners = {};

  SocketServiceState get state =>
      _socket.status == PureSocketStatus.connected ? SocketServiceState.connected : SocketServiceState.disconnected;

  int sampleRate;
  BleAudioCodec codec;
  bool includeSpeechProfile;
  bool newMemoryWatch;

  TranscripSegmentSocketService.create(
    this.sampleRate,
    this.codec, {
    this.includeSpeechProfile = false,
    this.newMemoryWatch = true,
  }) {
    final recordingsLanguage = SharedPreferencesUtil().recordingsLanguage;
    var params = '?language=$recordingsLanguage&sample_rate=$sampleRate&codec=$codec&uid=${SharedPreferencesUtil().uid}'
        '&include_speech_profile=$includeSpeechProfile&new_memory_watch=$newMemoryWatch&stt_service=${SharedPreferencesUtil().transcriptionModel}';
    String url = '${Env.apiBaseUrl!.replaceAll('https', 'wss')}listen$params';

    _socket = PureSocket(url);
    _socket.setListener(this);
  }

  void subscribe(Object context, ITransctipSegmentSocketServiceListener listener) {
    _listeners.remove(context.hashCode);
    _listeners.putIfAbsent(context.hashCode, () => listener);
  }

  void unsubscribe(Object context) {
    _listeners.remove(context.hashCode);
  }

  Future start() async {
    bool ok = await _socket.connect();
    if (!ok) {
      debugPrint("Can not connect to websocket");
    }
  }

  Future stop({String? reason}) async {
    await _socket.stop();
    _listeners.clear();

    if (reason != null) {
      debugPrint(reason);
    }
  }

  Future send(dynamic message) async {
    _socket.send(message);
    return;
  }

  @override
  void onClosed() {
    _listeners.forEach((k, v) {
      v.onClosed();
    });
  }

  @override
  void onError(Object err, StackTrace trace) {
    _listeners.forEach((k, v) {
      v.onError(err);
    });
  }

  @override
  void onMessage(event) {
    if (event == 'ping') return;

    // Decode json
    dynamic jsonEvent;
    try {
      jsonEvent = jsonDecode(event);
    } on FormatException catch (e) {
      debugPrint(e.toString());
    }
    if (jsonEvent == null) {
      debugPrint("Can not decode message event json $event");
      return;
    }

    // Transcript segments
    if (jsonEvent is List) {
      var segments = jsonEvent;
      if (segments.isEmpty) {
        return;
      }
      _listeners.forEach((k, v) {
        v.onSegmentReceived(segments.map((e) => TranscriptSegment.fromJson(e)).toList());
      });
      return;
    }

    // Message event
    if (jsonEvent.containsKey("type")) {
      var event = ServerMessageEvent.fromJson(jsonEvent);
      _listeners.forEach((k, v) {
        v.onMessageEventReceived(event);
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

  @override
  void onConnected() {
    _listeners.forEach((k, v) {
      v.onConnected();
    });
  }
}
