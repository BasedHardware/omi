import 'dart:convert';
import 'dart:io';

import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/bt_device/bt_device.dart';
import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/services/audio_sources/audio_source.dart';
import 'package:omi/services/wals/local_wal_sync.dart';
import 'package:omi/services/wals/wal_backlog_telemetry.dart';
import 'package:omi/utils/analytics/registry/events.g.dart';
import 'package:omi/services/wals/wal.dart';
import 'package:omi/services/wals/wal_interfaces.dart';
import 'package:omi/utils/debug_log_manager.dart';
import 'package:omi/utils/wal_file_manager.dart';

class _Listener implements IWalSyncListener {
  @override
  void onWalUpdated() {}

  @override
  void onWalSynced(Wal wal, {ServerConversation? conversation}) {}
}

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();
  late Directory directory;

  setUpAll(() async {
    directory = await Directory.systemTemp.createTemp('pendant_storage_admission_');
    TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger.setMockMethodCallHandler(
      const MethodChannel('plugins.flutter.io/path_provider'),
      (_) async => directory.path,
    );
  });

  setUp(() async {
    SharedPreferences.setMockInitialValues({});
    await SharedPreferencesUtil.init();
    await WalFileManager.init();
    await DebugLogManager.setEnabled(true);
    await DebugLogManager.clear();
  });

  tearDown(() async {
    // Also drains queued diagnostics before the next test or directory removal.
    await DebugLogManager.clear();
    await DebugLogManager.setEnabled(false);
  });

  tearDownAll(() async {
    TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger.setMockMethodCallHandler(
      const MethodChannel('plugins.flutter.io/path_provider'),
      null,
    );
    await directory.delete(recursive: true);
  });

  WalFrame frame(int counter) => WalFrame(
        payload: [0xAA, counter & 0xFF],
        syncKey: FrameSyncKey([counter & 0xFF, (counter >> 8) & 0xFF, 0]),
      );

  Future<List<Map<String, dynamic>>> eventsOfType(String type) async {
    for (var attempt = 0; attempt < 100; attempt++) {
      final file = await DebugLogManager.getLogFile();
      final events = (await file!.readAsLines())
          .map((line) => jsonDecode(line) as Map<String, dynamic>)
          .where((event) => event['type'] == type || event['level'] == type)
          .toList();
      if (events.isNotEmpty) return events;
      await Future<void>.delayed(const Duration(milliseconds: 10));
    }
    fail('Missing $type telemetry');
  }

  for (final retainedCount in [maxRetainedCaptureWalCount, maxRetainedCaptureWalCount + 3]) {
    test('count cap at $retainedCount WALs still stores pendant frames beyond the 2000-frame buffer', () async {
      final sync = LocalWalSyncImpl(_Listener(), freeDiskBytes: () async => 64 << 30);
      sync.setDeviceInfo('test-pendant', 'Omi');
      final pending = List.generate(
        retainedCount,
        (i) => Wal(
          timerStart: i,
          codec: BleAudioCodec.opus,
          seconds: 10,
          storage: WalStorage.disk,
          status: WalStatus.miss,
        ),
      );
      sync.testWals = pending;
      await sync.enforceRetentionPolicyForTesting();
      expect(sync.retentionRisk?.reason, 'count_cap');
      expect(await sync.ensureStorageAdmission(bytes: 1024, admittedGeneration: sync.sessionGeneration), isTrue);
      sync.releaseStorageAdmission(1024);

      for (var i = 0; i < 2100; i++) {
        sync.onFrameCaptured(frame(i));
      }
      expect(sync.testFrames, hasLength(2100));
      expect(sync.testFrameSynced, everyElement(isFalse));
      final pressure = await eventsOfType('wal_admission_pressure');
      expect(pressure.first['retained_count'], retainedCount);
      expect(pressure.first['blocked_count'], 0);

      await sync.stop();
      final stored = sync.testWals.where((wal) => wal.device == 'test-pendant').toList();
      expect(stored.fold<int>(0, (count, wal) => count + wal.totalFrames), 2100);
      expect(stored.map((wal) => wal.storage), everyElement(WalStorage.disk));
      expect(stored.map((wal) => wal.syncedAt), everyElement(0));
      for (final wal in stored) {
        expect(await File((await Wal.getFilePath(wal.filePath))!).length(), greaterThan(0));
      }
      final index = await WalFileManager.loadWals();
      expect(index, hasLength(retainedCount + stored.length));
      expect(index.where((wal) => wal.device == 'test-pendant').fold<int>(0, (n, wal) => n + wal.totalFrames), 2100);
      expect(pending.take(retainedCount).map((wal) => wal.status), everyElement(WalStatus.miss));
    });
  }

  for (final freeBytes in <int?>[minFreeDiskReserveBytes, null]) {
    test('storage pressure ($freeBytes free bytes) still bounds pendant buffering and reports drops', () async {
      final sync = LocalWalSyncImpl(_Listener(), freeDiskBytes: () async => freeBytes);
      sync.setDeviceInfo('test-pendant', 'Omi');
      expect(await sync.ensureStorageAdmission(bytes: 1024, admittedGeneration: sync.sessionGeneration), isFalse);
      expect(sync.retentionRisk?.reason, freeBytes == null ? 'disk_space_unknown' : 'disk_reserve');
      for (var i = 0; i < 2000; i++) {
        sync.onFrameCaptured(frame(i));
      }
      expect(sync.testFrames, hasLength(2000));
      final last = frame(2000);
      expect(sync.onFrameCaptured(last), same(last));
      expect(sync.testFrames, hasLength(2000));
      final warnings = await eventsOfType('WARN');
      expect(warnings.single['message'], contains('pendant frame dropped'));
      expect(warnings.single['extra']['dropped_count'], 1);
    });
  }

  test('a failed pendant file write still blocks ingress even when the risk is count_cap', () async {
    final sync = LocalWalSyncImpl(_Listener(), freeDiskBytes: () async => 64 << 30);
    sync.setDeviceInfo('test-pendant', 'Omi');
    final buffered = Wal(
      timerStart: 1700000000,
      codec: BleAudioCodec.opus,
      seconds: 40,
      device: 'test-pendant',
      storage: WalStorage.mem,
      totalFrames: 2000,
      data: List.generate(2000, (i) => frame(i).payload),
    );
    sync.testWals = [
      for (var i = 0; i < maxRetainedCaptureWalCount; i++)
        Wal(timerStart: i, codec: BleAudioCodec.opus, seconds: 10, storage: WalStorage.disk),
      buffered,
    ];
    await sync.enforceRetentionPolicyForTesting();
    // A directory at the planned file path makes the actual write fail after
    // a successful free-space probe, engaging the separate storage latch.
    final obstruction = await Directory('${directory.path}/${buffered.getFileName()}').create();
    addTearDown(() => obstruction.delete());
    await sync.stop();
    expect(sync.retentionRisk?.reason, 'count_cap');
    expect(buffered.storage, WalStorage.mem);
    expect(buffered.data, hasLength(2000));
    sync.onFrameCaptured(frame(2000));
    expect(sync.testFrames, isEmpty, reason: 'the full memory WAL counts toward the storage-blocked buffer');
    expect((await eventsOfType('WARN')).single['extra']['dropped_count'], 1);
  });

  test('the real flush reports one count-only observation per nonempty pendant drop window', () async {
    final events = <RegisteredEvent>[];
    final sync = LocalWalSyncImpl(
      _Listener(),
      freeDiskBytes: () async => minFreeDiskReserveBytes,
      backlogTelemetry: WalBacklogTelemetry(emit: events.add),
    );
    sync.setDeviceInfo('test-pendant', 'Omi');
    expect(await sync.ensureStorageAdmission(bytes: 1024, admittedGeneration: sync.sessionGeneration), isFalse);
    for (var i = 0; i < 2003; i++) {
      sync.onFrameCaptured(frame(i));
    }
    expect(events, isEmpty);
    await sync.stop();
    expect(events.whereType<PendantFramesDropped>().map((e) => e.properties), [
      {'count': 3, 'reason': 'disk_reserve'},
    ]);
    expect(sync.testWals.single.storage, WalStorage.mem);
    expect(sync.testWals.single.totalFrames, 2000);
    sync.onFrameCaptured(frame(2003));
    await sync.stop();
    expect(events.whereType<PendantFramesDropped>().last.properties, {'count': 1, 'reason': 'disk_reserve'});
    expect(events.whereType<PendantFramesDropped>(), hasLength(2));
  });
}
