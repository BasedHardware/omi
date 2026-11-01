import 'dart:convert';
import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:path_provider_platform_interface/path_provider_platform_interface.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/preferences_quarantine.dart';

class _Documents extends PathProviderPlatform {
  _Documents(this.path);
  final String path;
  @override
  Future<String> getApplicationDocumentsPath() async => path;
}

/// Installs that ran a build with the untyped-list bug had their string lists archived as JSON and
/// deleted. The first launch of a fixed build puts them back, once, before pruning would drop them.
void main() {
  TestWidgetsFlutterBinding.ensureInitialized();
  late Directory documents;
  late PathProviderPlatform previous;

  setUp(() async {
    documents = await Directory.systemTemp.createTemp('quarantine-restore-');
    previous = PathProviderPlatform.instance;
    PathProviderPlatform.instance = _Documents(documents.path);
  });
  tearDown(() async {
    PathProviderPlatform.instance = previous;
    await documents.delete(recursive: true);
    SharedPreferences.setMockInitialValues(<String, Object>{});
  });

  String archiveOf(String key, Duration ago) => '$key.corrupt-${DateTime.now().subtract(ago).microsecondsSinceEpoch}';
  Iterable<String> archives(SharedPreferences prefs) => prefs.getKeys().where((k) => k.contains('.corrupt-'));
  Future<List<dynamic>> journal() async =>
      jsonDecode(await File('${documents.path}/boot_stages.json').readAsString()) as List<dynamic>;

  test('a string list archived by the bug is restored on the first fixed launch', () async {
    SharedPreferences.setMockInitialValues(<String, Object>{
      archiveOf('cachedTranscriptionVocabulary', const Duration(days: 20)): jsonEncode(['Omi', 'Tailscale']),
    });
    await SharedPreferencesUtil.init();
    final prefs = await SharedPreferences.getInstance();

    expect(prefs.getStringList('cachedTranscriptionVocabulary'), ['Omi', 'Tailscale'],
        reason: 'past the retention window, pruning alone would have dropped the last copy');
    expect(archives(prefs), isEmpty);
    expect(prefs.getBool(PreferenceQuarantine.restoredMarkerKey), isTrue);
    expect(
        await journal(),
        contains(predicate<Map<String, dynamic>>(
            (e) => e['stage'] == 'quarantine:cachedTranscriptionVocabulary' && e['state'] == 'restored')));
  });

  test('the legacy Limitless queue is restored and its spent migration re-opened', () async {
    SharedPreferences.setMockInitialValues(<String, Object>{
      archiveOf('flash_page_pending_uploads', const Duration(days: 3)): jsonEncode(['/docs/audio_limitless_1.bin']),
      'limitless_wal_migration_v1': true,
    });
    await SharedPreferencesUtil.init();
    final prefs = await SharedPreferences.getInstance();

    expect(prefs.getStringList('flash_page_pending_uploads'), ['/docs/audio_limitless_1.bin']);
    expect(prefs.containsKey('limitless_wal_migration_v1'), isFalse,
        reason: 'the migration marked itself done after reading the queue the bug had emptied');
  });

  test('of several archives of a key, the newest is restored', () async {
    // The buggy build archived a key on every launch, so most keys hold many copies.
    SharedPreferences.setMockInitialValues(<String, Object>{
      archiveOf('cachedTranscriptionVocabulary', const Duration(days: 3)): jsonEncode(['old']),
      archiveOf('cachedTranscriptionVocabulary', const Duration(hours: 1)): jsonEncode(['new']),
    });
    await SharedPreferencesUtil.init();
    final prefs = await SharedPreferences.getInstance();

    expect(prefs.getStringList('cachedTranscriptionVocabulary'), ['new']);
    expect(archives(prefs), isEmpty);
  });

  test('an empty Limitless queue is restored without re-opening its migration', () async {
    SharedPreferences.setMockInitialValues(<String, Object>{
      archiveOf('flash_page_pending_uploads', const Duration(days: 3)): jsonEncode(<String>[]),
      'limitless_wal_migration_v1': true,
    });
    await SharedPreferencesUtil.init();
    final prefs = await SharedPreferences.getInstance();

    expect(prefs.getBool('limitless_wal_migration_v1'), isTrue, reason: 'nothing waits to be migrated');
  });

  test('restore never overwrites a live value, nor brings back a genuinely corrupt list', () async {
    SharedPreferences.setMockInitialValues(<String, Object>{
      'cachedPeople': <Object?>['live'],
      archiveOf('cachedPeople', const Duration(hours: 1)): jsonEncode(['stale']),
      archiveOf('cachedMessages', const Duration(hours: 1)): jsonEncode(['ok', 42]),
      archiveOf('cachedTranscriptionVocabulary', const Duration(hours: 1)): jsonEncode(['Omi']),
    });
    await SharedPreferencesUtil.init();
    final prefs = await SharedPreferences.getInstance();

    expect(SharedPreferencesUtil().getStringList('cachedPeople'), ['live']);
    expect(prefs.containsKey('cachedMessages'), isFalse);
    expect(archives(prefs).where((k) => k.startsWith('cachedMessages.corrupt-')), hasLength(1),
        reason: 'a list holding a non-string stays archived for inspection');
    expect(prefs.getStringList('cachedTranscriptionVocabulary'), ['Omi'],
        reason: 'a corrupt neighbour must not abort the restore of a valid list');
    expect(prefs.getBool(PreferenceQuarantine.restoredMarkerKey), isTrue);
  });

  test('restore runs once: a list removed later is not brought back', () async {
    final archive = archiveOf('cachedTranscriptionVocabulary', const Duration(hours: 1));
    SharedPreferences.setMockInitialValues(<String, Object>{
      archive: jsonEncode(['Omi']),
      PreferenceQuarantine.restoredMarkerKey: true,
    });
    await SharedPreferencesUtil.init();
    final prefs = await SharedPreferences.getInstance();

    expect(prefs.containsKey('cachedTranscriptionVocabulary'), isFalse);
    expect(prefs.containsKey(archive), isTrue);
  });

  test('a successful archive replaces the previous archive of the same key', () async {
    final previous = archiveOf('cachedPeople', const Duration(minutes: 5));
    SharedPreferences.setMockInitialValues(<String, Object>{'cachedPeople': 'bad', previous: 'older'});
    final prefs = await SharedPreferences.getInstance();

    await PreferenceQuarantine.archive(prefs, 'cachedPeople', 'bad', reason: 'test');

    final left = archives(prefs).toList();
    expect(left, hasLength(1));
    expect(left.single, isNot(previous));
    expect(prefs.getString(left.single), 'bad');
    expect(prefs.containsKey('cachedPeople'), isFalse);
  });

  test('an oversized value is dropped with its old archives, and the size is journaled', () async {
    final previous = archiveOf('cachedPeople', const Duration(minutes: 5));
    final huge = 'x' * (PreferenceQuarantine.maxArchivedChars + 1);
    SharedPreferences.setMockInitialValues(<String, Object>{'cachedPeople': huge, previous: 'older'});
    final prefs = await SharedPreferences.getInstance();

    await PreferenceQuarantine.archive(prefs, 'cachedPeople', huge, reason: 'type_mismatch');

    expect(archives(prefs), isEmpty);
    expect(prefs.containsKey('cachedPeople'), isFalse);
    expect(
        await journal(),
        contains(predicate<Map<String, dynamic>>((e) =>
            e['stage'] == 'quarantine:cachedPeople' &&
            e['state'] == 'type_mismatch_too_large_${PreferenceQuarantine.maxArchivedChars + 1}')));
  });
}
