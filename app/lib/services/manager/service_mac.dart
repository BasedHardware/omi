import 'dart:async';

import 'package:flutter/rendering.dart';
import 'package:flutter_background_service/flutter_background_service.dart';
import 'package:friend_private/services/manager/types.dart';

class BackgroundIsoLateService implements BaseBackgroundService {
  final StreamController<Map<String, dynamic>> _eventController = StreamController<Map<String, dynamic>>.broadcast();

  var serviceStatus = false;
  late Future Function(BackgroundIsoLateService service)? onStartCallback;

  void startService() {
    serviceStatus = true;
    if (onStartCallback != null) {
      onStartCallback!(this);
    }
  }

  void stopService() {
    print("Stopping service");
    serviceStatus = false;
    _eventController.close();
  }

  bool isRunning() {
    debugPrint("Current Status of mac-service is $serviceStatus");
    return serviceStatus;
  }

  Stream<Map<String, dynamic>> on(String method) {
    debugPrint("Called on method $method");
    return _eventController.stream.where((event) {
      print('on $event');
      return event['event'] == method;
    });
  }

  void invoke(String event, [Map<String, dynamic>? data]) {
    if (!serviceStatus) {
      return;
    }
    var eventData = data ?? {};
    eventData['event'] = event;
    debugPrint("Called invoke method $event");
    _eventController.sink.add(eventData); // Use 'data' consistently
  }

  @override
  Future<void> configure(
      {AndroidConfiguration? androidConfiguration, IosConfiguration? iosConfiguration, dynamic macConfig}) async {
    if (macConfig?.onStart != null) {
      onStartCallback = macConfig!.onStart!;
    }
  }
}
