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
  late String documentsPath;

  setUpAll(() async {
    directory = await Directory.systemTemp.createTemp('pendant_storage_admission_');
    documentsPath = directory.path;
    TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger.setMockMethodCallHandler(
      const MethodChannel('plugins.flutter.io/path_provider'),
      (_) async => documentsPath,
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
    final telemetry = <RegisteredEvent>[];
    final backpressure = <bool>[];
    final sync = LocalWalSyncImpl(
      _Listener(),
      freeDiskBytes: () async => 64 << 30,
      backlogTelemetry: WalBacklogTelemetry(emit: telemetry.add),
    );
    sync.onPendantStorageBackpressureChanged = backpressure.add;
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
    // Point Documents at a regular file: the free-space probe succeeds, while
    // every candidate WAL path has an invalid parent, so its actual write fails
    // even when the receipt manager adds a fresh managed-name discriminator.
    final blockedDocuments = File('${directory.path}/blocked-documents');
    await blockedDocuments.writeAsString('not a directory');
    final originalDocumentsPath = documentsPath;
    documentsPath = blockedDocuments.path;
    try {
      await sync.onAudioCodecChanged(BleAudioCodec.opus);
      expect(sync.retentionRisk?.reason, 'count_cap');
      expect(buffered.storage, WalStorage.mem);
      expect(buffered.data, hasLength(2000));
      expect(backpressure, [true], reason: 'a failed write suspends the physical capture source');
      for (var counter = 2000; counter < 2256; counter++) {
        sync.onFrameCaptured(frame(counter));
        expect(sync.lastFrameAccepted, isTrue);
      }
      expect(sync.testFrames, hasLength(256));
      expect(
        sync.testFrames.map((captured) => captured.syncKey.bytes[0] | (captured.syncKey.bytes[1] << 8)),
        orderedEquals(List.generate(256, (i) => i + 2000)),
      );
      expect(buffered.totalFrames + sync.testFrames.length, 2256,
          reason: 'accepted frames stay in a fixed, bounded in-flight allowance');
      final beyondBound = frame(2256);
      expect(sync.onFrameCaptured(beyondBound), same(beyondBound));
      expect(sync.lastFrameAccepted, isFalse);
      expect(sync.testFrames, hasLength(256));
      await sync.onAudioCodecChanged(BleAudioCodec.opus);
      expect(
        telemetry.whereType<PendantFramesDropped>().map((event) => event.properties),
        [
          {'count': 1, 'reason': 'storage_write_failed'},
        ],
      );
    } finally {
      documentsPath = originalDocumentsPath;
      await blockedDocuments.delete();
    }
  });

  test('the real flush preserves bounded backpressure frames after its initial drop window', () async {
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
    await sync.onAudioCodecChanged(BleAudioCodec.opus);
    expect(events.whereType<PendantFramesDropped>().map((e) => e.properties), [
      {'count': 3, 'reason': 'disk_reserve'},
    ]);
    expect(sync.testWals.single.storage, WalStorage.mem);
    expect(sync.testWals.single.totalFrames, 2000);
    sync.onFrameCaptured(frame(2003));
    await sync.onAudioCodecChanged(BleAudioCodec.opus);
    expect(events.whereType<PendantFramesDropped>().single.properties, {'count': 3, 'reason': 'disk_reserve'});
    expect(sync.testWals.fold<int>(0, (count, wal) => count + wal.totalFrames), 2001,
        reason: 'the accepted frame stays retained while storage backpressure is active');
  });
}
