import 'dart:async';
import 'dart:io';
import 'dart:typed_data';
import 'package:flutter/material.dart';
import 'package:flutter_background_service/flutter_background_service.dart';
import 'package:friend_private/backend/preferences.dart';
import 'package:friend_private/utils/other/notifications.dart';
import 'package:path_provider/path_provider.dart';
import 'package:record/record.dart';

void startBackgroundService() {
  final service = FlutterBackgroundService();
  service.startService();
}

void stopBackgroundService() {
  final service = FlutterBackgroundService();
  service.invoke("stop");
}

Future<void> initializeBackgroundService({bool isStream = false}) async {
  final service = FlutterBackgroundService();
  createNotification(
    title: 'Friend is listening in the background',
    body: 'Friend is listening and transcribing your conversations in the background',
  );

  await service.configure(
    iosConfiguration: IosConfiguration(
      autoStart: true,
      onForeground: (service) {
        onStart(service, isStream);
      },
    ),
    androidConfiguration: AndroidConfiguration(
      autoStart: true,
      onStart: (service) {
        onStart(service, isStream);
      },
      isForegroundMode: true,
      autoStartOnBoot: true,
      notificationChannelId: 'channel',
    ),
  );
  await service.startService();
}

@pragma('vm:entry-point')
void onStart(ServiceInstance service, bool isStream) async {
  if (isStream) {
    await streamRecording(service);
  } else {
    if (service is AndroidServiceInstance) {
      if (await service.isForegroundService()) {
        service.setForegroundNotificationInfo(
          title: 'Friend is running in background',
          content: 'Friend is listening and transcribing your conversations in the background',
        );
      }
    }
    int count = 0;
    await SharedPreferencesUtil.init();
    var record = AudioRecorder();
    var path = await getApplicationDocumentsDirectory();
    var files = Directory(path.path).listSync();
    for (var file in files) {
      if (file.path.contains('recording_') && !file.path.contains('recording_0')) {
        debugPrint('deleting file: ${file.path}');
        file.deleteSync();
      }
    }
    var filePath = '${path.path}/recording_$count.wav';
    service.invoke("stateUpdate", {"state": 'recording'});
    await record.start(const RecordConfig(encoder: AudioEncoder.wav), path: filePath);
    // timerUpdate is only invoked on Android
    service.on("timerUpdate").listen((event) async {
      if (event!["time"] == '0') {
        if (await record.isRecording()) {
          await record.stop();
          await record.dispose();
        }

        debugPrint("recording stopped");
      }
      if (event["time"] == '30') {
        var paths = SharedPreferencesUtil().recordingPaths;
        SharedPreferencesUtil().recordingPaths = [...paths, filePath];
        count++;
        filePath = '${path.path}/recording_$count.wav';
        record = AudioRecorder();
        await record.start(const RecordConfig(encoder: AudioEncoder.wav), path: filePath);
        debugPrint("recording started again file: $filePath");
      }
    });
    service.on("stop").listen((event) async {
      await record.stop();
      await record.dispose();
      await service.stopSelf();
      debugPrint("background process is now stopped");
    });
  }
}

Future streamRecording(ServiceInstance service) async {
  var record = AudioRecorder();
  var path = await getApplicationDocumentsDirectory();
  int count = 0;
  var filePath = '${path.path}/recording_$count.m4a';
  service.invoke("stateUpdate", {"state": 'recording'});
  var stream = await record.startStream(const RecordConfig(encoder: AudioEncoder.pcm16bits));
  var audioData = <int>[];
  var file = File(filePath);
  stream.listen((data) async {
    audioData.addAll(data);
    print(
      record.convertBytesToInt16(Uint8List.fromList(data)),
    );
    file.writeAsBytesSync(data, mode: FileMode.append);
  });
  service.on("stop").listen((event) async {
    await record.stop();
    await record.dispose();
    await service.stopSelf();
    debugPrint("background process is now stopped");
  });
}
