import 'dart:convert';
import 'dart:io';

import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/bt_device/bt_device.dart';
import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/backend/http/api/conversations.dart';
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
  var now = DateTime.utc(2026, 11, 2);
  setUp(() async {
    now = DateTime.utc(2026, 11, 2);
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

  test('real poller enforces the five-minute held hint without audio retries', () async {
    final status = SyncJobStatusResponse.fromJson(jsonDecode(
      File('../backend/tests/fixtures/held_partial_status.json').readAsStringSync(),
    ));
    final poller = SyncJobPoller(clock: () => now);
    var requests = 0;
    Future<SyncJobFetch> fetch(String _) async {
      requests++;
      return SyncJobFetch(SyncJobFetchOutcome.ok, status);
    }

    await poller.fetch(status.jobId, fetch);
    for (var minute = 1; minute <= 4; minute++) {
      now = now.add(const Duration(minutes: 1));
      await poller.fetch(status.jobId, fetch);
    }
    expect(requests, 1);
    now = now.add(const Duration(minutes: 1));
    await poller.fetch(status.jobId, fetch);
    expect(requests, 2);
  });

  test('partial upload retains 14-day-old bytes and never acknowledges after 30 minutes', () async {
    // Shared golden is produced by the backend's real partial projection/status test.
    final status = SyncJobStatusResponse.fromJson(jsonDecode(
      File('../backend/tests/fixtures/held_partial_status.json').readAsStringSync(),
    ));
    expect(status.isTerminal, isFalse);
    expect(syncJobTerminalPolicy(status: status.status, isTerminal: status.isTerminal), SyncJobTerminalPolicy.wait);
    expect(syncJobFailureIsPermanent(status), isFalse);
    final listener = _Listener();
    var polls = 0;
    final sync = LocalWalSyncImpl(listener,
        now: () => now,
        persistWals: (_) async {},
        jobStatusFetcher: (_) async {
          polls++;
          return SyncJobFetch(SyncJobFetchOutcome.ok, status);
        });
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
    expect(wal.status, WalStatus.uploaded);
    expect(wal.jobId, status.jobId);
    expect(wal.retryCount, 0);
    now = now.add(const Duration(minutes: 31));
    await sync.reconcileUploadedWals();
    expect(polls, 2);
    expect(listener.acknowledgements, 0);
    expect(wal.status, WalStatus.uploaded);
    expect(wal.syncedAt, 0);
    expect(await sync.enforceSyncedCopyRetentionForTesting(), 0);
    expect(await file.readAsBytes(), [1, 2, 3, 4, 5]);
    await sync.stop();
  });
}
