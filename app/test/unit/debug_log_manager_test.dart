import 'dart:convert';
import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:path_provider_platform_interface/path_provider_platform_interface.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:omi/backend/preferences.dart';
import 'package:omi/utils/debug_log_manager.dart';

class _Documents extends PathProviderPlatform {
  _Documents(this.path);

  final String path;

  @override
  Future<String> getApplicationDocumentsPath() async => path;
}

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  late Directory directory;
  late PathProviderPlatform previousProvider;

  // The manager caches its file for the process lifetime, so share one temp
  // directory across these tests and await every operation before removing it.
  setUpAll(() async {
    directory = await Directory.systemTemp.createTemp('debug-logs-');
    previousProvider = PathProviderPlatform.instance;
    PathProviderPlatform.instance = _Documents(directory.path);
    SharedPreferences.setMockInitialValues({'devLogsToFileEnabled': true});
    await SharedPreferencesUtil.init();
  });

  tearDownAll(() async {
    PathProviderPlatform.instance = previousProvider;
    await directory.delete(recursive: true);
  });

  test('50 concurrent events initialize the file and preserve complete JSON lines in order', () async {
    // Do not pre-initialize the manager: the first append must also be queued.
    final payloads = List.generate(50, (i) => 'payload-$i-${'x' * (32 * 1024)}-end-$i');
    await Future.wait(
      List.generate(payloads.length, (i) => DebugLogManager.logEvent('concurrent', {'id': i, 'payload': payloads[i]})),
    );

    final file = (await DebugLogManager.getLogFile())!;
    final contents = await file.readAsString();
    expect(contents.endsWith('\n'), isTrue);
    final lines = const LineSplitter().convert(contents);
    expect(lines, hasLength(50));
    final records = lines.map((line) => jsonDecode(line) as Map<String, dynamic>).toList();
    expect(records.map((record) => record['id']), orderedEquals(List.generate(50, (i) => i)));
    for (var i = 0; i < records.length; i++) {
      expect(records[i]['payload'], payloads[i]);
      expect(records[i]['type'], 'concurrent');
      expect(records[i]['level'], 'EVENT');
      expect(records[i]['timestamp'], matches(r'^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}Z$'));
    }
    await DebugLogManager.clear();
  });

  test('rotation truncates a file over the 5MB cap before appending', () async {
    final file = (await DebugLogManager.getLogFile())!;
    await file.writeAsString('x' * (5 * 1024 * 1024 + 1));

    await Future.wait(List.generate(50, (i) => DebugLogManager.logEvent('after_rotation', {'id': i})));

    final lines = await file.readAsLines();
    expect(lines, hasLength(50));
    final records = lines.map((line) => jsonDecode(line) as Map<String, dynamic>).toList();
    expect(records.map((record) => record['id']), orderedEquals(List.generate(50, (i) => i)));
    expect(records.every((record) => record['type'] == 'after_rotation'), isTrue);
    await DebugLogManager.clear();
  });

  test('clear waits for earlier appends and precedes later appends', () async {
    await Future.wait([
      ...List.generate(50, (i) => DebugLogManager.logInfo('before-clear-$i')),
      DebugLogManager.clear(),
      DebugLogManager.logWarning('after-clear'),
    ]);

    final lines = await (await DebugLogManager.getLogFile())!.readAsLines();
    expect(lines, hasLength(1));
    expect((jsonDecode(lines.single) as Map<String, dynamic>)['message'], 'after-clear');
    await DebugLogManager.clear();
  });

  test('disabled logging is a no-op', () async {
    await DebugLogManager.setEnabled(false);
    try {
      await DebugLogManager.logEvent('disabled', {'payload': 'ignored'});
      expect(await (await DebugLogManager.getLogFile())!.readAsString(), isEmpty);
    } finally {
      await DebugLogManager.setEnabled(true);
    }
  });

  test('a failed file write is swallowed and subsequent writes still complete', () async {
    final file = (await DebugLogManager.getLogFile())!;
    await file.delete();
    final obstruction = await Directory(file.path).create();
    try {
      await DebugLogManager.logError(StateError('failed-write'));
    } finally {
      await obstruction.delete();
    }

    await DebugLogManager.logError(StateError('recovered'));
    final lines = await file.readAsLines();
    expect(lines, hasLength(1));
    expect((jsonDecode(lines.single) as Map<String, dynamic>)['message'], 'Bad state: recovered');
    await DebugLogManager.clear();
  });
}
