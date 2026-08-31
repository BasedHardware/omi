import 'dart:io';

import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/bt_device/bt_device.dart';
import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/services/wals/local_wal_sync.dart';
import 'package:omi/services/wals/sync_rate_limiter.dart';
import 'package:omi/services/wals/sync_upload_gate.dart';
import 'package:omi/services/wals/wal.dart';
import 'package:omi/services/wals/wal_interfaces.dart';
import 'package:omi/utils/wal_file_manager.dart';

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
    sync = LocalWalSyncImpl(
      listener,
      uploadGate: SyncUploadGate(
        limiter: SyncRateLimiter.instance,
        uploader: (files, {onUploadProgress, conversationId, claimLiveCapture = false, geolocation}) async {
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
      await file.writeAsBytes([0xAA, 0xBB]); // Any content — just needs to exist

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
      await file.writeAsBytes([0xAA, 0xBB]); // File exists — passes pre-upload checks

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

    test('KNOWN GAP: syncAll picks up miss WAL regardless of retryCount', () async {
      // getOrphanedWals() gates on retryCount < 3 (line 438), but syncAll()
      // at line 504 filters ONLY on status==miss && storage==disk.
      // A WAL that has already failed 100 times is treated identically to one
      // that has never been tried.
      //
      // Fix needed: syncAll() should skip WALs with retryCount >= N,
      // or _autoUploadPendingPhoneFiles should apply the cap before calling syncAll().
      const filename = 'high_retry_7000.bin';
      final file = File('${tempDir.path}/$filename');
      await file.writeAsBytes([0xAA, 0xBB]);

      final wal = _makeWal(timerStart: 7000, filePath: filename);
      wal.retryCount = 50; // Has failed 50 times already
      sync.testWals = [wal];

      // syncAll will still attempt the upload — retryCount is never consulted.
      // We verify by observing that isSyncing is cleared after the attempt,
      // meaning syncAll processed the WAL (not skipped it).
      final result = await sync.syncAll();

      expect(result?.localUploadFailures, 1);
      expect(
        sync.testWals.first.isSyncing,
        false,
        reason: 'isSyncing cleared confirms syncAll processed this WAL, '
            'despite retryCount=50 — no cap is enforced',
      );
    });
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
      await file.writeAsBytes([0xAA, 0xBB]);
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
}
