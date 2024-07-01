import 'dart:async';
import 'dart:io';
import 'package:flutter_background_service/flutter_background_service.dart';
import 'package:friend_private/backend/preferences.dart';
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
void onStart(ServiceInstance service) async {
  if (service is AndroidServiceInstance) {
    if (await service.isForegroundService()) {
      print("foreground service is running");
      service.setForegroundNotificationInfo(title: 'foreground update', content: 'idk what to put here');
    }
  }
  var record = AudioRecorder();
  var path = await getApplicationDocumentsDirectory();
  var filePath = '${path.path}/recording.aac';
  service.invoke("stateUpdate", {"state": 'recording'});
  await record.start(const RecordConfig(), path: filePath);
  service.on("stop").listen((event) async {
    await record.stop();
    await record.dispose();
    await service.stopSelf();
    print("background process is now stopped");
  });
}

Future<void> recordingOnIOS(ServiceInstance service) async {
  var record = AudioRecorder();
  var path = await getApplicationDocumentsDirectory();
  var filePath = '${path.path}/recording.aac';
  service.invoke("stateUpdate", {"state": 'recording'});
  await record.start(const RecordConfig(), path: filePath);
  service.on("stop").listen((event) async {
    await record.stop();
    await record.dispose();
    await service.stopSelf();
    print("background process is now stopped");
  });
}

Future<void> recordingOnAndroid(ServiceInstance service) async {
  await SharedPreferencesUtil.init();
  var record = AudioRecorder();
  var path = await getApplicationDocumentsDirectory();
  var filePath = '${path.path}/recording.aac';
  var dir = Directory(path.path);
  var files = dir.listSync();
  for (var file in files) {
    if (file is File) {
      if (file.path.contains('recording')) {
        file.delete();
      }
    }
  }
  service.invoke("stateUpdate", {"state": 'recording'});
  await record.start(const RecordConfig(), path: filePath);
  SharedPreferencesUtil().recordingPath = filePath;
  print("last recording path: ${SharedPreferencesUtil().recordingPath}");
  service.on("stop").listen((event) async {
    var res = await record.stop();
    var f = File(res!);
    service.invoke("stateUpdate", {"state": 'stopped'});
    service.invoke("update", {"path": f.path});
    await record.dispose();
    service.stopSelf();
    print("background process is now stopped");
  });
}
