import 'dart:convert';
import 'dart:io';
import 'dart:isolate';

import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:omi/backend/schema/bt_device/bt_device.dart';
import 'package:omi/services/wals/wal.dart';
import 'package:omi/utils/off_ui_isolate.dart';
import 'package:omi/utils/wal_file_manager.dart';

Wal _wal(int timerStart) => Wal(
    timerStart: timerStart, codec: BleAudioCodec.opus, seconds: 60, status: WalStatus.miss, storage: WalStorage.disk);

class _IsolateStampedWal extends Wal {
  _IsolateStampedWal(int timerStart)
      : super(timerStart: timerStart, codec: BleAudioCodec.opus, seconds: 10, storage: WalStorage.disk);

  @override
  Map<String, dynamic> toJson() => {...super.toJson(), 'serialized_on': Isolate.current.debugName};
}

/// The WAL index is rewritten whole on every save and grows with every kept
/// recording, so its save path must stay off the UI isolate's critical path
/// without weakening the last-write-wins and backup guarantees.
void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  late Directory tempDir;
  late File walFile;
  late File backupFile;
  final defaultThreshold = WalFileManager.backgroundEncodeThreshold;

  setUp(() async {
    tempDir = await Directory.systemTemp.createTemp('wal_save_cost_test_');
    TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger.setMockMethodCallHandler(
      const MethodChannel('plugins.flutter.io/path_provider'),
      (MethodCall methodCall) async {
        if (methodCall.method == 'getApplicationDocumentsDirectory') return tempDir.path;
        return null;
      },
    );
    await WalFileManager.init();
    walFile = File('${tempDir.path}/wals.json');
    backupFile = File('${tempDir.path}/wals_backup.json');
  });

  tearDown(() async {
    WalFileManager.backgroundEncodeThreshold = defaultThreshold;
    TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger.setMockMethodCallHandler(
      const MethodChannel('plugins.flutter.io/path_provider'),
      null,
    );
    if (tempDir.existsSync()) tempDir.deleteSync(recursive: true);
  });

  test('back-to-back saves collapse into the newest snapshot', () async {
    final first = WalFileManager.saveWals([_wal(1000)]);
    // None of these has started writing yet; only the newest snapshot needs writing.
    final second = WalFileManager.saveWals([_wal(1000), _wal(2000)]);
    final third = WalFileManager.saveWals([_wal(1000), _wal(2000), _wal(3000)]);
    expect(identical(second, third), isTrue, reason: 'a queued save is replaced, not appended');

    expect(await Future.wait([first, second, third]), [true, true, true]);
    expect((await WalFileManager.loadWals()).map((w) => w.timerStart), [1000, 2000, 3000]);
  });

  test('a replaced caller resolves after the newest snapshot is on disk, as serial writes would leave it', () async {
    final first = WalFileManager.saveWals([_wal(1000)]);
    final replaced = WalFileManager.saveWals([_wal(1000), _wal(2000)]);
    // Not a superset: the newest snapshot drops 2000, as a delete would.
    final newest = WalFileManager.saveWals([_wal(3000)]);

    await replaced;
    final onDisk = jsonDecode(walFile.readAsStringSync()) as Map<String, dynamic>;
    expect((onDisk['wals'] as List).map((w) => w['timer_start']), [3000], reason: 'last write wins, as before');
    final backup = jsonDecode(backupFile.readAsStringSync()) as Map<String, dynamic>;
    expect((backup['wals'] as List).map((w) => w['timer_start']), [1000, 2000],
        reason: 'the newest replaced snapshot is the backup');
    await Future.wait([first, newest]);
  });

  test('collapsed saves keep the newest superseded snapshot as the backup', () async {
    // A fresh install: no index yet, so serial writes would have left the
    // first snapshot as the backup.
    final first = WalFileManager.saveWals([_wal(1000)]);
    final second = WalFileManager.saveWals([_wal(1000), _wal(2000)]);
    await Future.wait([first, second]);

    final backup = jsonDecode(backupFile.readAsStringSync()) as Map<String, dynamic>;
    expect((backup['wals'] as List).map((w) => w['timer_start']), [1000]);
    // And the index falls back to it when the main file is lost.
    walFile.writeAsStringSync('');
    expect((await WalFileManager.loadWals()).map((w) => w.timerStart), [1000]);
  });

  test('a failing superseded backup never blocks the index write', () async {
    // The backup target cannot be replaced (it is a directory).
    Directory(backupFile.path).createSync();
    final first = WalFileManager.saveWals([_wal(1000)]);
    final second = WalFileManager.saveWals([_wal(1000), _wal(2000)]);

    expect(await Future.wait([first, second]), [true, true]);
    expect((await WalFileManager.loadWals()).map((w) => w.timerStart), [1000, 2000]);
  });

  test('a large index is encoded off the UI isolate and round-trips', () async {
    WalFileManager.backgroundEncodeThreshold = 2;
    offUiIsolateFallbacks = 0;
    final wals = [for (var i = 0; i < 50; i++) _wal(1000 + i)];

    expect(await WalFileManager.saveWals(wals), isTrue);
    expect(await WalFileManager.saveWals([...wals, _wal(5000)]), isTrue);

    expect((await WalFileManager.loadWals()).length, 51);
    final backup = jsonDecode(backupFile.readAsStringSync()) as Map<String, dynamic>;
    expect((backup['wals'] as List).length, 50);
    expect(offUiIsolateFallbacks, 0);
  });

  test('large main and superseded backup snapshots build every toJson map on the worker', () async {
    offUiIsolateFallbacks = 0;
    final wals = List<Wal>.generate(5000, (i) => _IsolateStampedWal(1000 + i));
    // Force the coalescing path, whose superseded snapshot is serialized into
    // the backup separately from the final index.
    final first = WalFileManager.saveWals(wals);
    final newest = WalFileManager.saveWals([...wals, _IsolateStampedWal(7000)]);
    expect(await Future.wait([first, newest]), [true, true]);

    for (final file in [walFile, backupFile]) {
      final index = jsonDecode(await file.readAsString()) as Map<String, dynamic>;
      final rows = index['wals'] as List;
      expect(rows, hasLength(identical(file, walFile) ? 5001 : 5000));
      expect(rows.map((row) => row['serialized_on']), everyElement('wal_index_encode'));
    }
    expect(await WalFileManager.loadWals(), hasLength(5001));
    expect(offUiIsolateFallbacks, 0, reason: 'serialization must never silently fall back to the UI isolate');
  });

  // Guard for the skip-revalidation shortcut in _createBackup.
  test('an index changed behind our back is re-validated before it may become the backup', () async {
    await WalFileManager.saveWals([_wal(1000)]);
    await WalFileManager.saveWals([_wal(1000), _wal(2000)]);
    final good = backupFile.readAsStringSync();
    // Same process, but the file no longer matches what this process wrote.
    walFile.writeAsStringSync('{"version": 1, "wals": [');

    await WalFileManager.saveWals([_wal(1000), _wal(2000), _wal(3000)]);

    expect(backupFile.readAsStringSync(), good);
  });
}
