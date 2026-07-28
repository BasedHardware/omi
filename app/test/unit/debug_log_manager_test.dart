import 'dart:convert';
import 'dart:io';

import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:omi/backend/preferences.dart';
import 'package:omi/utils/debug_log_manager.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  const pathProviderChannel = MethodChannel(
    'plugins.flutter.io/path_provider',
  );
  late Directory tempDir;
  var activeMutations = 0;
  var maximumActiveMutations = 0;

  Future<void> observePhysicalMutation(
    Future<void> Function() mutation,
  ) async {
    activeMutations++;
    if (activeMutations > maximumActiveMutations) {
      maximumActiveMutations = activeMutations;
    }
    // Give every concurrently admitted mutation a deterministic chance to
    // overlap before touching the file.
    await Future<void>.delayed(Duration.zero);
    try {
      await mutation();
    } finally {
      activeMutations--;
    }
  }

  setUp(() async {
    SharedPreferences.setMockInitialValues({
      'devLogsToFileEnabled': true,
    });
    await SharedPreferencesUtil.init();
    tempDir = await Directory.systemTemp.createTemp('debug_log_manager_');
    TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger.setMockMethodCallHandler(pathProviderChannel,
        (call) async {
      if (call.method == 'getApplicationDocumentsDirectory') {
        return tempDir.path;
      }
      return null;
    });
    activeMutations = 0;
    maximumActiveMutations = 0;
    await DebugLogManager.resetForTesting(
      physicalMutationRunner: observePhysicalMutation,
    );
  });

  tearDown(() async {
    await DebugLogManager.resetForTesting();
    TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger
        .setMockMethodCallHandler(pathProviderChannel, null);
    if (await tempDir.exists()) {
      await tempDir.delete(recursive: true);
    }
  });

  test('concurrent events are written once as valid JSON by one physical writer', () async {
    const eventCount = 200;

    await Future.wait([
      for (var index = 0; index < eventCount; index++)
        DebugLogManager.logEvent('concurrent_write', {
          'record_id': index,
        }),
    ]);

    final file = await DebugLogManager.getLogFile();
    expect(file, isNotNull);
    final lines = await file!.readAsLines();
    expect(lines, hasLength(eventCount));
    final records = lines.map((line) => jsonDecode(line) as Map<String, dynamic>).toList(growable: false);
    expect(
      records.map((record) => record['type']).toSet(),
      {'concurrent_write'},
    );
    final ids = records.map((record) => record['record_id'] as int).toList();
    expect(ids.toSet(), {for (var index = 0; index < eventCount; index++) index});
    expect(maximumActiveMutations, 1);
  });

  test('clear is ordered between earlier and later appends', () async {
    await Future.wait([
      DebugLogManager.logEvent('before_clear', {'record_id': 1}),
      DebugLogManager.clear(),
      DebugLogManager.logEvent('after_clear', {'record_id': 2}),
    ]);

    final file = await DebugLogManager.getLogFile();
    final lines = await file!.readAsLines();
    expect(lines, hasLength(1));
    expect(jsonDecode(lines.single), containsPair('type', 'after_clear'));
    expect(maximumActiveMutations, 1);
  });
}
