import 'dart:async';
import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:friend_private/backend/preferences.dart';
import 'package:friend_private/backend/schema/message_event.dart';
import 'package:friend_private/env/env.dart';
import 'package:instabug_flutter/instabug_flutter.dart';
import 'package:web_socket_channel/io.dart';

enum WebsocketConnectionStatus { notConnected, connected, failed, closed, error }



// TODO: Implement from pure socket
class SdCardSocketService {

    IOWebSocketChannel? sdCardChannel;
    WebsocketConnectionStatus sdCardConnectionState = WebsocketConnectionStatus.notConnected;
    Timer? _reconnectionTimer;
    SdCardSocketService();

Future<void> setupSdCardWebSocket({required Function onMessageReceived, String? btConnectedTime}) async {
    //    IOWebSocketChannel? sdCardChannel;
       try {
       sdCardChannel = await openSdCardStream(
           onMessageReceived: onMessageReceived,
           onWebsocketConnectionSuccess: () {
           sdCardConnectionState = WebsocketConnectionStatus.connected;
           debugPrint('WebSocket connected successfully sd');
        //    notifyListeners();
         },
         onWebsocketConnectionFailed: (err) {
           sdCardConnectionState = WebsocketConnectionStatus.failed;
           //reconnectSdCardWebSocket(onMessageReceived: onMessageReceived);
           debugPrint('WebSocket connection failed sd: $err');
        //    notifyListeners();
         },
         onWebsocketConnectionClosed: (int? closeCode, String? closeReason) {
           sdCardConnectionState = WebsocketConnectionStatus.closed;
        //    //reconnectSdCardWebSocket(onMessageReceived: onMessageReceived);
           debugPrint('WebSocket connection closed2 sd: code ~ $closeCode, reason ~ $closeReason');
        //    notifyListeners();
         },
         onWebsocketConnectionError: (err) {
           sdCardConnectionState = WebsocketConnectionStatus.error;
           //reconnectSdCardWebSocket(onMessageReceived: onMessageReceived);
           debugPrint('WebSocket connection error sd: $err');
        //    notifyListeners();
         },
         btConnectedTime: btConnectedTime,
       );
     } catch (e) {
       debugPrint('Error in initWebSocket sd: $e');
       
    //    notifyListeners();
     }
    
   }

 Future<void> attemptReconnection({required Function onMessageReceived, String? btConnectedTime})async {
    _reconnectionTimer?.cancel();
    debugPrint('Attempting reconnection');
    _reconnectionTimer = Timer(Duration(seconds:5), () {
      setupSdCardWebSocket(
        onMessageReceived: onMessageReceived,
         btConnectedTime: btConnectedTime,
      );
    });
 }

Future<IOWebSocketChannel?> openSdCardStream({
  required VoidCallback onWebsocketConnectionSuccess,
  required void Function(dynamic) onWebsocketConnectionFailed,
  required void Function(int?, String?) onWebsocketConnectionClosed,
  required void Function(dynamic) onWebsocketConnectionError,
  required Function onMessageReceived,
  String? btConnectedTime,
}) async {
  debugPrint('Websocket Opening sd card');
  final recordingsLanguage = SharedPreferencesUtil().recordingsLanguage;
  // var params = '?language=$recordingsLanguage&sample_rate=$sampleRate&codec=$codec&uid=${SharedPreferencesUtil().uid}'
  //     '&include_speech_profile=$includeSpeechProfile&new_memory_watch=$newMemoryWatch&stt_service=${SharedPreferencesUtil().transcriptionModel}';
  var params = '?uid=${SharedPreferencesUtil().uid}&bt_connected_time=$btConnectedTime';
  debugPrint('btConnectedTime: $btConnectedTime');
  IOWebSocketChannel channel = IOWebSocketChannel.connect(
    Uri.parse('${Env.apiBaseUrl!.replaceAll('https', 'wss')}sdcard_stream$params'),
    // headers: {'Authorization': await getAuthHeader()},
  );

  await channel.ready.then((v) {
    channel.stream.listen(
      (event) {
        debugPrint('sdcard stream event');
        if (event == 'ping') return;

        final jsonEvent = jsonDecode(event);

        // segment
        if (jsonEvent is List) {
          var segments = jsonEvent;
          if (segments.isEmpty) return;
          // onMessageReceived(segments.map((e) => TranscriptSegment.fromJson(e)).toList());
          return;
        }

        // debugPrint(event);

        // object message event
        if (jsonEvent.containsKey("type")) {
          var messageEvent = ServerMessageEvent.fromJson(jsonEvent);
          onMessageReceived();
          // if (onMessageEventReceived != null) {
          //   // onMessageEventReceived(messageEvent);
          //   return;
          // }
        }

        debugPrint(event.toString());
      },
      onError: (err, stackTrace) {
        onWebsocketConnectionError(err); // error during connection
        CrashReporting.reportHandledCrash(err!, stackTrace, level: NonFatalExceptionLevel.warning);
      },
      onDone: (() {
        debugPrint('Websocket connection onDone sd'); // FIXME
        onWebsocketConnectionClosed(channel.closeCode, channel.closeReason);
      }),
      cancelOnError: true, // TODO: is this correct?
    );
  }).onError((err, stackTrace) {
    // no closing reason or code
    print(err);
    debugPrint('Websocket connection failed sd: $err');
    CrashReporting.reportHandledCrash(err!, stackTrace, level: NonFatalExceptionLevel.warning);
    onWebsocketConnectionFailed(err); // initial connection failed
  });

  try {
    await channel.ready;
    debugPrint('Websocket Opened in sd card');
    onWebsocketConnectionSuccess();
  } catch (err) {
    print(err);
  }
  return channel;
}

}
