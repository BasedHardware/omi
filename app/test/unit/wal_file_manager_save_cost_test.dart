import 'dart:convert';
import 'dart:io';

import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:omi/backend/schema/bt_device/bt_device.dart';
import 'package:omi/services/wals/wal.dart';
import 'package:omi/utils/off_ui_isolate.dart';
import 'package:omi/utils/wal_file_manager.dart';

Wal _wal(int timerStart) => Wal(
    timerStart: timerStart, codec: BleAudioCodec.opus, seconds: 60, status: WalStatus.miss, storage: WalStorage.disk);

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

  // Guard (also true before coalescing): a replaced caller must not resolve early.
  test('a superseded caller resolves only after a write that contains its snapshot', () async {
    final inFlight = WalFileManager.saveWals([_wal(1000)]);
    final superseded = WalFileManager.saveWals([_wal(1000), _wal(2000)]);
    WalFileManager.saveWals([_wal(1000), _wal(2000), _wal(3000)]);

    await superseded;
    final onDisk = jsonDecode(walFile.readAsStringSync()) as Map<String, dynamic>;
    expect((onDisk['wals'] as List).map((w) => w['timer_start']), containsAll([1000, 2000]));
    await inFlight;
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
