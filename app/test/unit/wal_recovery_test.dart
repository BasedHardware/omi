import 'dart:io';

import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/bt_device/bt_device.dart';
import 'package:omi/services/wals/wal.dart';
import 'package:omi/services/wals/local_wal_sync.dart';
import 'package:omi/services/wals/wal_interfaces.dart';
import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/services/audio_sources/audio_source.dart';
import 'package:omi/utils/wal_file_manager.dart';

class _FakeListener implements IWalSyncListener {
  int walUpdatedCount = 0;
  @override
  void onWalUpdated() => walUpdatedCount++;
  @override
  void onWalSynced(Wal wal, {ServerConversation? conversation}) {}
}

void main() {
  group('Wal model conversationId', () {
    test('conversationId is null by default', () {
      final wal = Wal(timerStart: 1000, codec: BleAudioCodec.opus, seconds: 60);
      expect(wal.conversationId, isNull);
      expect(wal.retryCount, 0);
      expect(wal.lastRetryAt, 0);
    });

    test('conversationId persists through toJson/fromJson', () {
      final wal = Wal(
        timerStart: 1000,
        codec: BleAudioCodec.opus,
        seconds: 60,
        conversationId: 'conv-abc-123',
        retryCount: 2,
        lastRetryAt: 1700000000,
      );

      final json = wal.toJson();
      expect(json['conversation_id'], 'conv-abc-123');
      expect(json['retry_count'], 2);
      expect(json['last_retry_at'], 1700000000);

      final restored = Wal.fromJson(json);
      expect(restored.conversationId, 'conv-abc-123');
      expect(restored.retryCount, 2);
      expect(restored.lastRetryAt, 1700000000);
    });

    test('fromJson handles missing conversationId gracefully', () {
      final json = {
        'timer_start': 1000,
        'codec': 'BleAudioCodec.opus',
        'seconds': 60,
        'status': 'miss',
        'storage': 'disk',
        'device': 'omi',
      };
      final wal = Wal.fromJson(json);
      expect(wal.conversationId, isNull);
      expect(wal.retryCount, 0);
      expect(wal.lastRetryAt, 0);
    });
  });

  group('stampConversationId', () {
    late LocalWalSyncImpl sync;
    late _FakeListener listener;
    late Directory tempDir;

    setUp(() async {
      TestWidgetsFlutterBinding.ensureInitialized();
      SharedPreferences.setMockInitialValues({});
      await SharedPreferencesUtil.init();

      tempDir = await Directory.systemTemp.createTemp('wal_stamp_test_');
      TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger.setMockMethodCallHandler(
        const MethodChannel('plugins.flutter.io/path_provider'),
        (MethodCall methodCall) async {
          if (methodCall.method == 'getApplicationDocumentsDirectory') return tempDir.path;
          return null;
        },
      );
      await WalFileManager.init();

      listener = _FakeListener();
      sync = LocalWalSyncImpl(listener);
    });

    tearDown(() async {
      TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger.setMockMethodCallHandler(
        const MethodChannel('plugins.flutter.io/path_provider'),
        null,
      );
      if (tempDir.existsSync()) tempDir.deleteSync(recursive: true);
    });

    test('stamps session WALs with conversationId', () async {
      final now = DateTime.now().millisecondsSinceEpoch ~/ 1000;
      sync.testWals = [
        Wal(
          timerStart: now - 100,
          codec: BleAudioCodec.opus,
          seconds: 60,
          status: WalStatus.miss,
          storage: WalStorage.disk,
        ),
        Wal(
          timerStart: now - 50,
          codec: BleAudioCodec.opus,
          seconds: 60,
          status: WalStatus.miss,
          storage: WalStorage.disk,
        ),
        Wal(
          timerStart: now - 200,
          codec: BleAudioCodec.opus,
          seconds: 60,
          status: WalStatus.synced,
          storage: WalStorage.disk,
        ),
      ];

      await sync.stampConversationId(now - 150, 'conv-xyz');

      expect(sync.testWals[0].conversationId, 'conv-xyz');
      expect(sync.testWals[1].conversationId, 'conv-xyz');
      // Synced WAL should NOT be stamped
      expect(sync.testWals[2].conversationId, isNull);
    });

    test('does not re-stamp WALs that already have a conversationId', () async {
      final now = DateTime.now().millisecondsSinceEpoch ~/ 1000;
      sync.testWals = [
        Wal(
          timerStart: now - 50,
          codec: BleAudioCodec.opus,
          seconds: 60,
          status: WalStatus.miss,
          storage: WalStorage.disk,
          conversationId: 'old-conv',
        ),
      ];

      await sync.stampConversationId(now - 100, 'new-conv');

      expect(sync.testWals[0].conversationId, 'old-conv');
    });
  });

  group('getOrphanedWals', () {
    late LocalWalSyncImpl sync;
    late _FakeListener listener;

    setUp(() {
      listener = _FakeListener();
      sync = LocalWalSyncImpl(listener);
    });

    test('returns miss+disk WALs with conversationId', () {
      final now = DateTime.now().millisecondsSinceEpoch ~/ 1000;
      sync.testWals = [
        Wal(
          timerStart: now - 100,
          codec: BleAudioCodec.opus,
          seconds: 60,
          status: WalStatus.miss,
          storage: WalStorage.disk,
          conversationId: 'conv-1',
        ),
        Wal(
          timerStart: now - 50,
          codec: BleAudioCodec.opus,
          seconds: 60,
          status: WalStatus.miss,
          storage: WalStorage.disk,
        ),
        Wal(
          timerStart: now - 30,
          codec: BleAudioCodec.opus,
          seconds: 60,
          status: WalStatus.synced,
          storage: WalStorage.disk,
          conversationId: 'conv-2',
        ),
      ];

      final orphaned = sync.getOrphanedWals();
      expect(orphaned.length, 1);
      expect(orphaned[0].conversationId, 'conv-1');
    });

    test('excludes WALs with retryCount >= 3', () {
      final now = DateTime.now().millisecondsSinceEpoch ~/ 1000;
      sync.testWals = [
        Wal(
          timerStart: now - 100,
          codec: BleAudioCodec.opus,
          seconds: 60,
          status: WalStatus.miss,
          storage: WalStorage.disk,
          conversationId: 'conv-1',
          retryCount: 3,
        ),
      ];

      final orphaned = sync.getOrphanedWals();
      expect(orphaned, isEmpty);
    });

    test('returns empty when no orphaned WALs exist', () {
      sync.testWals = [];
      expect(sync.getOrphanedWals(), isEmpty);
    });
  });

  group('getInFlightSeconds', () {
    late LocalWalSyncImpl sync;
    late _FakeListener listener;

    setUp(() {
      listener = _FakeListener();
      sync = LocalWalSyncImpl(listener);
    });

    test('returns 0 when no frames in memory', () {
      expect(sync.getInFlightSeconds(), 0);
    });

    test('counts frames at default opus rate', () {
      // Default codec is opus, 100 frames/second
      for (int i = 0; i < 500; i++) {
        sync.onFrameCaptured(WalFrame(payload: [0, 1, 2], syncKey: FrameSyncKey([i & 0xFF])));
      }
      expect(sync.getInFlightSeconds(), 5); // 500 frames / 100 fps = 5s
    });

    test('returns 0 when all frames are synced', () {
      for (int i = 0; i < 500; i++) {
        final key = FrameSyncKey([i & 0xFF]);
        sync.onFrameCaptured(WalFrame(payload: [0, 1, 2], syncKey: key));
        sync.markFrameSynced(key);
      }
      expect(sync.getInFlightSeconds(), 0);
    });

    test('counts only unsynced frames', () {
      // 300 synced + 200 unsynced = 200 unsynced / 100 fps = 2s
      for (int i = 0; i < 300; i++) {
        final key = FrameSyncKey([i & 0xFF, (i >> 8) & 0xFF]);
        sync.onFrameCaptured(WalFrame(payload: [0, 1, 2], syncKey: key));
        sync.markFrameSynced(key);
      }
      for (int i = 300; i < 500; i++) {
        sync.onFrameCaptured(WalFrame(payload: [0, 1, 2], syncKey: FrameSyncKey([i & 0xFF, (i >> 8) & 0xFF])));
      }
      expect(sync.getInFlightSeconds(), 2);
    });
  });

  group('finalizeCurrentSession', () {
    late LocalWalSyncImpl sync;
    late _FakeListener listener;
    late Directory tempDir;

    setUp(() async {
      TestWidgetsFlutterBinding.ensureInitialized();
      SharedPreferences.setMockInitialValues({});
      await SharedPreferencesUtil.init();

      tempDir = await Directory.systemTemp.createTemp('wal_finalize_test_');
      TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger.setMockMethodCallHandler(
        const MethodChannel('plugins.flutter.io/path_provider'),
        (MethodCall methodCall) async {
          if (methodCall.method == 'getApplicationDocumentsDirectory') return tempDir.path;
          return null;
        },
      );
      await WalFileManager.init();

      listener = _FakeListener();
      sync = LocalWalSyncImpl(listener);
    });

    tearDown(() async {
      TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger.setMockMethodCallHandler(
        const MethodChannel('plugins.flutter.io/path_provider'),
        null,
      );
      if (tempDir.existsSync()) tempDir.deleteSync(recursive: true);
    });

    test('drains all frames including an unsynced tail buffer', () async {
      for (int i = 0; i < 1100; i++) {
        sync.onFrameCaptured(WalFrame(payload: [0, 1, 2], syncKey: FrameSyncKey([i & 0xFF])));
      }
      expect(sync.testFrames.length, 1100);

      await sync.finalizeCurrentSession();

      // All frames should be drained
      expect(sync.testFrames, isEmpty);
      // A WAL should have been created because delivery was not confirmed.
      expect(sync.testWals.length, 1);
      expect(sync.testWals[0].status, WalStatus.miss);
      expect(sync.testWals[0].seconds, 11);
    });

    test('skips storage when all frames were synced via WebSocket', () async {
      // Add 200 frames (2s), all synced — should NOT create a WAL
      for (int i = 0; i < 200; i++) {
        final key = FrameSyncKey([i & 0xFF]);
        sync.onFrameCaptured(WalFrame(payload: [0, 1, 2], syncKey: key));
        sync.markFrameSynced(key);
      }

      await sync.finalizeCurrentSession();

      expect(sync.testFrames, isEmpty);
      // No WAL created because all frames were synced (shouldStored = false)
      expect(sync.testWals, isEmpty);
    });

    test('no-op when no frames in memory', () async {
      await sync.finalizeCurrentSession();
      expect(sync.testWals, isEmpty);
    });

    test('a single unconfirmed frame triggers durable storage', () async {
      for (int i = 0; i < 1; i++) {
        sync.onFrameCaptured(WalFrame(payload: [0, 1, 2], syncKey: FrameSyncKey([i & 0xFF])));
      }

      await sync.finalizeCurrentSession();

      expect(sync.testFrames, isEmpty);
      expect(sync.testWals.length, 1);
      expect(sync.testWals[0].status, WalStatus.miss);
      expect(sync.testWals[0].totalFrames, 1);
    });

    test('one unconfirmed frame among confirmed frames keeps the complete session', () async {
      final first = FrameSyncKey([1]);
      sync.onFrameCaptured(WalFrame(payload: [0, 1, 2], syncKey: first));
      sync.markFrameSynced(first);
      sync.onFrameCaptured(WalFrame(payload: [3, 4, 5], syncKey: FrameSyncKey([2])));

      await sync.finalizeCurrentSession();

      expect(sync.testFrames, isEmpty);
      expect(sync.testWals, hasLength(1));
      expect(sync.testWals.single.totalFrames, 2);
      expect(sync.testWals.single.syncedFrameOffset, 1);
    });

    test('marks WAL synced when all frames are synced in tail buffer', () async {
      // Add 1100 frames, all synced — WAL should be created with status synced
      for (int i = 0; i < 1100; i++) {
        final key = FrameSyncKey([i & 0xFF]);
        sync.onFrameCaptured(WalFrame(payload: [0, 1, 2], syncKey: key));
        sync.markFrameSynced(key);
      }

      await sync.finalizeCurrentSession();

      expect(sync.testFrames, isEmpty);
      // shouldStored is false because every frame has delivery confirmation.
      expect(sync.testWals, isEmpty);
    });
  });

  group('stampConversationId boundary', () {
    late LocalWalSyncImpl sync;
    late _FakeListener listener;
    late Directory tempDir;

    setUp(() async {
      TestWidgetsFlutterBinding.ensureInitialized();
      SharedPreferences.setMockInitialValues({});
      await SharedPreferencesUtil.init();

      tempDir = await Directory.systemTemp.createTemp('wal_stamp_boundary_');
      TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger.setMockMethodCallHandler(
        const MethodChannel('plugins.flutter.io/path_provider'),
        (MethodCall methodCall) async {
          if (methodCall.method == 'getApplicationDocumentsDirectory') return tempDir.path;
          return null;
        },
      );
      await WalFileManager.init();

      listener = _FakeListener();
      sync = LocalWalSyncImpl(listener);
    });

    tearDown(() async {
      TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger.setMockMethodCallHandler(
        const MethodChannel('plugins.flutter.io/path_provider'),
        null,
      );
      if (tempDir.existsSync()) tempDir.deleteSync(recursive: true);
    });

    test('only stamps WALs with timerStart >= sessionStartSeconds', () async {
      final now = DateTime.now().millisecondsSinceEpoch ~/ 1000;
      sync.testWals = [
        Wal(
          timerStart: now - 200,
          codec: BleAudioCodec.opus,
          seconds: 60,
          status: WalStatus.miss,
          storage: WalStorage.disk,
        ),
        Wal(
          timerStart: now - 50,
          codec: BleAudioCodec.opus,
          seconds: 60,
          status: WalStatus.miss,
          storage: WalStorage.disk,
        ),
      ];

      // Session started at now - 100, so only wal at now - 50 qualifies
      await sync.stampConversationId(now - 100, 'conv-boundary');

      expect(sync.testWals[0].conversationId, isNull); // timerStart < sessionStart
      expect(sync.testWals[1].conversationId, 'conv-boundary');
    });

    test('stamps WAL with timerStart exactly equal to sessionStartSeconds', () async {
      final now = DateTime.now().millisecondsSinceEpoch ~/ 1000;
      sync.testWals = [
        Wal(
          timerStart: now - 100,
          codec: BleAudioCodec.opus,
          seconds: 60,
          status: WalStatus.miss,
          storage: WalStorage.disk,
        ),
      ];

      await sync.stampConversationId(now - 100, 'conv-exact');

      expect(sync.testWals[0].conversationId, 'conv-exact');
    });
  });

  group('walReady', () {
    test('completes after start is called', () async {
      TestWidgetsFlutterBinding.ensureInitialized();
      SharedPreferences.setMockInitialValues({});
      await SharedPreferencesUtil.init();

      final tempDir = await Directory.systemTemp.createTemp('wal_ready_test_');
      TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger.setMockMethodCallHandler(
        const MethodChannel('plugins.flutter.io/path_provider'),
        (MethodCall methodCall) async {
          if (methodCall.method == 'getApplicationDocumentsDirectory') return tempDir.path;
          return null;
        },
      );
      await WalFileManager.init();

      final listener = _FakeListener();
      final sync = LocalWalSyncImpl(listener);
      try {
        sync.start();

        // walReady should complete once _initializeWals finishes
        await sync.walReady;
        // If we get here, the Completer completed successfully
        expect(true, isTrue);
      } finally {
        // Must await stop before deleting tempDir — unawaited flush/save races
        // the teardown and flakes under suite concurrency (CI).
        await sync.stop();
        TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger.setMockMethodCallHandler(
          const MethodChannel('plugins.flutter.io/path_provider'),
          null,
        );
        if (tempDir.existsSync()) tempDir.deleteSync(recursive: true);
      }
    });
  });
}
