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

/// Minimal listener for testing — records calls without side effects.
class _MockListener implements IWalSyncListener {
  int walUpdatedCount = 0;
  final List<Wal> syncedWals = [];

  @override
  void onWalUpdated() {
    walUpdatedCount++;
  }

  @override
  void onWalSynced(Wal wal, {ServerConversation? conversation}) {
    syncedWals.add(wal);
  }
}

/// Helper to create a Wal with sensible defaults for testing.
Wal _makeWal({
  required int timerStart,
  WalStatus status = WalStatus.miss,
  WalStorage storage = WalStorage.disk,
  String device = 'omi',
}) {
  return Wal(
    timerStart: timerStart,
    codec: BleAudioCodec.opus,
    seconds: 60,
    status: status,
    storage: storage,
    device: device,
    filePath: 'test_audio_${timerStart}.bin',
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

    // Create a temp directory and mock path_provider so WalFileManager
    // writes to it instead of the real app documents directory.
    tempDir = await Directory.systemTemp.createTemp('wal_test_');
    TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger.setMockMethodCallHandler(
      const MethodChannel('plugins.flutter.io/path_provider'),
      (MethodCall methodCall) async {
        if (methodCall.method == 'getApplicationDocumentsDirectory') {
          return tempDir.path;
        }
        return null;
      },
    );

    // Re-initialize WalFileManager so its static _walFile points to the
    // fresh temp directory (clears state from previous test runs).
    await WalFileManager.init();

    listener = _MockListener();
    sync = LocalWalSyncImpl(listener);
  });

  tearDown(() async {
    TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger.setMockMethodCallHandler(
      const MethodChannel('plugins.flutter.io/path_provider'),
      null,
    );
    if (tempDir.existsSync()) {
      tempDir.deleteSync(recursive: true);
    }
  });

  group('getSessionUnsyncedWals', () {
    test('returns only miss+disk WALs within session window', () {
      final now = DateTime.now().millisecondsSinceEpoch ~/ 1000;
      final sessionStart = now - 300; // 5 minutes ago

      sync.testWals = [
        _makeWal(timerStart: sessionStart + 10, status: WalStatus.miss, storage: WalStorage.disk),
        _makeWal(timerStart: sessionStart + 60, status: WalStatus.miss, storage: WalStorage.disk),
        _makeWal(timerStart: sessionStart + 120, status: WalStatus.synced, storage: WalStorage.disk),
      ];

      final result = sync.getSessionUnsyncedWals(sessionStart);

      expect(result.length, 2);
      expect(result.every((w) => w.status == WalStatus.miss), true);
      expect(result.every((w) => w.storage == WalStorage.disk), true);
      expect(result[0].timerStart, sessionStart + 10);
      expect(result[1].timerStart, sessionStart + 60);
    });

    test('excludes mem-storage WALs', () {
      final now = DateTime.now().millisecondsSinceEpoch ~/ 1000;
      final sessionStart = now - 300;

      sync.testWals = [
        _makeWal(timerStart: sessionStart + 10, status: WalStatus.miss, storage: WalStorage.mem),
        _makeWal(timerStart: sessionStart + 20, status: WalStatus.miss, storage: WalStorage.disk),
        _makeWal(timerStart: sessionStart + 30, status: WalStatus.miss, storage: WalStorage.sdcard),
      ];

      final result = sync.getSessionUnsyncedWals(sessionStart);

      expect(result.length, 1);
      expect(result[0].timerStart, sessionStart + 20);
      expect(result[0].storage, WalStorage.disk);
    });

    test('excludes WALs outside session window', () {
      final now = DateTime.now().millisecondsSinceEpoch ~/ 1000;
      final sessionStart = now - 120; // 2 minutes ago

      sync.testWals = [
        // Before session window
        _makeWal(timerStart: sessionStart - 600, status: WalStatus.miss, storage: WalStorage.disk),
        _makeWal(timerStart: sessionStart - 1, status: WalStatus.miss, storage: WalStorage.disk),
        // Inside session window
        _makeWal(timerStart: sessionStart, status: WalStatus.miss, storage: WalStorage.disk),
        _makeWal(timerStart: sessionStart + 60, status: WalStatus.miss, storage: WalStorage.disk),
        // After now (future — should not normally exist, but verify filter)
        _makeWal(timerStart: now + 600, status: WalStatus.miss, storage: WalStorage.disk),
      ];

      final result = sync.getSessionUnsyncedWals(sessionStart);

      expect(result.length, 2);
      expect(result[0].timerStart, sessionStart);
      expect(result[1].timerStart, sessionStart + 60);
    });

    test('returns empty when no WALs match', () {
      final now = DateTime.now().millisecondsSinceEpoch ~/ 1000;
      final sessionStart = now - 60;

      // All synced, none missing
      sync.testWals = [
        _makeWal(timerStart: sessionStart + 10, status: WalStatus.synced, storage: WalStorage.disk),
        _makeWal(timerStart: sessionStart + 20, status: WalStatus.synced, storage: WalStorage.disk),
      ];

      final result = sync.getSessionUnsyncedWals(sessionStart);

      expect(result, isEmpty);
    });

    test('returns empty when WALs list is empty', () {
      final now = DateTime.now().millisecondsSinceEpoch ~/ 1000;
      sync.testWals = [];

      final result = sync.getSessionUnsyncedWals(now - 60);

      expect(result, isEmpty);
    });
  });

  group('markWalSyncedAndPersist', () {
    test('updates status to synced', () async {
      final now = DateTime.now().millisecondsSinceEpoch ~/ 1000;
      final wal = _makeWal(timerStart: now - 30, status: WalStatus.miss, storage: WalStorage.disk);
      sync.testWals = [wal];

      expect(wal.status, WalStatus.miss);

      await sync.markWalSyncedAndPersist(wal);

      expect(wal.status, WalStatus.synced);
      expect(listener.walUpdatedCount, 1);
    });

    test('persists to disk via WalFileManager', () async {
      final now = DateTime.now().millisecondsSinceEpoch ~/ 1000;
      final wal = _makeWal(timerStart: now - 30, status: WalStatus.miss, storage: WalStorage.disk);
      sync.testWals = [wal];

      await sync.markWalSyncedAndPersist(wal);

      // Verify the WAL JSON file was written to the temp directory.
      final walFile = File('${tempDir.path}/wals.json');
      expect(walFile.existsSync(), true);

      final content = walFile.readAsStringSync();
      expect(content.contains('"status":"synced"'), true);
    });
  });
}
