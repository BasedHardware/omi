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
      sync.testWals = [
        _makeWal(timerStart: 1000, status: WalStatus.synced, filePath: null),
      ];

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

      expect(sync.testWals.first.status, WalStatus.corrupted,
          reason: 'null filePath must be marked corrupted so the WAL is not retried as miss');
    });

    test('WAL with non-existent file is marked corrupted after syncAll', () async {
      // Scenario: filePath is set but the file was deleted from disk
      // (OS cleanup, user cleared app storage, etc.).
      // The file does NOT exist in tempDir, so existsSync() returns false.
      final wal = _makeWal(timerStart: 2000, filePath: 'ghost_audio_2000.bin');
      sync.testWals = [wal];

      await sync.syncAll();

      expect(sync.testWals.first.status, WalStatus.corrupted,
          reason: 'missing file must be marked corrupted, not silently re-queued');
    });

    test('corrupted WAL is excluded from syncAll retry pool', () async {
      // Scenario: WAL was already marked corrupted in a prior run.
      // syncAll() filters to miss+disk only — corrupted WALs must not be touched.
      final wal = _makeWal(timerStart: 3000, status: WalStatus.corrupted, filePath: null);
      sync.testWals = [wal];

      // syncAll with no miss WALs returns null immediately — no mutation expected.
      final result = await sync.syncAll();

      expect(result, isNull);
      expect(sync.testWals.first.status, WalStatus.corrupted,
          reason: 'corrupted WAL must not be reset to miss by syncAll');
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
      await file.writeAsBytes([0xAA, 0xBB]);  // Any content — just needs to exist

      final wal = _makeWal(timerStart: 5000, filePath: filename);
      sync.testWals = [wal];

      // Attempt syncAll; it will try to upload but fail with a network error.
      // We catch the error and only check that the WAL was NOT pre-marked corrupted.
      try {
        await sync.syncAll().timeout(const Duration(seconds: 3));
      } catch (_) {
        // Expected: network call fails in test environment
      }

      // The WAL must not have been corrupted by the pre-upload checks.
      // It may be miss (upload failed) or synced (upload succeeded) — both are valid.
      expect(sync.testWals.first.status, isNot(WalStatus.corrupted),
          reason: 'a WAL whose file exists must not be marked corrupted during pre-upload checks');
    });
  });

  // -------------------------------------------------------------------------
  // Zombie miss — documents the known gap: no retry cap in syncAll()
  // -------------------------------------------------------------------------

  group('zombie miss: retry cap gap (known issue)', () {
    test('KNOWN ISSUE: miss WAL with no file has retryCount but syncAll does not check it', () async {
      // This test documents the behaviour, not a fix.
      //
      // getMissingWals() (used by getOrphanedWals) gates on retryCount < 3,
      // but syncAll() at line 504 filters ONLY on status == miss && storage == disk.
      // It ignores retryCount entirely.
      //
      // Result: a WAL that consistently fails upload will be re-queued on
      // every app open (via _autoUploadPendingPhoneFiles → syncAll) with no
      // backoff and no cap, causing infinite retry.
      //
      // Fix needed: syncAll() should skip WALs with retryCount >= maxRetries,
      // OR _autoUploadPendingPhoneFiles should apply its own cap before calling syncAll().
      final wal = _makeWal(timerStart: 1000, filePath: null);
      wal.retryCount = 10;  // Already retried 10 times
      sync.testWals = [wal];

      // syncAll does not check retryCount — the WAL is still processed
      await sync.syncAll();

      // The WAL is eventually corrupted (null filePath), but that is because
      // of the file-existence check, NOT a retry cap. With a valid but
      // persistently-failing file, the WAL would stay miss forever.
      //
      // This test simply documents that retryCount is not consulted.
      // A future fix should make syncAll skip WALs with retryCount >= 3.
    });
  });
}
