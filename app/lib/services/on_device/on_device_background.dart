import 'dart:async';
import 'package:firebase_auth/firebase_auth.dart';
import 'package:flutter/services.dart';
import 'package:flutter/widgets.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/services/on_device/on_device_runner.dart';
import 'package:omi/services/on_device/on_device_transcription_controller.dart';
import 'package:omi/services/wals/local_wal_sync.dart';
import 'package:omi/services/wals/wal.dart';
import 'package:omi/services/wals/wal_interfaces.dart';

class _WorkerListener implements IWalSyncListener {
  @override
  void onWalUpdated() {}
  @override
  void onWalSynced(Wal wal, {ServerConversation? conversation}) {}
}

/// Android invokes the main library's retained entry point. No capture service,
/// cloud-audio drain, UI, or second audio store is created by this isolate.
Future<void> runOnDeviceBackground({required Future<void> Function() initialize}) async {
  WidgetsFlutterBinding.ensureInitialized();
  const channel = MethodChannel('com.omi/on_device');
  OnDeviceRunner? runner;
  OnDeviceTranscriptionController? controller;
  StreamSubscription<User?>? auth;
  var succeeded = false;
  try {
    if (await channel.invokeMethod<bool>('shouldStopBackground') == true) return;
    await initialize();
    await SharedPreferencesUtil.init();
    final prefs = SharedPreferencesUtil();
    final uid = prefs.uid;
    if (!prefs.getBool('onDeviceOverflowConfigured') || uid.isEmpty || FirebaseAuth.instance.currentUser?.uid != uid) {
      return;
    }
    final sync = LocalWalSyncImpl(_WorkerListener());
    await sync.loadForOnDeviceWorker();
    controller = OnDeviceTranscriptionController(
        manageNativeCustody: false, readGate: () async => prefs.getBool('onDeviceOverflowConfigured'));
    // This worker is Android-only; Apple's summary capability has no channel here.
    await controller.ensureLoaded();
    await controller.model.refresh();
    runner = OnDeviceRunner(sync: sync, controller: controller, publish: (_) {});
    channel.setMethodCallHandler((call) async {
      if (call.method == 'backgroundExpired') await runner?.cancel();
    });
    auth = FirebaseAuth.instance.authStateChanges().listen((user) {
      if (user?.uid != uid) {
        sync.clearUserData();
        unawaited(runner?.cancel());
      }
    });
    if (await channel.invokeMethod<bool>('shouldStopBackground') == true) return;
    await runner.run();
    succeeded = runner.lastError == null;
  } catch (_) {
    // Native WorkManager owns bounded retry; original audio remains untouched.
  } finally {
    await auth?.cancel();
    runner?.dispose();
    controller?.dispose();
    await channel.invokeMethod<void>('backgroundComplete', {'success': succeeded});
  }
}
