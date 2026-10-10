import 'dart:async';
import 'dart:convert';
import 'dart:io';

import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:omi/backend/schema/bt_device/bt_device.dart';
import 'package:omi/services/wals/wal.dart';
import 'package:omi/utils/wal_file_manager.dart';

class _FailingCopyFile implements File {
  _FailingCopyFile(this._real);

  final File _real;

  @override
  String get path => _real.path;

  @override
  bool existsSync() => _real.existsSync();

  @override
  Future<String> readAsString({Encoding encoding = utf8}) => _real.readAsString(encoding: encoding);

  @override
  Future<File> copy(String newPath) async {
    throw const FileSystemException('simulated copy failure');
  }

  @override
  Future<File> writeAsString(
    String contents, {
    FileMode mode = FileMode.write,
    Encoding encoding = utf8,
    bool flush = false,
  }) => _real.writeAsString(contents, mode: mode, encoding: encoding, flush: flush);

  @override
  Future<File> rename(String newPath) => _real.rename(newPath);

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
    tempDir = await Directory.systemTemp.createTemp('wal_error_path_test_');
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

  test('_createBackup handles FormatException when WAL file is malformed', () async {
    await WalFileManager.saveWals([_wal(1000)]);
    await WalFileManager.saveWals([_wal(1000), _wal(2000)]);

    final beforeBackup = backupFile.readAsStringSync();

    // Corrupt the WAL file so it's invalid JSON
    walFile.writeAsStringSync('{ malformed json');

    // A save triggers _createBackup, which reads the invalid JSON and throws FormatException
    await WalFileManager.saveWals([_wal(3000)]);

    // The backup should remain unchanged (the bad file was not backed up)
    expect(backupFile.readAsStringSync(), beforeBackup);
  });

  test('_createBackup handles FileSystemException when WAL file fails to copy', () async {
    await WalFileManager.saveWals([_wal(1000)]);
    await WalFileManager.saveWals([_wal(1000), _wal(2000)]); // Ensures backupFile exists before we read it
    final beforeBackup = backupFile.readAsStringSync();

    await IOOverrides.runZoned(() async {
      await WalFileManager.init();
      // The save operation calls _createBackup, which will fail during copy()
      await WalFileManager.saveWals([_wal(1000), _wal(2000), _wal(3000)]);
    }, createFile: (path) {
      final realFile = Zone.root.run(() => File(path));
      if (path.endsWith('wals.json')) {
        return _FailingCopyFile(realFile);
      }
      return realFile;
    });

    // We verify the saveWals completed successfully (no uncaught exception)
    // The backup file shouldn't be updated due to the simulated copy failure
    expect(backupFile.readAsStringSync(), beforeBackup);
  });
}
