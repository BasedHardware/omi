import 'dart:io';

import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/bt_device/bt_device.dart';
import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/services/audio_sources/audio_source.dart';
import 'package:omi/services/wals/local_wal_sync.dart';
import 'package:omi/services/wals/wal.dart';
import 'package:omi/services/wals/wal_interfaces.dart';
import 'package:omi/utils/wal_file_manager.dart';

class _MockListener implements IWalSyncListener {
  @override
  void onWalUpdated() {}

  @override
  void onWalSynced(Wal wal, {ServerConversation? conversation}) {}
}

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  late Directory tempDir;

  setUp(() async {
    SharedPreferences.setMockInitialValues({});
    await SharedPreferencesUtil.init();
    tempDir = await Directory.systemTemp.createTemp('local_durability_');
    TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger.setMockMethodCallHandler(
      const MethodChannel('plugins.flutter.io/path_provider'),
      (MethodCall call) async {
        if (call.method == 'getApplicationDocumentsDirectory') return tempDir.path;
        return null;
      },
    );
    await WalFileManager.init();
  });

  tearDown(() async {
    TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger.setMockMethodCallHandler(
      const MethodChannel('plugins.flutter.io/path_provider'),
      null,
    );
    if (tempDir.existsSync()) tempDir.deleteSync(recursive: true);
  });

  WalFrame frame(int counter, int fragment) => WalFrame(
        payload: [0xAA, counter & 0xFF],
        syncKey: FrameSyncKey([counter & 0xFF, (counter >> 8) & 0xFF, fragment]),
      );

  List<File> audioFiles() => tempDir.listSync().whereType<File>().where((f) => f.path.endsWith('.bin')).toList();

  test('finalizeCurrentSession produces a fsynced audio file AND a persisted index entry', () async {
    final sync = LocalWalSyncImpl(_MockListener());
    sync.setDeviceInfo('devkit-1', 'Omi DevKit');
    sync.start();
    await sync.walReady;
    for (var i = 0; i < 50; i++) {
      sync.onFrameCaptured(frame(i, 0));
    }

    await sync.finalizeCurrentSession();

    expect(audioFiles(), isNotEmpty, reason: 'durable audio file must exist after finalize');
    final index = await WalFileManager.loadWals();
    expect(index, isNotEmpty, reason: 'index must persist the WAL across restarts');
    expect(index.first.device, 'devkit-1');
    expect(index.first.storage, WalStorage.disk);
    final walFile = File('${tempDir.path}/${index.first.filePath}');
    expect(await walFile.exists(), isTrue);
    expect(await walFile.length(), greaterThan(0));
    await sync.stop();
  });

  test('an app kill before flush leaves no durable WAL — nothing provable is lost', () async {
    final sync = LocalWalSyncImpl(_MockListener());
    sync.setDeviceInfo('devkit-1', 'Omi DevKit');
    sync.start();
    await sync.walReady;
    for (var i = 0; i < 50; i++) {
      sync.onFrameCaptured(frame(i, 0));
    }

    final index = await WalFileManager.loadWals();
    expect(index, isEmpty, reason: 'unflushed frames must not appear durable in the index');
    expect(audioFiles(), isEmpty);
    await sync.stop();
  });

  test('two external WALs colliding on device+timerStart both survive on distinct files', () async {
    final sync = LocalWalSyncImpl(_MockListener());
    sync.setDeviceInfo('devkit-1', 'Omi DevKit');
    sync.start();
    await sync.walReady;

    const ts = 1700000000;
    File makeFile(String name) {
      final f = File('${tempDir.path}/$name');
      f.writeAsBytesSync(List.filled(64, 0xAB), flush: true);
      return f;
    }

    final f1 = makeFile('audio_collision_a.bin');
    final f2 = makeFile('audio_collision_b.bin');

    Wal ext(String path) => Wal(
          timerStart: ts,
          codec: BleAudioCodec.opus,
          seconds: 1,
          status: WalStatus.miss,
          storage: WalStorage.disk,
          filePath: path,
          device: 'devkit-1',
          deviceModel: 'Omi DevKit',
          totalFrames: 10,
        );

    final gen = sync.sessionGeneration;
    await sync.addExternalWal(ext(f1.path.split('/').last), admittedGeneration: gen);
    await sync.addExternalWal(ext(f2.path.split('/').last), admittedGeneration: gen);

    final index = await WalFileManager.loadWals();
    final colliding = index.where((w) => w.timerStart == ts && w.device == 'devkit-1').toList();
    expect(
      colliding,
      hasLength(2),
      reason: 'distinct audio sharing device+timerStart must not be dropped or overwrite',
    );
    expect(colliding.map((w) => w.filePath).toSet(), hasLength(2));
    await sync.stop();
  });

  test('index persists only durable entries — in-memory WALs never reach wals.json', () async {
    final sync = LocalWalSyncImpl(_MockListener());
    sync.setDeviceInfo('devkit-1', 'Omi DevKit');
    sync.start();
    await sync.walReady;
    for (var i = 0; i < 50; i++) {
      sync.onFrameCaptured(frame(i, 0));
    }

    var index = await WalFileManager.loadWals();
    expect(index.where((w) => w.storage == WalStorage.mem), isEmpty);

    await sync.finalizeCurrentSession();
    index = await WalFileManager.loadWals();
    expect(index.where((w) => w.storage == WalStorage.mem), isEmpty);
    expect(index.where((w) => w.storage == WalStorage.disk), isNotEmpty);
    await sync.stop();
  });
}
