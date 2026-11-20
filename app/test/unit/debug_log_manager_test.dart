import 'dart:convert';
import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:path_provider_platform_interface/path_provider_platform_interface.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:omi/backend/preferences.dart';
import 'package:omi/utils/debug_log_manager.dart';
import 'package:omi/services/auth/auth_token_result.dart';
import 'package:omi/services/notifications/fcm_token_registration.dart';

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
      await logPushRegistration(PushRegistrationStage.apns, PushRegistrationResult.unavailable);
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
      await logPushRegistration(PushRegistrationStage.persistence, PushRegistrationResult.accepted);
    } finally {
      await obstruction.delete();
    }

    await DebugLogManager.logError(StateError('recovered'));
    final lines = await file.readAsLines();
    expect(lines, hasLength(1));
    expect((jsonDecode(lines.single) as Map<String, dynamic>)['message'], 'Bad state: recovered');
    await DebugLogManager.clear();
  });
  test('registration failures reach the developer export without credential or exception text', () async {
    const owner = AuthSessionSnapshot(ownerUid: 'private-account', generation: 1);
    final registrar = FcmTokenRegistration(
      capture: () => owner,
      isCurrent: (_) => true,
      readApns: () async => 'private-apns-token',
      readToken: () async => throw StateError('private-fcm-token and private-account'),
      readTimeZone: () async => 'private-time-zone',
      persist: (_, __, ___) async => true,
      requiresApns: true,
      retryDelays: const [],
    );
    try {
      await registrar.refresh();
      // Await the same production write queue before reading the export file.
      await logPushRegistration(PushRegistrationStage.http, PushRegistrationResult.declined, httpStatus: 503);
      final file = (await DebugLogManager.listLogFiles()).first;
      final raw = await file.readAsString();
      expect(raw, isNot(contains('private-')));
      expect(raw, isNot(contains('StateError')));
      final rows = const LineSplitter().convert(raw).map((line) => jsonDecode(line) as Map<String, dynamic>).toList();
      expect(rows.map((row) => (row['stage'], row['result'])), [
        ('token', 'exception'),
        ('retry', 'exhausted'),
        ('http', 'declined'),
      ]);
      expect(rows.last['http_status'], 503);
      for (final row in rows) {
        expect(row.keys.toSet().difference({'timestamp', 'level', 'type', 'stage', 'result', 'http_status'}), isEmpty);
        expect(row['type'], 'push_registration');
      }
    } finally {
      registrar.dispose();
      await DebugLogManager.clear();
    }
  });
}
