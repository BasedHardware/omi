import 'dart:io';

import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/bt_device/bt_device.dart';
import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/services/wals/local_wal_sync.dart';
import 'package:omi/services/wals/sync_rate_limiter.dart';
import 'package:omi/services/wals/wal.dart';
import 'package:omi/services/wals/wal_interfaces.dart';
import 'package:omi/utils/wal_file_manager.dart';

/// A server job that fails on the audio itself (`sync_invalid_audio` /
/// `stt_invalid_input`) reaches the same verdict for the same bytes every time.
///
/// The reconciler used to answer that by spending the auto-retry budget and
/// leaving the recording `miss`, which renders as "Failed — tap Retry". Every
/// tap then re-uploaded, re-earned the verdict and re-spent the budget, so the
/// row and the "needs attention" banner were permanent with no way out but an
/// unlabelled swipe. These tests pin the terminal outcome instead.

class _Listener implements IWalSyncListener {
  @override
  void onWalUpdated() {}

  @override
  void onWalSynced(Wal wal, {ServerConversation? conversation}) {}
}

void main() {
  late Directory tempDir;

  SyncJobStatusResponse failedJob({required String reasonCode, int totalSegments = 1}) => SyncJobStatusResponse(
        jobId: 'job-1',
        status: 'failed',
        totalSegments: totalSegments,
        processedSegments: totalSegments,
        failedSegments: totalSegments,
        reasonCode: reasonCode,
      );

  Wal uploadedWal({int timerStart = 1700000000}) => Wal(
        timerStart: timerStart,
        codec: BleAudioCodec.opus,
        seconds: 31,
        status: WalStatus.uploaded,
        storage: WalStorage.disk,
        device: 'omi',
        filePath: 'audio_$timerStart.bin',
      )..jobId = 'job-1';

  LocalWalSyncImpl syncWithVerdict(SyncJobStatusResponse status) => LocalWalSyncImpl(
        _Listener(),
        jobStatusFetcher: (jobId) async => SyncJobFetch(SyncJobFetchOutcome.ok, status),
      );

  setUp(() async {
    TestWidgetsFlutterBinding.ensureInitialized();
    SharedPreferences.setMockInitialValues({});
    await SharedPreferencesUtil.init();
    tempDir = await Directory.systemTemp.createTemp('wal_unsupported_');
    TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger.setMockMethodCallHandler(
      const MethodChannel('plugins.flutter.io/path_provider'),
      (MethodCall call) async {
        if (call.method == 'getApplicationDocumentsDirectory') return tempDir.path;
        return null;
      },
    );
    await WalFileManager.init();
    SyncRateLimiter.instance.clear();
  });

  tearDown(() async {
    TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger.setMockMethodCallHandler(
      const MethodChannel('plugins.flutter.io/path_provider'),
      null,
    );
    SyncRateLimiter.instance.clear();
    if (tempDir.existsSync()) tempDir.deleteSync(recursive: true);
  });

  for (final reasonCode in ['sync_invalid_audio', 'stt_invalid_input']) {
    test('$reasonCode retires the recording instead of re-arming Retry', () async {
      final sync = syncWithVerdict(failedJob(reasonCode: reasonCode));
      sync.testWals = [uploadedWal()];

      await sync.reconcileUploadedWals();

      final wal = sync.testWals.single;
      expect(wal.status, WalStatus.unsupportedAudio);
      expect(wal.syncDisplayState, WalSyncDisplayState.unsupportedAudio);
      expect(
        wal.syncDisplayState,
        isNot(WalSyncDisplayState.failed),
        reason: 'a "tap Retry" row would send the same bytes back for the same verdict',
      );
      expect(isRetryableSyncState(wal.syncDisplayState), isFalse);
      expect(isAutoUploadEligible(wal), isFalse);
      expect(wal.jobId, isNull, reason: 'the job reached a verdict and must not be polled again');
    });
  }

  test('a transient whole-job failure still spends one retry and stays retryable', () async {
    final sync = syncWithVerdict(failedJob(reasonCode: 'sync_vad_failed'));
    sync.testWals = [uploadedWal()];

    await sync.reconcileUploadedWals();

    final wal = sync.testWals.single;
    expect(wal.status, WalStatus.miss, reason: 'only an input-caused verdict is terminal');
    expect(wal.retryCount, 1);
    expect(isAutoUploadEligible(wal), isTrue);
  });

  test('a backend-busy failure is terminal for neither status nor budget', () async {
    final sync = syncWithVerdict(failedJob(reasonCode: 'backfill_capacity', totalSegments: 0));
    sync.testWals = [uploadedWal()];

    await sync.reconcileUploadedWals();

    final wal = sync.testWals.single;
    expect(wal.status, WalStatus.miss);
    expect(wal.retryCount, 0, reason: 'capacity limits are the server being busy, not bad audio');
  });

  test('every WAL sharing the rejected job is retired together', () async {
    final sync = syncWithVerdict(failedJob(reasonCode: 'sync_invalid_audio', totalSegments: 2));
    sync.testWals = [uploadedWal(timerStart: 1700000000), uploadedWal(timerStart: 1700000100)];

    await sync.reconcileUploadedWals();

    expect(sync.testWals.map((w) => w.status), everyElement(WalStatus.unsupportedAudio));
  });
}
