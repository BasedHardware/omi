import 'dart:io';

import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/services/audio_sources/audio_source.dart';
import 'package:omi/services/wals/local_wal_sync.dart';
import 'package:omi/services/wals/wal.dart';
import 'package:omi/services/wals/wal_interfaces.dart';
import 'package:omi/utils/wal_file_manager.dart';

import '../support/capture/virtual_capture_time.dart';

class _Listener implements IWalSyncListener {
  @override
  void onWalSynced(Wal wal, {ServerConversation? conversation}) {}

  @override
  void onWalUpdated() {}
}

/// #25871: a disk-full index write inside a periodic flush/drain has no caller
/// to catch it. It must not surface as an uncaught async error, and the next
/// tick must still commit the retained rows once space returns.
void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  late Directory tempDir;
  late ManualScheduler scheduler;
  late LocalWalSyncImpl sync;
  late bool diskFull;
  late int saveAttempts;

  setUp(() async {
    SharedPreferences.setMockInitialValues({});
    await SharedPreferencesUtil.init();
    tempDir = await Directory.systemTemp.createTemp('wal_timer_index_failure_');
    TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger.setMockMethodCallHandler(
      const MethodChannel('plugins.flutter.io/path_provider'),
      (MethodCall call) async {
        if (call.method == 'getApplicationDocumentsDirectory') return tempDir.path;
        return null;
      },
    );
    await WalFileManager.init();
    scheduler = ManualScheduler(clock: VirtualClock(DateTime.utc(2026, 11, 20)));
    diskFull = false;
    saveAttempts = 0;
    sync = LocalWalSyncImpl(
      _Listener(),
      periodic: scheduler.periodic,
      freeDiskBytes: () async => 1 << 40,
      persistWals: (wals) async {
        saveAttempts++;
        if (diskFull) {
          throw const FileSystemException('writeFrom failed', 'wals.json.tmp', OSError('No space left on device', 28));
        }
        await WalFileManager.saveWals(wals);
      },
    );
    sync.setDeviceInfo('phone-mic', 'Phone Microphone');
    sync.start();
    await sync.walReady;
  });

  tearDown(() async {
    diskFull = false;
    await scheduler.waitForCallbackIo();
    await sync.stop();
    TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger.setMockMethodCallHandler(
      const MethodChannel('plugins.flutter.io/path_provider'),
      null,
    );
    if (tempDir.existsSync()) tempDir.deleteSync(recursive: true);
  });

  void capture(int frames) {
    for (var i = 0; i < frames; i++) {
      sync.onFrameCaptured(WalFrame(payload: [0xAA, i & 0xFF], syncKey: FrameSyncKey([i & 0xFF, (i >> 8) & 0xFF])));
    }
  }

  test('periodic drain swallows a disk-full index save and retries on the next tick', () async {
    capture(1000);
    diskFull = true;

    scheduler.elapse(const Duration(seconds: 10));
    await expectLater(scheduler.waitForCallbackIo(), completes);

    expect(saveAttempts, greaterThan(0), reason: 'the drain reached the index save');
    final wal = sync.testWals.single;
    expect(wal.data, isNotEmpty, reason: 'RAM copy is kept until an index save succeeds');
    expect(await WalFileManager.loadIndexedWals(), isEmpty, reason: 'nothing was committed');

    // The sealed tail leaves no live frames, so the periodic flush retries it.
    diskFull = false;
    scheduler.elapse(const Duration(seconds: flushIntervalInSeconds + newFrameSyncDelaySeconds));
    await scheduler.waitForCallbackIo();

    final indexed = await WalFileManager.loadIndexedWals();
    expect(indexed.map((w) => w.id), contains(wal.id), reason: 'the retained row commits once space returns');
    expect(wal.data, isEmpty);
  });

  test('periodic flush swallows a disk-full index save', () async {
    capture(1000);
    diskFull = true;

    scheduler.elapse(const Duration(seconds: flushIntervalInSeconds + newFrameSyncDelaySeconds));
    await expectLater(scheduler.waitForCallbackIo(), completes);
    expect(saveAttempts, greaterThan(0));
  });
}
