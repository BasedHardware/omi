import 'dart:convert';
import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:omi/startup/boot_journal.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  late Directory directory;
  late BootJournal journal;
  setUp(() async {
    directory = await Directory.systemTemp.createTemp('boot-journal-');
    journal = BootJournal(documents: () async => directory);
  });
  tearDown(() async => directory.delete(recursive: true));

  test('serializes concurrent writes, caps history, and atomically replaces the file', () async {
    await Future.wait(List.generate(40, (index) => journal.record('stage_$index', 'completed')));
    final entries = await journal.read();
    expect(entries.length, BootJournal.capacity);
    expect(entries.first['stage'], 'stage_16');
    expect(entries.last['stage'], 'stage_39');
    expect(File('${directory.path}/boot_stages.json.tmp').existsSync(), isFalse);
    expect(jsonDecode(await File('${directory.path}/boot_stages.json').readAsString()), entries);
  });

  test('records begin and failure type without exception message', () async {
    await expectLater(journal.stage('resolve_auth', () async => throw StateError('private-token')), throwsStateError);
    final raw = await File('${directory.path}/boot_stages.json').readAsString();
    expect(raw, isNot(contains('private-token')));
    expect((await journal.read()).map((row) => row['state']), ['begin', 'failed']);
    expect(journal.failureStage, 'resolve_auth');
    await journal.record('startup_error', 'observed', error: StateError('another-secret'));
    expect(journal.failureStage, 'resolve_auth');
  });

  test('retains an unclosed boot boundary across a long startup', () async {
    await journal.record('boot', 'begin');
    for (var i = 0; i < BootJournal.capacity + 4; i++) {
      await journal.record('stage_$i', 'completed');
    }
    final entries = await journal.read();
    expect(entries.length, BootJournal.capacity);
    expect(entries.first['stage'], 'boot');
  });

  test('diagnostic IO failures do not break the stage operation', () async {
    final unavailable = BootJournal(documents: () async => throw const FileSystemException('unavailable'));
    expect(await unavailable.stage('shared_preferences', () async => 7), 7);
  });
}
