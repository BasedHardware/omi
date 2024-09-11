import 'dart:async';
import 'dart:typed_data';

import 'package:flutter/widgets.dart';
import 'package:flutter_background_service/flutter_background_service.dart';
import 'package:flutter_sound/flutter_sound.dart';

void startBackgroundService() {
  final service = FlutterBackgroundService();
  service.startService();
}

void stopBackgroundService() {
  final service = FlutterBackgroundService();
  service.invoke("stop");
}

Future<void> initializeMicBackgroundService() async {
  final service = FlutterBackgroundService();

  await service.configure(
    iosConfiguration: IosConfiguration(
      autoStart: false,
      onForeground: onStart,
      onBackground: onIosBackground,
    ),
    androidConfiguration: AndroidConfiguration(
      autoStart: true,
      onStart: onStart,
      isForegroundMode: true,
      autoStartOnBoot: true,
      foregroundServiceType: AndroidForegroundType.microphone,
    ),
  );
}

@pragma('vm:entry-point')
Future<bool> onIosBackground(ServiceInstance service) async {
  WidgetsFlutterBinding.ensureInitialized();

  return true;
}

@pragma('vm:entry-point')
Future onStart(ServiceInstance service) async {
  FlutterSoundRecorder? _mRecorder = FlutterSoundRecorder();
  await _mRecorder.openRecorder(isBGService: true);
  var recordingDataController = StreamController<Uint8List>();

  await _mRecorder.startRecorder(
    toStream: recordingDataController.sink,
    codec: Codec.pcm16,
    numChannels: 1,
    sampleRate: 16000,
    bufferSize: 8192,
  );
  service.invoke("stateUpdate", {"state": 'recording'});
  recordingDataController.stream.listen((buffer) {
    Uint8List audioBytes = buffer;
    List<dynamic> audioBytesList = audioBytes.toList();
    service.invoke("audioBytes", {"data": audioBytesList});
  });

  service.on('stop').listen((event) {
    _mRecorder.stopRecorder();
    service.invoke("stateUpdate", {"state": 'stopped'});
    service.stopSelf();
  });
}
