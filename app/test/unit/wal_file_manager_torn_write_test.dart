import 'dart:async';
import 'dart:convert';
import 'dart:io';

import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:omi/backend/schema/bt_device/bt_device.dart';
import 'package:omi/services/wals/wal.dart';
import 'package:omi/utils/wal_file_manager.dart';

class _TornWriteFile implements File {
  _TornWriteFile(this._real);

  final File _real;

  @override
  String get path => _real.path;

  @override
  bool existsSync() => _real.existsSync();

  @override
  Future<String> readAsString({Encoding encoding = utf8}) => _real.readAsString(encoding: encoding);

  @override
  Future<File> copy(String newPath) => _real.copy(newPath);

  @override
  Future<File> rename(String newPath) => _real.rename(newPath);

  @override
  Future<File> writeAsString(
    String contents, {
    FileMode mode = FileMode.write,
    Encoding encoding = utf8,
    bool flush = false,
  }) async {
    await _real.writeAsString('');
    throw const FileSystemException('simulated crash mid-write');
  }

  @override
  dynamic noSuchMethod(Invocation invocation) => super.noSuchMethod(invocation);
}

Wal _wal(int timerStart) => Wal(
    timerStart: timerStart, codec: BleAudioCodec.opus, seconds: 60, status: WalStatus.miss, storage: WalStorage.disk);

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  late Directory tempDir;
  late File walFile;
  late File backupFile;

  setUp(() async {
    tempDir = await Directory.systemTemp.createTemp('wal_torn_write_test_');
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
    TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger.setMockMethodCallHandler(
      const MethodChannel('plugins.flutter.io/path_provider'),
      null,
    );
    if (tempDir.existsSync()) tempDir.deleteSync(recursive: true);
  });

  test('a save that dies mid-write leaves the stored index readable', () async {
    await WalFileManager.saveWals([_wal(1000)]);
    final before = walFile.readAsStringSync();

    await IOOverrides.runZoned(() async {
      await WalFileManager.init();
      await expectLater(WalFileManager.saveWals([_wal(1000), _wal(2000)]), throwsA(isA<FileSystemException>()));
    }, createFile: (path) => _TornWriteFile(Zone.root.run(() => File(path))));

    await WalFileManager.init();
    expect(walFile.readAsStringSync(), before);
    expect((await WalFileManager.loadWals()).map((w) => w.timerStart), [1000]);
  });

  test('an empty index falls back to the backup instead of dropping every WAL', () async {
    await WalFileManager.saveWals([_wal(1000)]);
    await WalFileManager.saveWals([_wal(1000), _wal(2000)]);
    walFile.writeAsStringSync('');

    expect((await WalFileManager.loadWals()).map((w) => w.timerStart), [1000]);
  });

  test('a half written index falls back to the backup', () async {
    await WalFileManager.saveWals([_wal(1000)]);
    await WalFileManager.saveWals([_wal(1000), _wal(2000)]);
    final full = walFile.readAsStringSync();
    walFile.writeAsStringSync(full.substring(0, full.length ~/ 2));

    expect((await WalFileManager.loadWals()).map((w) => w.timerStart), [1000]);
  });

  test('an empty index with no backup still loads as empty', () async {
    walFile.writeAsStringSync('');
    expect(backupFile.existsSync(), isFalse);

    expect(await WalFileManager.loadWals(), isEmpty);
  });

  test('overlapping saves both complete and the later one wins', () async {
    await Future.wait([
      WalFileManager.saveWals([_wal(1000)]),
      WalFileManager.saveWals([_wal(1000), _wal(2000)]),
    ]);

    expect((await WalFileManager.loadWals()).map((w) => w.timerStart), [1000, 2000]);
  });

  test('saving after an empty index keeps the good backup', () async {
    await WalFileManager.saveWals([_wal(1000)]);
    await WalFileManager.saveWals([_wal(1000), _wal(2000)]);
    walFile.writeAsStringSync('');

    final recovered = await WalFileManager.loadWals();
    await WalFileManager.saveWals([...recovered, _wal(3000)]);

    final backup = jsonDecode(backupFile.readAsStringSync()) as Map<String, dynamic>;
    expect((backup['wals'] as List).map((w) => w['timer_start']), [1000]);
  });
}
