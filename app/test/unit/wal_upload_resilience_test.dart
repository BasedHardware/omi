import 'dart:async';
import 'dart:convert';
import 'dart:io';

import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:shared_preferences/shared_preferences.dart';

import 'package:omi/backend/http/api/sync_upload_refusal.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/bt_device/bt_device.dart';
import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/services/capture/capture_end.dart';
import 'package:omi/services/wals/local_wal_sync.dart';
import 'package:omi/services/wals/recording_wait_deferrals.dart';
import 'package:omi/services/wals/mobile_batch_buffer.dart';
import 'package:omi/services/wals/sync_rate_limiter.dart';
import 'package:omi/services/wals/sync_upload_gate.dart';
import 'package:omi/services/wals/wal.dart';
import 'package:omi/services/wals/wal_interfaces.dart';
import 'package:omi/utils/debug_log_manager.dart';
import 'package:omi/utils/wal_file_manager.dart';
import '../support/faulting_wal_writer.dart';

/// Covers WAL upload failure scenarios that cause recordings to become stuck.
///
/// Three sticky states observed in production:
///   1. null filePath — WAL was created in memory but flush failed; file
///      reference was never written. syncAll() marks it corrupted and skips it
///      permanently.
///   2. File missing on disk — file was deleted (OS cleanup, user cleared
///      storage) after the WAL was serialised. Same permanent-corrupted outcome.
///   3. Zombie miss — upload fails (network/server error) and the WAL stays
///      miss, so it is re-queued on every app open with no retry cap or
///      backoff. These tests document that retry cap is NOT enforced by
///      syncAll(), so the team knows it must be added separately.
///
/// Every upload attempt uses a deterministic local failure gate. The tests
/// exercise the production state machine without live HTTP or wall-clock
/// timeouts.

class _MockListener implements IWalSyncListener {
  int walUpdatedCount = 0;
  final List<Wal> syncedWals = [];

  @override
  void onWalUpdated() => walUpdatedCount++;

  @override
  void onWalSynced(Wal wal, {ServerConversation? conversation}) => syncedWals.add(wal);
}

class _UploadGateSpy implements SyncUploadGate {
  int calls = 0;

  @override
  bool isRecordingWaiting({String? recordingGroup, String? filePath}) => false;

  @override
  dynamic noSuchMethod(Invocation invocation) {
    if (invocation.memberName == #upload) {
      calls++;
      return Future.value(UploadFilesResult.queued('accepted'));
    }
    return super.noSuchMethod(invocation);
  }
}

Wal _makeWal({
  required int timerStart,
  WalStatus status = WalStatus.miss,
  WalStorage storage = WalStorage.disk,
  String? filePath = 'audio_1000.bin',
}) {
  return Wal(
    timerStart: timerStart,
    codec: BleAudioCodec.opus,
    seconds: 60,
    status: status,
    storage: storage,
    device: 'omi',
    filePath: filePath,
  );
}

void main() {
  late LocalWalSyncImpl sync;
  late _MockListener listener;
  late Directory tempDir;
  // What the injected uploader throws. Defaults to a generic failure; groups
  // that exercise a specific server rejection override it in their own setUp.
  late Object uploadFailure;
  Future<UploadFilesResult> Function(List<File>)? uploadResponse;
  late List<List<String>> uploadAttempts;
  late List<bool> liveClaims;

  setUp(() async {
    TestWidgetsFlutterBinding.ensureInitialized();
    SharedPreferences.setMockInitialValues({});
    await SharedPreferencesUtil.init();

    tempDir = await Directory.systemTemp.createTemp('wal_resilience_');
    TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger.setMockMethodCallHandler(
      const MethodChannel('plugins.flutter.io/path_provider'),
      (MethodCall call) async {
        if (call.method == 'getApplicationDocumentsDirectory') return tempDir.path;
        return null;
      },
    );

    await WalFileManager.init();
    listener = _MockListener();
    SyncRateLimiter.instance.clear();
    uploadFailure = StateError('deterministic test upload failure');
    uploadResponse = null;
    uploadAttempts = [];
    liveClaims = [];
    sync = LocalWalSyncImpl(
      listener,
      uploadGate: SyncUploadGate(
        limiter: SyncRateLimiter.instance,
        uploader: (files,
            {onUploadProgress,
            conversationId,
            captureEvidence,
            recordingSessionId,
            audioStartSeconds,
            audioEndSeconds,
            claimLiveCapture = false,
            geolocation}) async {
          uploadAttempts.add(files.map((file) => file.uri.pathSegments.last).toList());
          liveClaims.add(claimLiveCapture);
          if (uploadResponse != null) return uploadResponse!(files);
          throw uploadFailure;
        },
        fairUseStatusLoader: () async => {'stage': 'none'},
      ),
    );
  });

  tearDown(() async {
    TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger.setMockMethodCallHandler(
      const MethodChannel('plugins.flutter.io/path_provider'),
      null,
    );
    SyncRateLimiter.instance.clear();
    if (tempDir.existsSync()) tempDir.deleteSync(recursive: true);
  });

  test('a timed-out file batch retains its WAL and the next recording uploads in the same drain', () async {
    final started = Completer<void>();
    final blocked = Completer<UploadFilesResult>();
    uploadResponse = (files) async {
      if (uploadAttempts.length == 1) {
        started.complete();
        return blocked.future;
      }
      return UploadFilesResult.queued('healthy-job');
    };
    final stamp = DateTime.now().millisecondsSinceEpoch ~/ 1000;
    sync.testWals = [
      for (var i = 0; i < 2; i++)
        _makeWal(timerStart: stamp - 120 + i, filePath: 'audio_$i.bin')..conversationId = 'rec-$i'
    ];
    for (final w in sync.testWals) {
      await File('${tempDir.path}/${w.filePath}').writeAsBytes([1]);
    }
    final pass = sync.syncAll();
    await started.future;
    expect(uploadAttempts.length, 1);
    blocked.completeError(TimeoutException('stalled POST'));
    await pass;
    expect(uploadAttempts.length, 2);
    final failed = sync.testWals.singleWhere((w) => w.filePath == uploadAttempts.first.single);
    expect(failed.status, WalStatus.miss);
    expect(await File('${tempDir.path}/${failed.filePath}').exists(), isTrue);
    expect(sync.testWals.singleWhere((w) => w != failed).jobId, 'healthy-job');
  });

  for (final liveOnly in [false, true]) {
    test('cancel during queued flush prevents the real ${liveOnly ? 'live' : 'fallback'} phone drain reaching its gate',
        () async {
      final gate = _UploadGateSpy();
      final phone = LocalWalSyncImpl(listener, uploadGate: gate);
      final now = DateTime.now().millisecondsSinceEpoch ~/ 1000;
      final wal = _makeWal(timerStart: now - (liveOnly ? 60 : 86400));
      await File('${tempDir.path}/${wal.filePath}').writeAsBytes([1, 0, 0, 0, 42]);
      phone.testWals = [wal];
      final blocked = Completer<void>();
      final queued = phone.testQueueWalIo(blocked.future);
      final pass = liveOnly ? phone.syncLiveCaptureOnly() : phone.syncAll();
      phone.cancelSync(); // The real drain has entered and is waiting on the buffer queue.
      blocked.complete();
      await queued;
      await pass;
      expect(gate.calls, 0);
      expect(wal.status, WalStatus.miss);
      expect(wal.isSyncing, isFalse);
      expect(await File('${tempDir.path}/${wal.filePath}').readAsBytes(), [1, 0, 0, 0, 42]);
      await phone.syncAll(); // Only a deliberately new pass may upload again.
      expect(gate.calls, 1);
    });
  }

  test('end watermark counts unknown clocks and refusals without counting accepted files or valid trailing silence',
      () {
    final now = DateTime.now().millisecondsSinceEpoch ~/ 1000;
    final end = DateTime.fromMillisecondsSinceEpoch((now - 120) * 1000);
    Wal row(int start, WalStatus status) => _makeWal(timerStart: start, status: status)..recordingSessionId = 'ended';
    final refused = row(now - 180, WalStatus.uploadRejected)
      ..uploadRejectionReason = WalUploadRejection.invalidCaptureTime;
    sync.testWals = [
      row(now - 180, WalStatus.miss),
      row(2145916800, WalStatus.miss),
      row(0, WalStatus.miss),
      refused,
      row(now - 180, WalStatus.inProgress),
      row(now - 60, WalStatus.miss), // Trusted trailing silence after the end.
      row(2145916800, WalStatus.uploaded),
      row(2145916800, WalStatus.synced)..syncedAt = now,
      row(now - 180, WalStatus.synced), // Transport only: no server proof.
      row(now - 180, WalStatus.corrupted),
      row(now - 180, WalStatus.outsideRecoveryWindow),
      row(2145916800, WalStatus.miss)..recordingSessionId = 'other',
    ];
    expect(sync.pendingWalsForRecording('ended', through: end), 8);
    expect(sync.pendingWalsForRecording('ended'), 9);
  });

  for (final operation in ['flush', 'close']) {
    test('failed $operation seal stays pending from disk through cancel and replay until real upload acceptance',
        () async {
      SharedPreferencesUtil().uid = 'owner';
      late FaultingWalWriter writer;
      final producer = MobileBatchBuffer(
        directory: tempDir,
        publish: (_) async => fail('a failed seal must not publish'),
        openWriter: (file) => writer = FaultingWalWriter(file),
      );
      await producer.initialize();
      final now = DateTime.now();
      expect(
          producer.append([9], uid: 'owner', codec: BleAudioCodec.opus, now: now, recordingSessionId: 'sealed'), true);
      if (operation == 'flush') {
        writer.failFlush = true;
      } else {
        writer.failClose = true;
      }
      producer.seal();
      expect(producer.failed, isTrue);
      expect(producer.hasFrames, isFalse, reason: 'the failed writer has left the in-memory set');
      // Recreate the observer as on restart: it has never held this WAL in memory.
      final observer = MobileBatchBuffer(directory: tempDir, publish: (_) async {});
      final sent = <int>[];
      Future<int> pending() async =>
          await observer.pendingJournalCount('sealed',
              through: now, acceptedFileBytes: sync.captureEndAcceptedFileBytes('sealed')) +
          sync.pendingWalsForRecording('sealed', through: now);
      final reporter = CaptureEndReporter(
        post: (signal, {required pendingWals, required sentAt}) async {
          sent.add(pendingWals);
          return true;
        },
        pendingWals: (_) => pending(),
        disabled: () async => false,
      );
      await reporter.report(CaptureEndSignal(
          recordingSessionId: 'sealed', type: CaptureEndType.userInitiated, lastSpeechAt: now, decidedAt: now));
      expect(sent, [1], reason: 'the durable journal survives a failed seal and a fresh observer');
      final recovered = await MobileBatchBuffer.recover(tempDir, []);
      expect(recovered, hasLength(1));
      await sync.addExternalWal(recovered.single, admittedGeneration: sync.sessionGeneration);
      expect(await pending(), greaterThan(0), reason: 'journal replay/index admission is not server acceptance');
      final blocked = Completer<void>();
      final queued = sync.testQueueWalIo(blocked.future);
      final cancelled = sync.syncAll();
      sync.cancelSync();
      blocked.complete();
      await queued;
      await cancelled;
      await reporter.uploadAccepted('sealed');
      expect(uploadAttempts, isEmpty);
      expect(sent, [1], reason: 'cancellation cannot discharge pending evidence');
      uploadResponse = (_) async => UploadFilesResult.queued('accepted-seal');
      sync.onRecordingUploadAccepted = (session) => unawaited(reporter.uploadAccepted(session));
      await sync.syncAll();
      await reporter.uploadAccepted('sealed');
      expect(sent, [1, 0]);
      expect(await pending(), 0);
      expect(tempDir.listSync().whereType<File>().where((file) => file.path.endsWith('.batch-journal')), hasLength(1),
          reason: 'observing acceptance does not delete or rewrite recovery evidence');
      expect(await File('${tempDir.path}/${recovered.single.filePath}').readAsBytes(), [1, 0, 0, 0, 9]);
    });
  }

  test('end reporter reaches zero only after both clock classes in the same session are accepted', () async {
    final now = DateTime.now().millisecondsSinceEpoch ~/ 1000;
    final valid = _makeWal(timerStart: now - 60, filePath: 'audio_${now - 60}.bin')..recordingSessionId = 'mixed';
    final future = _makeWal(timerStart: 2145916800, filePath: 'audio_2145916800.bin')
      ..recordingSessionId = 'mixed'
      ..markUploadRejected(reasonCode: WalUploadRejection.invalidCaptureTime, nowSeconds: now - 10 * 86400);
    for (final wal in [valid, future]) {
      await File('${tempDir.path}/${wal.filePath}').writeAsBytes([1, 0, 0, 0, 42]);
    }
    sync.testWals = [future, valid];
    final sent = <int>[];
    final reporter = CaptureEndReporter(
      disabled: () async => false,
      post: (signal, {required pendingWals, required sentAt}) async {
        sent.add(pendingWals);
        return true;
      },
      pendingWals: (signal) => sync.pendingWalsForRecording(signal.recordingSessionId, through: signal.decidedAt),
    );
    sync.onRecordingUploadAccepted = (session) => unawaited(reporter.uploadAccepted(session));
    uploadResponse = (files) async {
      if (files.single.uri.pathSegments.last == future.filePath) {
        expect(valid.status, WalStatus.uploaded, reason: 'valid audio retains the first turn');
        expect(sync.pendingWalsForRecording('mixed', through: DateTime.now()), 1);
      }
      return UploadFilesResult.queued('accepted-${uploadAttempts.length}');
    };
    await reporter.report(CaptureEndSignal(
      recordingSessionId: 'mixed',
      type: CaptureEndType.userInitiated,
      lastSpeechAt: DateTime.now(),
      decidedAt: DateTime.now(),
    ));
    await sync.syncAll();
    await reporter.uploadAccepted('mixed'); // Settle the reporter's serialized observer queue.
    expect(uploadAttempts, [
      [valid.filePath],
      [future.filePath]
    ]);
    expect(liveClaims.last, isFalse, reason: 'the unknown clock never claims a live manifest');
    expect(sent, [2, 0], reason: 'accepting valid work must not hide the retained invalid-date refusal');
    expect(future.status, WalStatus.uploaded);
  });

  // -------------------------------------------------------------------------
  // getMissingWals — status filter
  // -------------------------------------------------------------------------

  group('getMissingWals', () {
    test('returns only miss WALs, excludes synced and corrupted', () async {
      sync.testWals = [
        _makeWal(timerStart: 1000, status: WalStatus.miss),
        _makeWal(timerStart: 2000, status: WalStatus.synced),
        _makeWal(timerStart: 3000, status: WalStatus.corrupted),
        _makeWal(timerStart: 4000, status: WalStatus.miss),
      ];

      final missing = await sync.getMissingWals();

      expect(missing.length, 2);
      expect(missing.every((w) => w.status == WalStatus.miss), isTrue);
      expect(missing.map((w) => w.timerStart), containsAll([1000, 4000]));
    });

    test('returns empty list when no miss WALs exist', () async {
      sync.testWals = [
        _makeWal(timerStart: 1000, status: WalStatus.synced),
        _makeWal(timerStart: 2000, status: WalStatus.corrupted),
      ];

      final missing = await sync.getMissingWals();
      expect(missing, isEmpty);
    });
  });

  // -------------------------------------------------------------------------
  // deleteAllPendingWals — terminal corruption stays visible for individual
  // review/delete instead of being silently grouped with retryable work.
  // -------------------------------------------------------------------------

  group('deleteAllPendingWals', () {
    test('removes miss but preserves terminal corrupted and synced WALs', () async {
      final syncedWal = _makeWal(timerStart: 9000, status: WalStatus.synced, filePath: null);
      final corruptedWal = _makeWal(timerStart: 2000, status: WalStatus.corrupted, filePath: null);
      sync.testWals = [_makeWal(timerStart: 1000, status: WalStatus.miss, filePath: null), corruptedWal, syncedWal];

      await sync.deleteAllPendingWals();

      final remaining = await sync.getAllWals();
      expect(remaining, containsAll([corruptedWal, syncedWal]));
      expect(remaining, hasLength(2));
    });

    test('no-op when no pending WALs exist', () async {
      sync.testWals = [_makeWal(timerStart: 1000, status: WalStatus.synced, filePath: null)];

      await sync.deleteAllPendingWals();

      expect((await sync.getAllWals()).length, 1);
    });

    test('terminal clear removes only corrupted WALs', () async {
      final missingWal = _makeWal(timerStart: 1000, status: WalStatus.miss, filePath: null);
      final corruptedWal = _makeWal(timerStart: 2000, status: WalStatus.corrupted, filePath: null);
      final syncedWal = _makeWal(timerStart: 3000, status: WalStatus.synced, filePath: null);
      sync.testWals = [missingWal, corruptedWal, syncedWal];

      await sync.deleteAllCorruptedWals();

      expect(await sync.getAllWals(), containsAll([missingWal, syncedWal]));
      expect(await sync.getAllWals(), hasLength(2));
    });
  });

  // -------------------------------------------------------------------------
  // syncAll pre-upload file checks
  //
  // Both cases below pass the syncAll() miss filter but fail local file
  // validation, so they become terminal corruption before any upload.
  // -------------------------------------------------------------------------

  group('syncAll: pre-upload file validation', () {
    test('WAL with null filePath is marked corrupted after syncAll', () async {
      // Scenario: WAL was never flushed to disk — filePath is null.
      // syncAll() checks filePath == null before attempting getFilePath().
      final wal = _makeWal(timerStart: 1000, filePath: null);
      sync.testWals = [wal];

      await sync.syncAll();

      expect(
        sync.testWals.first.status,
        WalStatus.corrupted,
        reason: 'null filePath must be marked corrupted so the WAL is not retried as miss',
      );
    });

    test('WAL with non-existent file is marked corrupted after syncAll', () async {
      // Scenario: filePath is set but the file was deleted from disk
      // (OS cleanup, user cleared app storage, etc.).
      // The file does NOT exist in tempDir, so existsSync() returns false.
      final wal = _makeWal(timerStart: 2000, filePath: 'ghost_audio_2000.bin');
      wal
        ..isSyncing = true
        ..syncStartedAt = DateTime.now()
        ..syncEtaSeconds = 10
        ..syncSpeedKBps = 12;
      sync.testWals = [wal];

      await sync.syncAll();

      expect(
        sync.testWals.first.status,
        WalStatus.corrupted,
        reason: 'missing file must be marked corrupted, not silently re-queued',
      );
      expect(await sync.getMissingWals(), isEmpty, reason: 'terminal corruption must leave the retry queue');
      expect(await sync.syncAll(), isNull, reason: 'a second sync must not retry terminal corruption');
      expect(wal.isSyncing, isFalse);
      expect(wal.syncStartedAt, isNull);
      expect(wal.syncEtaSeconds, isNull);
      expect(wal.syncSpeedKBps, isNull);
    });

    test('corrupted WAL is excluded from syncAll retry pool', () async {
      // Scenario: WAL was already marked corrupted in a prior run.
      // syncAll() filters to miss+disk only — corrupted WALs must not be touched.
      final wal = _makeWal(timerStart: 3000, status: WalStatus.corrupted, filePath: null);
      sync.testWals = [wal];

      // syncAll with no miss WALs returns null immediately — no mutation expected.
      final result = await sync.syncAll();

      expect(result, isNull);
      expect(
        sync.testWals.first.status,
        WalStatus.corrupted,
        reason: 'corrupted WAL must not be reset to miss by syncAll',
      );
    });

    test('multiple null-filePath WALs in one batch are all marked corrupted', () async {
      sync.testWals = [
        _makeWal(timerStart: 1000, filePath: null),
        _makeWal(timerStart: 2000, filePath: null),
        _makeWal(timerStart: 3000, filePath: null),
      ];

      await sync.syncAll();

      expect(sync.testWals.every((w) => w.status == WalStatus.corrupted), isTrue);
    });

    test('valid file on disk is NOT marked corrupted', () async {
      // Write an actual file so existsSync() returns true.
      // syncAll() reaches the injected deterministic upload failure only after
      // production file validation accepts the file.
      const filename = 'valid_audio_5000.bin';
      final file = File('${tempDir.path}/$filename');
      await file.writeAsBytes([1, 0, 0, 0, 0xAA]); // Any content — just needs to exist

      final wal = _makeWal(timerStart: 5000, filePath: filename);
      sync.testWals = [wal];

      final result = await sync.syncAll();

      expect(result?.localUploadFailures, 1);
      expect(
        sync.testWals.first.status,
        WalStatus.miss,
        reason: 'a WAL whose file exists must not be corrupted by pre-upload checks; '
            'a failed upload leaves it retryable as miss',
      );
    });
  });

  // -------------------------------------------------------------------------
  // Zombie miss — the exact symptom the user is experiencing:
  //   "recordings retry upload every time I exit and open the app"
  //
  // Root cause: syncAll() catches all upload failures and resets isSyncing,
  // but does NOT increment retryCount or change status. The WAL stays miss
  // and is re-queued by _autoUploadPendingPhoneFiles on the next cold start.
  // -------------------------------------------------------------------------

  group('zombie miss: upload failure leaves WAL stuck as miss', () {
    test('failed upload leaves WAL as miss with retryCount unchanged', () async {
      // Simulates what the user observes: a recording that exists on disk,
      // gets picked up by syncAll(), upload attempt fails (network/server error),
      // and the WAL is returned to miss — indistinguishable from its initial state.
      //
      // On next app open, _autoUploadPendingPhoneFiles runs again, finds the same
      // miss WAL, and re-queues it. This loop repeats indefinitely.

      const filename = 'zombie_audio_6000.bin';
      final file = File('${tempDir.path}/$filename');
      await file.writeAsBytes([1, 0, 0, 0, 0xAA]); // File exists — passes pre-upload checks

      final wal = _makeWal(timerStart: 6000, filePath: filename);
      expect(wal.retryCount, 0);
      sync.testWals = [wal];

      // syncAll() reaches the deterministic local upload failure.
      // The catch block at local_wal_sync.dart:661 resets isSyncing but does NOT:
      //   - increment retryCount
      //   - change status
      //   - apply any backoff
      final result = await sync.syncAll();

      final stuck = sync.testWals.first;
      expect(result?.localUploadFailures, 1);
      expect(
        stuck.status,
        WalStatus.miss,
        reason: 'upload failure must not permanently corrupt the WAL — it stays miss',
      );
      expect(
        stuck.retryCount,
        0,
        reason: 'syncAll() never increments retryCount, so the WAL looks brand-new '
            'on every app open and is unconditionally re-queued',
      );
      expect(stuck.isSyncing, false, reason: 'isSyncing must be cleared so the WAL is eligible for the next attempt');
    });

    test('syncAll skips a WAL whose auto-retry budget is spent', () async {
      // The automatic drain used to filter only on status==miss && storage==disk,
      // so a recording that had already failed 50 times was treated exactly like
      // one never tried — the server could refuse the same bytes forever.
      // `isAutoUploadEligible` now applies `walMaxAutoRetries` to every auto loop.
      const filename = 'high_retry_7000.bin';
      final file = File('${tempDir.path}/$filename');
      await file.writeAsBytes([1, 0, 0, 0, 0xAA]);

      final wal = _makeWal(timerStart: 7000, filePath: filename);
      wal.retryCount = 50; // Has failed 50 times already
      sync.testWals = [wal];

      final result = await sync.syncAll();

      expect(result, isNull, reason: 'nothing is eligible, so the drain has no batch to attempt');
      final skipped = sync.testWals.first;
      expect(skipped.status, WalStatus.miss, reason: 'the recording is retained, not discarded');
      expect(skipped.isSyncing, false);
      expect(skipped.retryCount, 50, reason: 'a skipped recording spends nothing further');
      expect(skipped.syncDisplayState, WalSyncDisplayState.failed,
          reason: 'the sync row presents it as failed with a manual retry');
    });

    test('syncAll still uploads a WAL with budget left', () async {
      const filename = 'some_retry_7100.bin';
      final file = File('${tempDir.path}/$filename');
      await file.writeAsBytes([1, 0, 0, 0, 0xAA]);

      final wal = _makeWal(timerStart: 7100, filePath: filename);
      wal.retryCount = walMaxAutoRetries - 1;
      sync.testWals = [wal];

      final result = await sync.syncAll();

      expect(result?.localUploadFailures, 1, reason: 'the last budgeted attempt is still made');
      expect(sync.testWals.first.isSyncing, false);
    });
  });

  // -------------------------------------------------------------------------
  // A network switch under an open upload: iOS fails the socket with
  // EADDRNOTAVAIL (errno 49), and package:http reports it as a bare
  // ClientException("Can't assign requested address"). The recording must stay
  // queued with its retry budget, the failure must not read as a permanent
  // refusal, and the next pass must upload the same file.
  // -------------------------------------------------------------------------

  group('network switch mid-upload (EADDRNOTAVAIL)', () {
    final uri = Uri.parse('https://api.omi.me/v2/sync-local-files?audio_start_seconds=1792927415.0');
    final failures = <String, Object>{
      'bare ClientException': http.ClientException("Can't assign requested address", uri),
      'SocketException errno 49':
          const SocketException('Write failed', osError: OSError("Can't assign requested address", 49)),
    };

    for (final MapEntry(key: label, value: failure) in failures.entries) {
      test('$label keeps the recording queued and the next pass uploads it', () async {
        const filename = 'handover_audio_8000.bin';
        final file = File('${tempDir.path}/$filename');
        await file.writeAsBytes([1, 0, 0, 0, 0xAA]);
        final wal = _makeWal(timerStart: 8000, filePath: filename);
        sync.testWals = [wal];
        uploadFailure = failure;

        final failed = await sync.syncAll();

        expect(failed?.localUploadFailures, 1);
        expect(failed?.localUploadPermanentFailures, 0, reason: 'a network switch is not a refusal of the audio');
        expect(failed?.localUploadPermanentError, isNull);
        expect(wal.status, WalStatus.miss);
        expect(wal.retryCount, 0);
        expect(wal.isSyncing, isFalse);
        expect(isAutoUploadEligible(wal), isTrue, reason: 'the next automatic pass must pick it up');
        expect(file.existsSync(), isTrue, reason: 'the audio is never dropped');

        uploadResponse = (files) async => UploadFilesResult.queued('job-after-switch');
        final recovered = await sync.syncAll();

        expect(recovered?.localUploadFailures, 0);
        expect(uploadAttempts, [
          [filename],
          [filename],
        ]);
        expect(wal.status, WalStatus.uploaded);
        expect(wal.jobId, 'job-after-switch');
        expect(file.existsSync(), isTrue, reason: 'the file is kept until the server confirms the job');
      });
    }
  });

  // -------------------------------------------------------------------------
  // Recording older than the server's automatic-recovery window (#10975).
  //
  // `/v2/sync-local-files` answers 422 `backfill_lookback_exceeded` for a
  // capture older than SYNC_BACKFILL_MAX_AGE_SECONDS. No retry can ever make
  // that succeed, so it must leave the retry pool with an explicit state
  // instead of re-uploading the same bytes on every sync pass forever.
  // -------------------------------------------------------------------------

  group('recording older than the automatic-recovery window', () {
    setUp(() {
      uploadFailure = const SyncRecoveryWindowExceededException();
    });

    Future<File> writeAudio(String filename) async {
      final file = File('${tempDir.path}/$filename');
      await file.writeAsBytes([1, 0, 0, 0, 0xAA]);
      return file;
    }

    test('a batch upload rejection is terminal and is never retried', () async {
      const filename = 'too_old_8000.bin';
      final file = await writeAudio(filename);
      final wal = _makeWal(timerStart: 8000, filePath: filename);
      sync.testWals = [wal];

      await sync.syncAll();

      final refused = sync.testWals.first;
      expect(refused.status, WalStatus.outsideRecoveryWindow);
      expect(
        refused.syncDisplayState,
        WalSyncDisplayState.outsideRecoveryWindow,
        reason: 'the row must say why, not read as an unexplained failure',
      );
      expect(refused.isSyncing, isFalse);
      expect(refused.retryCount, 0, reason: 'a rejection that can never succeed must not spend the retry budget');
      expect(await sync.getMissingWals(), isEmpty, reason: 'it must leave the retry pool');
      expect(await sync.syncAll(), isNull, reason: 'a second sync pass must not re-upload it');
      expect(file.existsSync(), isTrue, reason: 'the local audio is intact — only the sync attempt is terminal');
    });

    test('a manual single-recording sync is terminal too', () async {
      const filename = 'too_old_9000.bin';
      await writeAudio(filename);
      final wal = _makeWal(timerStart: 9000, filePath: filename);
      sync.testWals = [wal];

      await sync.syncWal(wal: wal);

      expect(sync.testWals.first.status, WalStatus.outsideRecoveryWindow);
      expect(sync.testWals.first.isSyncing, isFalse);
    });

    test('a mixed-age batch retires only what the rejection proves is too old', () async {
      // The backend measures the lookback from the OLDEST capture in the
      // upload, so a rejected batch says nothing about its newer members.
      // Retiring the whole batch would strand recordings the server accepts.
      for (final t in [8100, 8200, 8300]) {
        await writeAudio('mixed_$t.bin');
      }
      final oldest = _makeWal(timerStart: 8100, filePath: 'mixed_8100.bin');
      final middle = _makeWal(timerStart: 8200, filePath: 'mixed_8200.bin');
      final newest = _makeWal(timerStart: 8300, filePath: 'mixed_8300.bin');
      sync.testWals = [oldest, middle, newest];

      await sync.syncAll();

      expect(oldest.status, WalStatus.outsideRecoveryWindow, reason: 'the rejection proves this one is outside');
      expect(middle.status, WalStatus.miss, reason: 'nothing proves this one is outside — it must stay retryable');
      expect(newest.status, WalStatus.miss);
      // The survivors were flagged in-flight before the batch was rejected. If
      // that flag is left behind they render as "Syncing…" forever and drop out
      // of the deletable-pending set, so a rejection two recordings away silently
      // strands them.
      for (final survivor in [middle, newest]) {
        expect(survivor.isSyncing, isFalse, reason: 'a rejected batch must not leave its survivors stuck in-flight');
        expect(survivor.syncDisplayState, isNot(WalSyncDisplayState.syncing));
      }
    });

    test('recordings outside this batch but at least as old also retire, in the same pass', () async {
      // Otherwise a long backlog costs one doomed batch upload per recording.
      // `outsideBatch` is held out of the batch by its conversation grouping,
      // but it is older than a capture the server just proved is out of range,
      // so it can only be out of range too.
      for (final t in [8000, 8100, 8400]) {
        await writeAudio('tail_$t.bin');
      }
      final outsideBatch = _makeWal(timerStart: 8000, filePath: 'tail_8000.bin')..conversationId = 'other-conversation';
      final oldestInBatch = _makeWal(timerStart: 8100, filePath: 'tail_8100.bin');
      final newest = _makeWal(timerStart: 8400, filePath: 'tail_8400.bin');
      sync.testWals = [outsideBatch, oldestInBatch, newest];

      await sync.syncAll();

      expect(oldestInBatch.status, WalStatus.outsideRecoveryWindow);
      expect(outsideBatch.status, WalStatus.outsideRecoveryWindow, reason: 'older than a proven-rejected capture');
      expect(newest.status, WalStatus.miss, reason: 'newer than the proven bound — still the server\'s call');
    });

    test('a generic upload failure stays retryable', () async {
      uploadFailure = StateError('transient server error');
      const filename = 'transient_8400.bin';
      await writeAudio(filename);
      sync.testWals = [_makeWal(timerStart: 8400, filePath: filename)];

      await sync.syncAll();

      expect(
        sync.testWals.first.status,
        WalStatus.miss,
        reason: 'only the bounded lookback code is terminal — everything else keeps retrying',
      );
    });
  });

  group('definitive upload refusals', () {
    test('isolated retries never claim a partial live-capture manifest', () async {
      final now = DateTime.now().millisecondsSinceEpoch ~/ 1000;
      final wals = <Wal>[];
      for (var i = 0; i < 2; i++) {
        final start = now - 180 + i * 60;
        final name = 'audio_omi_$start.bin';
        await File('${tempDir.path}/$name').writeAsBytes([1, 0, 0, 0, i]);
        wals.add(_makeWal(timerStart: start, filePath: name)
          ..conversationId = 'live-recording'
          ..captureRoot = '12345678-1234-1234-1234-123456789abc'
          ..sourceFrameStart = i * 6000
          ..sourceClockEpoch = 0
          ..totalFrames = 6000);
      }
      sync.testWals = wals;
      uploadResponse = (files) async {
        if (files.length > 1) throw const SyncUploadHttpException(413, 'request too large');
        return UploadFilesResult.queued('job-${uploadAttempts.length}');
      };

      await sync.syncAll();

      expect(liveClaims, [true, false, false]);
      expect(wals.map((wal) => wal.status), everyElement(WalStatus.uploaded));
    });

    for (final statusCode in [400, 413]) {
      test('HTTP $statusCode isolates a refused request before retiring any member', () async {
        final wals = <Wal>[];
        for (var i = 0; i < 3; i++) {
          final name = 'audio_omi_1000$i.bin';
          await File('${tempDir.path}/$name').writeAsBytes([1, 0, 0, 0, i]);
          wals.add(_makeWal(timerStart: 10000 + i, filePath: name));
        }
        sync.testWals = wals;
        uploadResponse = (files) async {
          // 400: one invalid file rejects the request. 413: only the combined
          // request is too large. Neither response proves every file unusable.
          if (files.length > 1 || (statusCode == 400 && files.single.path.endsWith('10002.bin'))) {
            throw SyncUploadHttpException(statusCode, 'request refused');
          }
          return UploadFilesResult.queued('job-${uploadAttempts.length}');
        };

        final result = await sync.syncAll();

        expect(uploadAttempts.map((attempt) => attempt.length), [3, 1, 1, 1]);
        expect(wals.take(2).map((wal) => wal.status), everyElement(WalStatus.uploaded));
        expect(wals.last.status, statusCode == 400 ? WalStatus.uploadRejected : WalStatus.uploaded);
        expect(result?.localUploadPermanentFailures, 0);
        expect(result?.localUploadFailures, 0);
        for (final wal in wals) {
          expect(File('${tempDir.path}/${wal.filePath}').existsSync(), isTrue);
          expect(wal.timerStart, 10000 + wals.indexOf(wal), reason: 'recovery never invents a capture time');
        }
      });
    }

    Future<Wal> refusedWal(int statusCode) async {
      uploadFailure = SyncUploadHttpException(statusCode, 'definitive refusal');
      final filename = 'refused_$statusCode.bin';
      await File('${tempDir.path}/$filename').writeAsBytes([1, 0, 0, 0, 0xAA]);
      final wal = _makeWal(timerStart: 10000 + statusCode, filePath: filename);
      sync.testWals = [wal];
      return wal;
    }

    for (final statusCode in [400, 413]) {
      test('HTTP $statusCode is quiet and immediate repeated wakes do not re-upload', () async {
        final wal = await refusedWal(statusCode);

        final first = await sync.syncAll();
        final second = await sync.syncAll();

        expect(first?.localUploadPermanentFailures, 0);
        expect(second, isNull, reason: 'a connectivity wake must not re-offer a definitive refusal');
        expect(wal.status, WalStatus.uploadRejected);
        expect(wal.syncDisplayState, WalSyncDisplayState.uploadRejected);
        expect(await sync.getMissingWals(), isEmpty);
        expect(File('${tempDir.path}/${wal.filePath}').existsSync(), isTrue,
            reason: 'terminal means stop retrying, not silently delete user audio');
      });
    }

    test('only permanent request refusals share the terminal classifier', () {
      for (final statusCode in [400, 413]) {
        expect(isDefinitiveUploadRefusal(SyncUploadHttpException(statusCode, 'refused')), isTrue);
      }
      expect(isDefinitiveUploadRefusal(const SyncUploadHttpException(401, 're-login required')), isFalse);
      expect(isDefinitiveUploadRefusal(const SyncUploadHttpException(403, 'authentication failed')), isFalse);
      expect(isDefinitiveUploadRefusal(const SyncUploadHttpException(500, 'retryable')), isFalse);
    });

    for (final statusCode in [401, 403]) {
      test('HTTP $statusCode retains audio with a bounded retry budget', () async {
        final wal = await refusedWal(statusCode);
        for (var i = 0; i < walMaxAutoRetries; i++) {
          await sync.syncAll();
        }
        expect(await sync.syncAll(), isNull);
        expect(uploadAttempts, hasLength(1), reason: 'do not repeat the same denied credentials automatically');
        expect(wal.status, WalStatus.miss, reason: 'credentials are not an audio verdict');
        expect(wal.syncDisplayState, WalSyncDisplayState.failed);
        expect(File('${tempDir.path}/${wal.filePath}').existsSync(), isTrue);
      });

      test('a single-file HTTP $statusCode persists a retryable authentication pause', () async {
        final wal = await refusedWal(statusCode);

        await expectLater(sync.syncWal(wal: wal), throwsA(isA<SyncUploadHttpException>()));

        final restored = (await WalFileManager.loadWals()).single;
        expect(restored.status, WalStatus.miss);
        expect(restored.retryCount, walMaxAutoRetries);
        expect(await sync.syncAll(), isNull, reason: 'a manual failure must not spawn an automatic auth loop');
        expect(uploadAttempts, hasLength(1));
      });
    }

    test('a refused batch cannot start isolation under a replacement account', () async {
      final originals = <Wal>[];
      for (var i = 0; i < 2; i++) {
        final name = 'audio_old_$i.bin';
        await File('${tempDir.path}/$name').writeAsBytes([1, 0, 0, 0, i]);
        originals.add(_makeWal(timerStart: 10100 + i, filePath: name));
      }
      final next = _makeWal(timerStart: 10200, filePath: 'audio_next.bin');
      await File('${tempDir.path}/${next.filePath}').writeAsBytes([0xBB]);
      sync.testWals = originals;
      uploadResponse = (_) async {
        sync.clearUserData();
        sync.testWals = [next];
        throw const SyncUploadHttpException(400, 'request refused');
      };

      await sync.syncAll();

      expect(uploadAttempts, hasLength(1));
      expect(next.status, WalStatus.miss);
      expect(originals.map((wal) => wal.status), everyElement(WalStatus.miss));
    });

    test('HTTP 401 is re-armed after a re-login connectivity reset', () async {
      final wal = await refusedWal(401);

      final first = await sync.syncAll();
      wal.retryCount = walMaxAutoRetries;
      final reset = await sync.resetExhaustedAutoRetries();

      expect(first?.localUploadFailures, 1);
      expect(wal.status, WalStatus.miss, reason: 'authentication failure must remain retryable');
      expect(reset, 1);
      expect(wal.retryCount, 0);
      expect(isAutoUploadEligible(wal), isTrue, reason: 'a later login can provide valid credentials');
    });

    test('manual sync retries every terminal WAL state', () async {
      var uploads = 0;
      final manualSync = LocalWalSyncImpl(
        listener,
        uploadGate: SyncUploadGate(
          limiter: SyncRateLimiter.instance,
          uploader: (files,
              {onUploadProgress,
              conversationId,
              captureEvidence,
              recordingSessionId,
              audioStartSeconds,
              audioEndSeconds,
              claimLiveCapture = false,
              geolocation}) async {
            uploads++;
            return UploadFilesResult.done(
              SyncLocalFilesResponse(newConversationIds: const [], updatedConversationIds: const ['recovered']),
            );
          },
          fairUseStatusLoader: () async => {'stage': 'none'},
        ),
      );
      final terminalStatuses = [
        WalStatus.corrupted,
        WalStatus.outsideRecoveryWindow,
        WalStatus.unsupportedAudio,
      ];

      for (var index = 0; index < terminalStatuses.length; index++) {
        final filename = 'manual_terminal_$index.bin';
        await File('${tempDir.path}/$filename').writeAsBytes([1, 0, 0, 0, 0xAA]);
        final wal = _makeWal(timerStart: 11000 + index, status: terminalStatuses[index], filePath: filename);
        manualSync.testWals = [wal];

        await manualSync.syncWal(wal: wal);

        expect(wal.status, WalStatus.synced, reason: '${terminalStatuses[index]} should honor an explicit retry');
      }
      expect(uploads, terminalStatuses.length);
    });
  });

  group('background live-capture drain', () {
    test('recent ID-less WAL drains after connectivity returns without lifecycle events', () async {
      final now = DateTime.utc(2026, 9, 26, 12);
      const filename = 'accepted_socket_no_lifecycle.bin';
      await File('${tempDir.path}/$filename').writeAsBytes([1, 0, 0, 0, 0xAA]);
      var uploads = 0;
      String? uploadedConversationId = 'not-called';
      var claimedLiveCapture = true;
      final backgroundSync = LocalWalSyncImpl(
        listener,
        now: () => now,
        uploadGate: SyncUploadGate(
          limiter: SyncRateLimiter.instance,
          uploader: (files,
              {onUploadProgress,
              conversationId,
              captureEvidence,
              recordingSessionId,
              audioStartSeconds,
              audioEndSeconds,
              claimLiveCapture = false,
              geolocation}) async {
            uploads++;
            uploadedConversationId = conversationId;
            claimedLiveCapture = claimLiveCapture;
            return UploadFilesResult.done(
              SyncLocalFilesResponse(newConversationIds: ['recovered'], updatedConversationIds: []),
            );
          },
          fairUseStatusLoader: () async => {'stage': 'none'},
        ),
      );
      final wal = _makeWal(
        timerStart: now.millisecondsSinceEpoch ~/ 1000 - 60,
        filePath: filename,
      );
      expect(wal.conversationId, isNull, reason: 'no ConversationProcessingStartedEvent ever arrived');
      backgroundSync.testWals = [wal];

      final result = await backgroundSync.syncLiveCaptureOnly();

      expect(uploads, 1, reason: 'the connectivity/background wake must drain the recent safety copy');
      expect(uploadedConversationId, isNull);
      expect(claimedLiveCapture, isFalse, reason: 'an ID-less WAL creates a new server conversation');
      expect(result?.newConversationIds, ['recovered']);
      expect(wal.status, WalStatus.synced);
    });
  });

  test('after restart one session honors a 30-minute custody wait while the other uploads', () async {
    final waitStartedAt = DateTime.utc(2026, 11, 20);
    var now = waitStartedAt;
    const owner = 'record-wait-owner';
    await SharedPreferencesUtil().saveString('uid', owner);
    var canAccept = false;

    LocalWalSyncImpl createLedger() => LocalWalSyncImpl(
          listener,
          now: () => now,
          uploadGate: SyncUploadGate(
            limiter: SyncRateLimiter.instance,
            recordingWaits: RecordingWaitDeferrals(() => now, persist: true),
            fairUseStatusLoader: () async => null,
            uploader: (files,
                {onUploadProgress,
                conversationId,
                captureEvidence,
                recordingSessionId,
                audioStartSeconds,
                audioEndSeconds,
                claimLiveCapture = false,
                geolocation}) async {
              uploadAttempts.add(files.map((file) => file.uri.pathSegments.last).toList());
              if (recordingSessionId == 'waiting-session' && !canAccept) {
                throw const SyncUploadHttpException(503, 'Custody pending',
                    reasonCode: 'record_capture_pending', recordingWaitSeconds: 1800);
              }
              return UploadFilesResult.queued('accepted-$recordingSessionId');
            },
          ),
        );

    final start = now.millisecondsSinceEpoch ~/ 1000 - 100;
    final waiting = _makeWal(timerStart: start, filePath: 'waiting.bin')
      ..conversationId = 'shared-conversation'
      ..recordingSessionId = 'waiting-session';
    final other = _makeWal(timerStart: start + 1, filePath: 'other.bin')
      ..conversationId = 'shared-conversation'
      ..recordingSessionId = 'other-session';
    for (final wal in [waiting, other]) {
      await File('${tempDir.path}/${wal.filePath}').writeAsBytes([1, 0, 0, 0, 42]);
    }
    final first = createLedger()..testWals = [waiting, other];
    await expectLater(first.syncWal(wal: waiting), throwsA(isA<SyncUploadHttpException>()));
    expect(waiting.status, WalStatus.miss);

    now = waitStartedAt.add(const Duration(minutes: 6));
    final restarted = createLedger()..testWals = await WalFileManager.loadWals();
    final restored = restarted.testWals.singleWhere((wal) => wal.recordingSessionId == 'waiting-session');
    final retainedFile = File('${tempDir.path}/${restored.filePath}');
    final deferred = await restarted.syncAll();
    await expectLater(restarted.syncWal(wal: restored), throwsA(isA<SyncRecordingWaitException>()));
    expect(uploadAttempts, [
      ['waiting.bin'],
      ['other.bin'],
    ]);
    expect(deferred?.localUploadFailures, 0);
    final accepted = restarted.testWals.singleWhere((wal) => wal.recordingSessionId == 'other-session');
    expect(accepted.status, WalStatus.uploaded);
    expect(accepted.jobId, 'accepted-other-session');
    expect(restored.status, WalStatus.miss);
    expect(restored.retryCount, 0);
    expect(restored.jobId, isNull);
    expect(await retainedFile.readAsBytes(), [1, 0, 0, 0, 42]);

    canAccept = true;
    now = waitStartedAt.add(const Duration(minutes: 29, seconds: 59));
    await expectLater(restarted.syncWal(wal: restored), throwsA(isA<SyncRecordingWaitException>()));
    expect(uploadAttempts, hasLength(2));

    now = waitStartedAt.add(const Duration(minutes: 30));
    await restarted.syncAll();

    expect(uploadAttempts.last, ['waiting.bin']);
    expect(uploadAttempts, hasLength(3));
    expect(restored.status, WalStatus.uploaded);
    expect(restored.jobId, 'accepted-waiting-session');
    expect(retainedFile.existsSync(), isTrue);
  });

  group('syncAll: server-unavailable pacing', () {
    Future<LocalWalSyncImpl> buildDrain({
      required Object Function() failure,
      required List<Duration> pauses,
      required List<List<String>> attempts,
    }) async {
      final sync = LocalWalSyncImpl(
        listener,
        uploadGate: SyncUploadGate(
          limiter: SyncRateLimiter.instance,
          uploader: (files,
              {onUploadProgress,
              conversationId,
              captureEvidence,
              recordingSessionId,
              audioStartSeconds,
              audioEndSeconds,
              claimLiveCapture = false,
              geolocation}) async {
            attempts.add(files.map((file) => file.uri.pathSegments.last).toList());
            throw failure();
          },
          fairUseStatusLoader: () async => null,
        ),
        sleep: (duration) async => pauses.add(duration),
      );
      // Distinct conversations/sessions so each WAL forms its own batch.
      const base = 2000000000 - 7 * 24 * 60 * 60;
      sync.testWals = [
        for (var i = 0; i < 4; i++)
          () {
            final name = 'paced_$i.bin';
            File('${tempDir.path}/$name').writeAsBytesSync([1]);
            return _makeWal(timerStart: base - i * 60, filePath: name)
              ..conversationId = 'paced-conversation-$i'
              ..recordingSessionId = 'paced-session-$i';
          }(),
      ];
      return sync;
    }

    test('a 503 with Retry-After stops the drain instead of failing every batch', () async {
      final pauses = <Duration>[];
      final attempts = <List<String>>[];
      final sync = await buildDrain(
        failure: () => const SyncUploadHttpException(503, 'Server is temporarily unavailable', retryAfterSeconds: 30),
        pauses: pauses,
        attempts: attempts,
      );

      await sync.syncAll();

      expect(attempts.length, 1, reason: 'the gate cooldown must stop the drain after the first refused batch');
      expect(SyncRateLimiter.instance.isLimited, isTrue);
      expect(SyncRateLimiter.instance.reason, RateLimitReason.backendBusy);
      expect(pauses, isEmpty, reason: 'the server already scoped the pause; no local backoff on top');
      expect(sync.testWals.every((wal) => wal.status == WalStatus.miss), isTrue,
          reason: 'a 503 consumes no retry budget');
    });

    test('a 503 failure line in the shared debug log carries the server reason and pacing', () async {
      // Customer logs showed only "Server is temporarily unavailable": the reason the app
      // already parsed from the response was never written, so support could not tell an
      // Omi refusal from platform shedding without server-side logs.
      await DebugLogManager.setEnabled(true);
      addTearDown(() => DebugLogManager.setEnabled(false));

      Future<Map<String, dynamic>> failureLine(SyncUploadHttpException failure) async {
        await DebugLogManager.clear();
        final sync = await buildDrain(failure: () => failure, pauses: <Duration>[], attempts: <List<String>>[]);
        await sync.syncAll();
        Map<String, dynamic>? extra;
        for (var attempt = 0; attempt < 100 && extra == null; attempt++) {
          await Future<void>.delayed(const Duration(milliseconds: 20));
          final lines = await (await DebugLogManager.getLogFile())!.readAsLines();
          for (final line in lines) {
            final entry = jsonDecode(line) as Map<String, dynamic>;
            if (entry['message'] case final String message when message.startsWith('Local upload HTTP failure')) {
              extra = entry['extra'] as Map<String, dynamic>;
            }
          }
        }
        expect(extra, isNotNull, reason: 'the refused batch must reach the shared debug log');
        return extra!;
      }

      // The recording-scoped wait the server answers while live-record coverage is unproven.
      final scoped = await failureLine(const SyncUploadHttpException(503, 'Server is temporarily unavailable',
          reasonCode: recordCapturePending, retryAfterSeconds: 30, recordingWaitSeconds: 1800));
      expect(scoped['statusCode'], 503);
      expect(scoped['reasonCode'], recordCapturePending);
      expect(scoped['retryAfterSeconds'], 30);
      expect(scoped['recordingWaitSeconds'], 1800);

      // A platform 5xx carries no Omi reason; its line must say so by omission.
      final platform = await failureLine(const SyncUploadHttpException(503, 'Server is temporarily unavailable'));
      expect(platform['statusCode'], 503);
      expect(platform.keys, isNot(contains('reasonCode')));
      expect(platform.keys, isNot(contains('retryAfterSeconds')));
      expect(platform.keys, isNot(contains('recordingWaitSeconds')));
    });

    test('a 503 without Retry-After pauses between batches with a growing backoff', () async {
      final pauses = <Duration>[];
      final attempts = <List<String>>[];
      final sync = await buildDrain(
        failure: () => const SyncUploadHttpException(503, 'Server is temporarily unavailable'),
        pauses: pauses,
        attempts: attempts,
      );

      await sync.syncAll();

      expect(attempts.length, 4, reason: 'without server pacing the drain keeps trying every batch');
      expect(pauses.map((duration) => duration.inSeconds), [2, 4, 8, 16]);
      expect(SyncRateLimiter.instance.isLimited, isFalse);
    });
  });
}
