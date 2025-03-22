import 'dart:async';
import 'dart:typed_data';

import 'package:flutter_background_service_platform_interface/flutter_background_service_platform_interface.dart';

enum RecorderServiceStatus {
  initialising,
  recording,
  stop,
}

abstract class IMicRecorderService {
  Future<void> start({
    required Function(Uint8List bytes) onByteReceived,
    Function()? onRecording,
    Function()? onStop,
    Function()? onInitializing,
  });
  void stop();
}

enum BackgroundServiceStatus {
  initiated,
  running,
}

class MacConfiguration<T> {
  final Future Function(T service)? onStart;

  MacConfiguration({
    this.onStart,
  });
}

abstract class BaseBackgroundService implements Observable {
  Future<void> configure(
      {IosConfiguration? iosConfiguration, AndroidConfiguration? androidConfiguration, dynamic macConfig});
  bool isRunning();
  void startService();
  void stopService();
}
