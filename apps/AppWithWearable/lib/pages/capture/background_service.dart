import 'dart:async';
import 'dart:io';
import 'dart:ui';
import 'package:flutter/material.dart';
import 'package:flutter_background_service/flutter_background_service.dart';
import 'package:friend_private/utils/notifications.dart';
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

Future<void> initializeBackgroundService() async {
  final service = FlutterBackgroundService();
  createNotification(
    title: 'Friend is listening in the background',
    body: 'Friend is listening and transcribing your conversations in the background',
  );
  await service.configure(
    iosConfiguration: IosConfiguration(
      autoStart: true,
      onForeground: onStart,
      onBackground: onIosBackground,
    ),
    androidConfiguration: AndroidConfiguration(
      autoStart: true,
      onStart: onStart,
      isForegroundMode: true,
      autoStartOnBoot: true,
    ),
  );
}

@pragma('vm:entry-point')
Future<bool> onIosBackground(ServiceInstance service) async {
  WidgetsFlutterBinding.ensureInitialized();
  DartPluginRegistrant.ensureInitialized();

  return true;
}

@pragma('vm:entry-point')
void onStart(ServiceInstance service) async {
  WidgetsFlutterBinding.ensureInitialized();
  final record = AudioRecorder();

  var path = await getApplicationDocumentsDirectory();
  int count = 0;
  int deleteCount = -1;
  var filePath = '${path.path}/recording_$count.aac';
  // get number of files in directory
  // delete all previous recordings
  var dir = Directory(path.path);
  var files = dir.listSync();
  for (var file in files) {
    if (file is File) {
      if (file.path.contains('recording_')) {
        deleteCount++;
        debugPrint("deleting file $deleteCount");
        file.delete();
      }
    }
  }
  service.invoke("stateUpdate", {"state": 'recording'});
  await record.start(const RecordConfig(), path: filePath);
  Timer.periodic(const Duration(seconds: 30), (timer) async {
    var res = await record.stop();
    var f = File(res!);
    if (f.existsSync()) {
      service.invoke("update", {"path": f.path, "bytes": f.readAsBytesSync()});
      count++;
      filePath = '${path.path}/recording_$count.aac';
      record.start(const RecordConfig(), path: filePath);
    } else {
      debugPrint("file does not exist");
    }
  });
  service.on("stop").listen((event) {
    service.stopSelf();
    debugPrint("background process is now stopped");
  });
}
