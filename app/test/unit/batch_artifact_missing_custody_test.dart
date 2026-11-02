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
import 'package:omi/services/wals/sync_upload_batch.dart';
import 'package:omi/services/wals/sync_upload_gate.dart';
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

  test('missing-artifact retry keeps its original bundle when new audio arrives', () async {
    final wire = jsonDecode(File('../backend/tests/fixtures/batch_artifact_missing_status.json').readAsStringSync())
        as Map<String, dynamic>;
    wire['total_files'] = 2;
    final status = SyncJobStatusResponse.fromJson(wire);
    final listener = _Listener();
    final sync = LocalWalSyncImpl(listener,
        now: () => now,
        persistWals: (_) async {},
        jobStatusFetcher: (_) async => SyncJobFetch(SyncJobFetchOutcome.ok, status));
    final old = <Wal>[];
    for (var i = 0; i < 2; i++) {
      final name = 'audio_${1000 + i}.bin';
      await File('${dir.path}/$name').writeAsBytes([1, 2, 3, 4, 5]);
      old.add(Wal(
          timerStart: 1000 + i,
          codec: BleAudioCodec.opus,
          seconds: 10,
          status: WalStatus.uploaded,
          storage: WalStorage.disk,
          device: 'omi',
          filePath: name)
        ..jobId = status.jobId);
    }
    final fresh = Wal(
        timerStart: 1002,
        codec: BleAudioCodec.opus,
        seconds: 10,
        status: WalStatus.miss,
        storage: WalStorage.disk,
        device: 'omi',
        filePath: 'audio_1002.bin');
    sync.testWals = [...old, fresh];
    await sync.reconcileUploadedWals();
    expect(listener.acknowledgements, 0);
    final retry = nextSyncUploadBatch(
        sync.testWals.where((w) => w.status == WalStatus.miss).toList(), now.millisecondsSinceEpoch ~/ 1000);
    expect(retry.map((w) => w.filePath), old.map((w) => w.filePath),
        reason: 'Changing membership changes the server content ID and bypasses the original repair fence');
    final restored = old.map((w) => Wal.fromJson(w.toJson())).toList();
    expect(restored.every((w) => w.repairJobId == status.jobId && w.repairFileCount == 2), isTrue);
    expect(nextSyncUploadBatch([...restored, fresh], now.millisecondsSinceEpoch ~/ 1000).length, 2);
    expect(nextSyncUploadBatch([restored.first, fresh], now.millisecondsSinceEpoch ~/ 1000), [fresh],
        reason: 'A missing member must not become a partial repair or block new recordings');
    restored.last.retryCount = walMaxAutoRetries;
    final eligible = [...restored, fresh].where((w) => isAutoUploadEligible(w)).toList();
    expect(nextSyncUploadBatch(eligible, now.millisecondsSinceEpoch ~/ 1000), [fresh]);
    await sync.stop();
  });

  test('missing repair file sends no subset and preserves the surviving bytes', () async {
    var repairs = 0;
    final normalUploads = <List<String>>[];
    final sync = LocalWalSyncImpl(_Listener(),
        now: () => now,
        persistWals: (_) async {},
        uploadGate: SyncUploadGate(
            limiter: SyncRateLimiter.instance,
            fairUseStatusLoader: () async => {'stage': 'none'},
            uploader: (files,
                {onUploadProgress,
                conversationId,
                captureEvidence,
                recordingSessionId,
                audioStartSeconds,
                audioEndSeconds,
                claimLiveCapture = false,
                geolocation}) async {
              normalUploads.add(files.map((f) => f.uri.pathSegments.last).toList());
              return UploadFilesResult.queued('new-job');
            },
            repairUploader: (files,
                {required repairJobId,
                onUploadProgress,
                conversationId,
                captureEvidence,
                recordingSessionId,
                audioStartSeconds,
                audioEndSeconds,
                claimLiveCapture = false,
                geolocation}) async {
              repairs++;
              return UploadFilesResult.queued(repairJobId);
            }));
    Wal pending(int offset, String name) => Wal(
        timerStart: 1000 + offset,
        codec: BleAudioCodec.opus,
        seconds: 10,
        status: WalStatus.miss,
        storage: WalStorage.disk,
        device: 'omi',
        filePath: name);
    final survivor = pending(0, 'audio_survivor.bin')
      ..repairJobId = 'bp_original'
      ..repairFileCount = 2;
    final missing = pending(1, 'audio_absent.bin')
      ..repairJobId = 'bp_original'
      ..repairFileCount = 2;
    final fresh = pending(2, 'audio_new.bin');
    final bytes = await File('${dir.path}/audio_survivor.bin').writeAsBytes([1, 2, 3, 4, 5]);
    await File('${dir.path}/audio_new.bin').writeAsBytes([1, 2, 3, 4, 5]);
    sync.testWals = [survivor, missing, fresh];
    await sync.syncAll();
    expect(repairs, 0);
    expect(normalUploads, [
      ['audio_new.bin']
    ]);
    expect(survivor.status, WalStatus.miss);
    expect(survivor.repairJobId, 'bp_original');
    expect(await bytes.readAsBytes(), [1, 2, 3, 4, 5]);
    await sync.stop();
  });

  test('synced copies tagged for an incomplete repair never age out', () async {
    final listener = _Listener();
    final sync = LocalWalSyncImpl(listener, now: () => now, persistWals: (_) async {});
    final wal = Wal(
        timerStart: 1000,
        codec: BleAudioCodec.opus,
        seconds: 10,
        status: WalStatus.synced,
        syncedAt: 1001,
        storage: WalStorage.disk,
        device: 'omi',
        filePath: 'audio_held.bin')
      ..repairJobId = 'bp_original'
      ..repairFileCount = 2;
    final file = await File('${dir.path}/audio_held.bin').writeAsBytes([1, 2, 3, 4, 5]);
    sync.testWals = [wal];
    expect(await sync.enforceSyncedCopyRetentionForTesting(), 0);
    expect(await file.exists(), isTrue);
    await sync.stop();
  });

  test('unknown original file count cannot authorize a surviving subset', () async {
    final wire = jsonDecode(File('../backend/tests/fixtures/batch_artifact_missing_status.json').readAsStringSync())
        as Map<String, dynamic>;
    wire.remove('total_files');
    final status = SyncJobStatusResponse.fromJson(wire);
    final sync = LocalWalSyncImpl(_Listener(),
        now: () => now,
        persistWals: (_) async {},
        jobStatusFetcher: (_) async => SyncJobFetch(SyncJobFetchOutcome.ok, status));
    final survivor = Wal(
        timerStart: 1000,
        codec: BleAudioCodec.opus,
        seconds: 10,
        status: WalStatus.uploaded,
        storage: WalStorage.disk,
        device: 'omi',
        filePath: 'audio_old.bin')
      ..jobId = status.jobId;
    final fresh = Wal(
        timerStart: 1001,
        codec: BleAudioCodec.opus,
        seconds: 10,
        status: WalStatus.miss,
        storage: WalStorage.disk,
        device: 'omi',
        filePath: 'audio_new.bin');
    sync.testWals = [survivor, fresh];
    await sync.reconcileUploadedWals();
    expect(survivor.repairJobId, status.jobId);
    expect(survivor.repairFileCount, 0, reason: 'Observed local members do not prove original bundle size');
    expect(
        nextSyncUploadBatch(
            sync.testWals.where((w) => w.status == WalStatus.miss).toList(), now.millisecondsSinceEpoch ~/ 1000),
        [fresh]);
    await sync.stop();
  });

  for (final scenario in [(false, false), (true, false), (false, true)]) {
    final memberMissing = scenario.$1;
    final memberSynced = scenario.$2;
    test('manual retry keeps the entire held repair bundle (missing=$memberMissing, synced=$memberSynced)', () async {
      final listener = _Listener();
      final repairs = <List<String>>[];
      final sync = LocalWalSyncImpl(listener,
          now: () => now,
          persistWals: (_) async {},
          uploadGate: SyncUploadGate(
              limiter: SyncRateLimiter.instance,
              fairUseStatusLoader: () async => {'stage': 'none'},
              uploader: (files,
                  {onUploadProgress,
                  conversationId,
                  captureEvidence,
                  recordingSessionId,
                  audioStartSeconds,
                  audioEndSeconds,
                  claimLiveCapture = false,
                  geolocation}) async {
                fail('Manual repair must not upload unrelated recordings');
              },
              repairUploader: (files,
                  {required repairJobId,
                  onUploadProgress,
                  conversationId,
                  captureEvidence,
                  recordingSessionId,
                  audioStartSeconds,
                  audioEndSeconds,
                  claimLiveCapture = false,
                  geolocation}) async {
                expect(repairJobId, 'bp_original');
                repairs.add(files.map((f) => f.uri.pathSegments.last).toList());
                return UploadFilesResult.queued(repairJobId);
              }));
      final bundle = <Wal>[];
      for (var index = 0; index < 2; index++) {
        final name = 'audio_manual_$index.bin';
        if (!memberMissing || index == 0) await File('${dir.path}/$name').writeAsBytes([1, 2, 3, 4, 5]);
        bundle.add(Wal(
            timerStart: 1000 + index,
            codec: BleAudioCodec.opus,
            seconds: 10,
            status: memberSynced && index == 1 ? WalStatus.synced : WalStatus.miss,
            holdForUser: true,
            storage: WalStorage.disk,
            device: 'omi',
            filePath: name)
          ..repairJobId = 'bp_original'
          ..repairFileCount = 2
          ..retryCount = walMaxAutoRetries);
      }
      final fresh = Wal(
          timerStart: 1002,
          codec: BleAudioCodec.opus,
          seconds: 10,
          status: WalStatus.miss,
          storage: WalStorage.disk,
          device: 'omi',
          filePath: 'audio_unrelated.bin');
      sync.testWals = [...bundle, fresh];
      await sync.syncWal(wal: memberSynced ? bundle.last : bundle.first);
      expect(
          repairs,
          memberMissing
              ? isEmpty
              : [
                  ['audio_manual_0.bin', 'audio_manual_1.bin']
                ]);
      expect(bundle.first.status, memberMissing ? WalStatus.miss : WalStatus.uploaded);
      expect(bundle.every((w) => w.repairJobId == 'bp_original' && !w.isSyncing), isTrue);
      expect(fresh.status, WalStatus.miss);
      expect(listener.acknowledgements, 0);
      expect(await File('${dir.path}/audio_manual_0.bin').readAsBytes(), [1, 2, 3, 4, 5]);
      await sync.stop();
    });
  }

  test('complete repair sends its original handle and acknowledges only after completion', () async {
    final listener = _Listener();
    final handles = <String>[];
    final uploads = <List<String>>[];
    var completed = false;
    var clock = now;
    final sync = LocalWalSyncImpl(listener,
        now: () => clock,
        persistWals: (_) async {},
        jobStatusFetcher: (_) async => SyncJobFetch(
            SyncJobFetchOutcome.ok,
            SyncJobStatusResponse(
                jobId: 'bp_original',
                status: completed ? 'completed' : 'processing',
                totalFiles: 2,
                processedSegments: completed ? 2 : 1,
                totalSegments: 2,
                failedSegments: 0)),
        uploadGate: SyncUploadGate(
            limiter: SyncRateLimiter.instance,
            fairUseStatusLoader: () async => {'stage': 'none'},
            uploader: (files,
                {onUploadProgress,
                conversationId,
                captureEvidence,
                recordingSessionId,
                audioStartSeconds,
                audioEndSeconds,
                claimLiveCapture = false,
                geolocation}) async {
              fail('Repair must not use ordinary upload transport');
            },
            repairUploader: (files,
                {required repairJobId,
                onUploadProgress,
                conversationId,
                captureEvidence,
                recordingSessionId,
                audioStartSeconds,
                audioEndSeconds,
                claimLiveCapture = false,
                geolocation}) async {
              handles.add(repairJobId);
              uploads.add(files.map((f) => f.uri.pathSegments.last).toList());
              return UploadFilesResult.queued(repairJobId, pollAfterMs: 0);
            }));
    final wals = <Wal>[];
    for (var index = 0; index < 2; index++) {
      final name = 'audio_repair_$index.bin';
      await File('${dir.path}/$name').writeAsBytes([1, 2, 3, 4, 5]);
      wals.add(Wal(
          timerStart: 1000 + index,
          codec: BleAudioCodec.opus,
          seconds: 10,
          status: WalStatus.miss,
          storage: WalStorage.disk,
          device: 'omi',
          filePath: name)
        ..repairJobId = 'bp_original'
        ..repairFileCount = 2);
    }
    sync.testWals = wals;
    await sync.syncAll();
    expect(handles, ['bp_original']);
    expect(uploads, [
      ['audio_repair_0.bin', 'audio_repair_1.bin']
    ]);
    expect(listener.acknowledgements, 0);
    expect(wals.every((w) => w.status == WalStatus.uploaded && w.repairJobId == 'bp_original'), isTrue);
    completed = true;
    clock = now.add(const Duration(minutes: 6));
    SyncJobPoller.instance.resetForTesting(clock: () => clock);
    await sync.reconcileUploadedWals();
    expect(listener.acknowledgements, 2);
    expect(wals.every((w) => w.status == WalStatus.synced && w.repairJobId == null && w.repairFileCount == 0), isTrue);
    await sync.stop();
  });
}
