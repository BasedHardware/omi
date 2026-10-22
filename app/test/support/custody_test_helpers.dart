import 'dart:io';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/services/wals/local_wal_sync.dart';
import 'package:omi/services/wals/sync_rate_limiter.dart';
import 'package:omi/services/wals/sync_upload_gate.dart';
import 'package:omi/services/wals/wal.dart';
import 'package:omi/services/wals/wal_interfaces.dart';

class CustodyListener implements IWalSyncListener {
  @override
  void onWalUpdated() {}
  @override
  void onWalSynced(Wal wal, {ServerConversation? conversation}) {}
}

Future<Directory> custodyDirectory() async {
  TestWidgetsFlutterBinding.ensureInitialized();
  SharedPreferences.setMockInitialValues({});
  await SharedPreferencesUtil.init();
  SharedPreferencesUtil().uid = 'owner';
  SyncRateLimiter.instance.clear();
  final dir = await Directory.systemTemp.createTemp('custody_test_');
  await SharedPreferencesUtil().saveString('batchAudioDir', dir.path);
  TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger
      .setMockMethodCallHandler(const MethodChannel('plugins.flutter.io/path_provider'), (_) async => dir.path);
  return dir;
}

Future<LocalWalSyncImpl> custodyLedger(
    {SyncUploadGate? gate,
    DateTime Function()? now,
    Future<void> Function(List<Wal>)? persist,
    Future<SyncJobFetch> Function(String)? fetch}) async {
  final ledger = LocalWalSyncImpl(CustodyListener(),
      uploadGate: gate,
      now: now,
      freeDiskBytes: () async => 4 * 1024 * 1024 * 1024,
      persistWals: persist,
      jobStatusFetcher: fetch);
  await ledger.loadForOnDeviceWorker();
  return ledger;
}
