import 'dart:convert';
import 'dart:io';

import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/bt_device/bt_device.dart';
import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/services/wals/local_wal_sync.dart';
import 'package:omi/services/wals/sync_job_poller.dart';
import 'package:omi/services/wals/sync_job_policy.dart';
import 'package:omi/services/wals/sync_rate_limiter.dart';
import 'package:omi/services/wals/wal.dart';
import 'package:omi/services/wals/wal_interfaces.dart';
import 'package:omi/utils/wal_file_manager.dart';

class _Listener implements IWalSyncListener {
  int acknowledgements = 0;
  @override
  void onWalUpdated() {}
  @override
  void onWalSynced(Wal wal, {ServerConversation? conversation}) => acknowledgements++;
}

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();
  late Directory dir;
  final now = DateTime.utc(2026, 11, 2);
  setUp(() async {
    SharedPreferences.setMockInitialValues({'autoRemoveSyncedCopies': true, 'autoRemoveSyncedCopiesDays': 1});
    await SharedPreferencesUtil.init();
    SyncRateLimiter.instance.clear();
    SyncJobPoller.instance.resetForTesting(clock: () => now);
    dir = await Directory.systemTemp.createTemp('artifact_missing_custody_');
    TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger.setMockMethodCallHandler(
      const MethodChannel('plugins.flutter.io/path_provider'),
      (call) async => dir.path,
    );
    await WalFileManager.init();
  });
  tearDown(() async {
    SyncRateLimiter.instance.clear();
    SyncJobPoller.instance.resetForTesting();
    TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger.setMockMethodCallHandler(
      const MethodChannel('plugins.flutter.io/path_provider'),
      null,
    );
    await dir.delete(recursive: true);
  });

  test('14-day-old missing-artifact upload never acknowledges or ages out its phone bytes', () async {
    // Shared golden is produced by the backend's real partial projection/status test.
    final status = SyncJobStatusResponse.fromJson(jsonDecode(
      File('../backend/tests/fixtures/batch_artifact_missing_status.json').readAsStringSync(),
    ));
    expect(status.isTerminal, isTrue);
    expect(syncJobTerminalPolicy(status: status.status, isTerminal: status.isTerminal), SyncJobTerminalPolicy.retry);
    expect(syncJobFailureIsPermanent(status), isFalse);
    final listener = _Listener();
    final sync = LocalWalSyncImpl(listener,
        now: () => now,
        persistWals: (_) async {},
        jobStatusFetcher: (_) async => SyncJobFetch(SyncJobFetchOutcome.ok, status));
    final file = await File('${dir.path}/audio_missing.bin').writeAsBytes([1, 2, 3, 4, 5]);
    final wal = Wal(
        timerStart: now.subtract(const Duration(days: 14)).millisecondsSinceEpoch ~/ 1000,
        codec: BleAudioCodec.opus,
        seconds: 31,
        status: WalStatus.uploaded,
        storage: WalStorage.disk,
        device: 'omi',
        filePath: 'audio_missing.bin')
      ..jobId = status.jobId;
    sync.testWals = [wal];
    expect(await sync.enforceSyncedCopyRetentionForTesting(), 0);
    await sync.reconcileUploadedWals();
    expect(listener.acknowledgements, 0);
    expect(wal.status, WalStatus.miss);
    expect(wal.jobId, isNull);
    expect(wal.syncedAt, 0);
    expect(await sync.enforceSyncedCopyRetentionForTesting(), 0);
    expect(await file.readAsBytes(), [1, 2, 3, 4, 5]);
    await sync.stop();
  });
}
