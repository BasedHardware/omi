import 'dart:async';
import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:friend_private/backend/preferences.dart';
import 'package:friend_private/backend/schema/message_event.dart';
import 'package:friend_private/env/env.dart';
import 'package:friend_private/services/sockets/pure_socket.dart';
import 'package:friend_private/services/sockets/transcription_connection.dart';

abstract interface class IWalSocketServiceListener {
  void onMessageEventReceived(ServerMessageEvent event);

  void onError(Object err);

  void onConnected();

  void onClosed();
}

class WalSocketService implements IPureSocketListener {
  late PureSocket _socket;
  final Map<Object, IWalSocketServiceListener> _listeners = {};

  SocketServiceState get state =>
      _socket.status == PureSocketStatus.connected ? SocketServiceState.connected : SocketServiceState.disconnected;

  List<String> fileNames;

  WalSocketService.create(
    this.fileNames,
  ) {
    final recordingsLanguage = SharedPreferencesUtil().recordingsLanguage;
    var params = '?language=$recordingsLanguage&uid=${SharedPreferencesUtil().uid}&file_names=${fileNames.join(",")}';
    String url = '${Env.apiBaseUrl!.replaceAll('https', 'wss')}v2/listen/backward$params';

    _socket = PureSocket(url);
    _socket.setListener(this);
  }

  void subscribe(Object context, IWalSocketServiceListener listener) {
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

    /*
    // Send notification
    NotificationService.instance.clearNotification(3);
    NotificationService.instance.createNotification(
      notificationId: 3,
      title: 'Internet Connection Lost',
      body: 'Your device is offline. Transcription is paused until connection is restored.',
    );
		*/
  }

  @override
  void onMaxRetriesReach() {
    debugPrint("onMaxRetriesReach");

    /*
    // Send notification
    NotificationService.instance.clearNotification(2);
    NotificationService.instance.createNotification(
      notificationId: 2,
      title: 'Connection Issue 🚨',
      body: 'Unable to connect to the transcript service.'
          ' Please restart the app or contact support if the problem persists.',
    );
		*/
  }

  @override
  void onConnected() {
    _listeners.forEach((k, v) {
      v.onConnected();
    });
  }
}
