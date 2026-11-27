import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:omi/services/experiments/reliability_flags.dart';
import 'package:omi/utils/reliability_experiments.dart';

void main() {
  late Directory dir;
  Future<Directory> documents() async => dir;

  setUp(() async {
    dir = await Directory.systemTemp.createTemp('reliability_experiments_');
    ReliabilityExperiments.overrideForTesting(null);
    // No account flags unless a test supplies them.
    ReliabilityExperiments.remoteForTesting((_) => false);
  });
  tearDown(() async {
    ReliabilityExperiments.overrideForTesting(null);
    ReliabilityExperiments.remoteForTesting(null);
    // Leave the process-wide selection as an unconfigured build has it.
    await ReliabilityExperiments.load(documentsDirectory: () async => throw const FileSystemException('gone'));
    await dir.delete(recursive: true);
  });

  Future<void> writeSelection(String text) =>
      File('${dir.path}/${ReliabilityExperiments.fileName}').writeAsString(text);

  test('the fourteen app experiments are registered with a description', () {
    expect(ReliabilityExperiments.registered.keys, {
      'receipt_long_poll',
      'receipt_finished_note',
      'receipt_check_during_drain',
      'status_fetch_failure_isolated',
      'keep_cooldown_after_upload',
      'end_open_conversation',
      'fast_end_feedback',
      'end_button_by_device',
      'instant_live_text',
      'vendor_recognizer_on_opened_app',
      'phone_recogniser_mute',
      'early_title_icon',
      'no_live_player',
      'title_at_end',
    });
    expect(ReliabilityExperiments.registered.values.every((text) => text.trim().isNotEmpty), isTrue);
  });

  test('an account flag turns its own name on, with no local selection', () async {
    await ReliabilityExperiments.load(documentsDirectory: documents, compileTime: '');
    ReliabilityExperiments.remoteForTesting((name) => name == 'fast_end_feedback');
    expect(ReliabilityExperiments.enabled('fast_end_feedback'), isTrue);
    expect(ReliabilityExperiments.enabled('end_open_conversation'), isFalse);
    // Read on every call: a flag that arrives after start-up applies from then on.
    ReliabilityExperiments.remoteForTesting((_) => false);
    expect(ReliabilityExperiments.enabled('fast_end_feedback'), isFalse);
  });

  test('a test selection is exact: account flags do not add to it', () {
    ReliabilityExperiments.remoteForTesting((_) => true);
    ReliabilityExperiments.overrideForTesting({'receipt_long_poll'});
    expect(ReliabilityExperiments.enabled('receipt_long_poll'), isTrue);
    expect(ReliabilityExperiments.enabled('fast_end_feedback'), isFalse);
  });

  test('a released build ignores the define and the file, and reads no file', () async {
    await writeSelection('all');
    var asked = 0;
    await ReliabilityExperiments.load(
      documentsDirectory: () async {
        asked++;
        return dir;
      },
      compileTime: 'all',
      allowed: false,
    );
    expect(asked, 0);
    expect(ReliabilityExperiments.selected, isEmpty);
    for (final name in ReliabilityExperiments.registered.keys) {
      expect(ReliabilityExperiments.enabled(name), isFalse, reason: name);
    }
    // Its account flags still apply.
    ReliabilityExperiments.remoteForTesting((name) => name == 'early_title_icon');
    expect(ReliabilityExperiments.enabled('early_title_icon'), isTrue);
  });

  test('every remote key belongs to a registered name, and test-only names have none', () {
    expect(ReliabilityExperiments.registered.keys.toSet().containsAll(ReliabilityFlags.keys.keys), isTrue);
    expect(ReliabilityFlags.keys.keys, {
      'end_open_conversation',
      'fast_end_feedback',
      'end_button_by_device',
      'instant_live_text',
      'early_title_icon',
      'receipt_long_poll',
      'receipt_finished_note',
      'vendor_recognizer_on_opened_app',
      'no_live_player',
      'title_at_end',
    });
    expect(ReliabilityFlags.keys.values.toSet().length, ReliabilityFlags.keys.length);
    expect(ReliabilityFlags.enabled('phone_recogniser_mute', readFlag: (_) => true), isFalse);
    expect(ReliabilityFlags.enabled('receipt_long_poll', readFlag: (key) => key == 'receipt_long_poll'), isTrue);
    expect(ReliabilityFlags.enabled('receipt_long_poll', readFlag: (_) => throw StateError('no adapter')), isFalse);
  });

  test('parse accepts commas, newlines, blank items and surrounding space', () {
    expect(ReliabilityExperiments.parse(''), isEmpty);
    expect(ReliabilityExperiments.parse(' \n ,, \r\n'), isEmpty);
    expect(ReliabilityExperiments.parse('a, b\nc\r\n d ,a'), {'a', 'b', 'c', 'd'});
  });

  test('nothing is on in a build with no selection and no file', () async {
    await ReliabilityExperiments.load(documentsDirectory: documents, compileTime: '');
    expect(ReliabilityExperiments.selected, isEmpty);
    for (final name in ReliabilityExperiments.registered.keys) {
      expect(ReliabilityExperiments.enabled(name), isFalse, reason: name);
    }
  });

  test('the compile-time value selects by name, and each name is independent', () async {
    await ReliabilityExperiments.load(
        documentsDirectory: documents, compileTime: 'keep_cooldown_after_upload, receipt_long_poll');
    expect(ReliabilityExperiments.enabled('keep_cooldown_after_upload'), isTrue);
    expect(ReliabilityExperiments.enabled('receipt_long_poll'), isTrue);
    expect(ReliabilityExperiments.enabled('receipt_check_during_drain'), isFalse);
    expect(ReliabilityExperiments.enabled('status_fetch_failure_isolated'), isFalse);
  });

  test('all turns on every registered experiment', () async {
    await ReliabilityExperiments.load(documentsDirectory: documents, compileTime: 'all');
    for (final name in ReliabilityExperiments.registered.keys) {
      expect(ReliabilityExperiments.enabled(name), isTrue, reason: name);
    }
  });

  test('an unregistered name throws, also when all is selected', () async {
    expect(() => ReliabilityExperiments.enabled('no_such_experiment'), throwsArgumentError);
    await ReliabilityExperiments.load(documentsDirectory: documents, compileTime: 'all');
    expect(() => ReliabilityExperiments.enabled('no_such_experiment'), throwsArgumentError);
    expect(() => ReliabilityExperiments.enabled('all'), throwsArgumentError);
  });

  test('a selected name this build does not know is reported and turns nothing on', () async {
    await ReliabilityExperiments.load(
        documentsDirectory: documents, compileTime: 'no_such_experiment,recipt_long_poll');
    expect(ReliabilityExperiments.unknown, {'no_such_experiment', 'recipt_long_poll'});
    expect(ReliabilityExperiments.enabled('receipt_long_poll'), isFalse);
  });

  test('the file replaces the compile-time value', () async {
    await writeSelection('status_fetch_failure_isolated\nreceipt_check_during_drain\n');
    await ReliabilityExperiments.load(documentsDirectory: documents, compileTime: 'keep_cooldown_after_upload');
    expect(ReliabilityExperiments.selected, {'status_fetch_failure_isolated', 'receipt_check_during_drain'});
    expect(ReliabilityExperiments.enabled('status_fetch_failure_isolated'), isTrue);
    expect(ReliabilityExperiments.enabled('receipt_check_during_drain'), isTrue);
    expect(ReliabilityExperiments.enabled('keep_cooldown_after_upload'), isFalse);
  });

  test('an empty file means none, even when the build selected all', () async {
    await writeSelection(' \n');
    await ReliabilityExperiments.load(documentsDirectory: documents, compileTime: 'all');
    expect(ReliabilityExperiments.selected, isEmpty);
    expect(ReliabilityExperiments.enabled('receipt_long_poll'), isFalse);
  });

  test('a file can select all', () async {
    await writeSelection('all');
    await ReliabilityExperiments.load(documentsDirectory: documents, compileTime: '');
    expect(ReliabilityExperiments.enabled('keep_cooldown_after_upload'), isTrue);
  });

  test('load never throws: an unavailable directory or unreadable file keeps the compile-time value', () async {
    await ReliabilityExperiments.load(
        documentsDirectory: () async => throw const FileSystemException('no documents directory'),
        compileTime: 'receipt_long_poll');
    expect(ReliabilityExperiments.selected, {'receipt_long_poll'});

    // A directory where the file should be is not a selection file.
    await Directory('${dir.path}/${ReliabilityExperiments.fileName}').create();
    await ReliabilityExperiments.load(documentsDirectory: documents, compileTime: 'keep_cooldown_after_upload');
    expect(ReliabilityExperiments.selected, {'keep_cooldown_after_upload'});

    await ReliabilityExperiments.load(
        documentsDirectory: () => Future<Directory>.error(StateError('plugin missing')), compileTime: '');
    expect(ReliabilityExperiments.selected, isEmpty);
  });

  test('a later load re-reads the file', () async {
    await writeSelection('receipt_long_poll');
    await ReliabilityExperiments.load(documentsDirectory: documents);
    expect(ReliabilityExperiments.enabled('receipt_long_poll'), isTrue);
    await File('${dir.path}/${ReliabilityExperiments.fileName}').delete();
    await ReliabilityExperiments.load(documentsDirectory: documents, compileTime: '');
    expect(ReliabilityExperiments.enabled('receipt_long_poll'), isFalse);
  });

  test('the test override wins over the loaded selection and can be removed', () async {
    await ReliabilityExperiments.load(documentsDirectory: documents, compileTime: 'receipt_long_poll');
    ReliabilityExperiments.overrideForTesting({'keep_cooldown_after_upload'});
    expect(ReliabilityExperiments.enabled('keep_cooldown_after_upload'), isTrue);
    expect(ReliabilityExperiments.enabled('receipt_long_poll'), isFalse);
    ReliabilityExperiments.overrideForTesting({});
    expect(ReliabilityExperiments.enabled('receipt_long_poll'), isFalse);
    ReliabilityExperiments.overrideForTesting({'all'});
    expect(ReliabilityExperiments.enabled('status_fetch_failure_isolated'), isTrue);
    ReliabilityExperiments.overrideForTesting(null);
    expect(ReliabilityExperiments.enabled('receipt_long_poll'), isTrue);
    expect(() => ReliabilityExperiments.overrideForTesting({'typo'}), throwsArgumentError);
  });
}
