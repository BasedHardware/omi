import 'dart:async';

import 'package:flutter/rendering.dart';
import 'package:flutter_background_service/flutter_background_service.dart';
import 'package:omi/services/manager/types.dart';

class BackgroundIsoLateService implements BaseBackgroundService {
  final StreamController<Map<String, dynamic>> _eventController = StreamController<Map<String, dynamic>>.broadcast();

  var serviceStatus = false;
  late Future Function(BackgroundIsoLateService service)? onStartCallback;

  @override
  void startService() {
    serviceStatus = true;
    if (onStartCallback != null) {
      onStartCallback!(this);
    }
  }

  @override
  void stopService() {
    debugPrint("Stopping service");
    serviceStatus = false;
    _eventController.close();
  }

  @override
  bool isRunning() {
    return serviceStatus;
  }

  Stream<Map<String, dynamic>> on(String method) {
    return _eventController.stream.where((event) {
      return event['event'] == method;
    });
  }

  @override
  void invoke(String event, [Map<String, dynamic>? data]) {
    if (!serviceStatus) {
      return;
    }
    var eventData = data ?? {};
    eventData['event'] = event;
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
