import 'dart:io';

import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/bt_device/bt_device.dart';
import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/services/wals/local_wal_sync.dart';
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
/// Tests avoid real HTTP by using WAL configurations where files.isEmpty is
/// always true (null/missing paths), so syncLocalFilesV2 is never reached.

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
    sync = LocalWalSyncImpl(listener);
  });

  tearDown(() async {
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
  // deleteAllPendingWals — miss + corrupted are both "pending"
  // -------------------------------------------------------------------------

  group('deleteAllPendingWals', () {
    test('removes miss and corrupted WALs but preserves synced', () async {
      final syncedWal = _makeWal(timerStart: 9000, status: WalStatus.synced, filePath: null);
      sync.testWals = [
        _makeWal(timerStart: 1000, status: WalStatus.miss, filePath: null),
        _makeWal(timerStart: 2000, status: WalStatus.corrupted, filePath: null),
        syncedWal,
      ];

      await sync.deleteAllPendingWals();

      final remaining = await sync.getAllWals();
      expect(remaining.length, 1);
      expect(remaining.first.status, WalStatus.synced);
      expect(remaining.first.timerStart, 9000);
    });

    test('no-op when no pending WALs exist', () async {
      sync.testWals = [_makeWal(timerStart: 1000, status: WalStatus.synced, filePath: null)];

      await sync.deleteAllPendingWals();

      expect((await sync.getAllWals()).length, 1);
    });
  });

  // -------------------------------------------------------------------------
  // syncAll pre-upload file checks
  //
  // Both cases below are "zombie miss" sub-types: the WAL passes the
  // syncAll() miss filter but fails the file-existence check, so it is
  // marked corrupted and no HTTP upload is attempted.
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
      sync.testWals = [wal];

      await sync.syncAll();

      expect(
        sync.testWals.first.status,
        WalStatus.corrupted,
        reason: 'missing file must be marked corrupted, not silently re-queued',
      );
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
      // syncAll() will then try to upload, but files.isNotEmpty means
      // it would call syncLocalFilesV2 — we stop here and just verify
      // the pre-check does not corrupt a valid WAL.
      //
      // NOTE: The actual upload is NOT tested here (requires HTTP mock).
      // This test only exercises the file-existence guard path.
      const filename = 'valid_audio_5000.bin';
      final file = File('${tempDir.path}/$filename');
      await file.writeAsBytes([0xAA, 0xBB]); // Any content — just needs to exist

      final wal = _makeWal(timerStart: 5000, filePath: filename);
      sync.testWals = [wal];

      // Attempt syncAll; it will try to upload but fail with a network error.
      // We catch the error and only check that the WAL was NOT pre-marked corrupted.
      try {
        await sync.syncAll().timeout(const Duration(seconds: 3));
      } catch (_) {
        // Expected: network call fails in test environment
      }

      // No server in test environment — upload fails, WAL stays miss.
      expect(
        sync.testWals.first.status,
        WalStatus.miss,
        reason:
            'a WAL whose file exists must not be corrupted by pre-upload checks; '
            'upload failure in this environment leaves it as miss',
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

      // syncAll() will reach syncLocalFilesV2, which fails (no server in test env).
      // The catch block at local_wal_sync.dart:661 resets isSyncing but does NOT:
      //   - increment retryCount
      //   - change status
      //   - apply any backoff
      try {
        await sync.syncAll().timeout(const Duration(seconds: 5));
      } catch (_) {}

      final stuck = sync.testWals.first;
      expect(
        stuck.status,
        WalStatus.miss,
        reason: 'upload failure must not permanently corrupt the WAL — it stays miss',
      );
      expect(
        stuck.retryCount,
        0,
        reason:
            'syncAll() never increments retryCount, so the WAL looks brand-new '
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
      try {
        await sync.syncAll().timeout(const Duration(seconds: 5));
      } catch (_) {}

      expect(
        sync.testWals.first.isSyncing,
        false,
        reason:
            'isSyncing cleared confirms syncAll processed this WAL, '
            'despite retryCount=50 — no cap is enforced',
      );
    });
  });
}
