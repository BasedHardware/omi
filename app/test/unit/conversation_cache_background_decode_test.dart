import 'dart:async';
import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:shared_preferences_platform_interface/shared_preferences_platform_interface.dart';

import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/backend/schema/structured.dart';
import 'package:omi/backend/schema/transcript_segment.dart';
import 'package:omi/utils/off_ui_isolate.dart';

ServerConversation _conversation(String id, {int segments = 0}) => ServerConversation(
      id: id,
      createdAt: DateTime.utc(2026, 10, 20),
      structured: Structured('Synthetic $id', 'Synthetic summary'),
      transcriptSegments: [
        for (var i = 0; i < segments; i++)
          TranscriptSegment(
              id: '$id-$i',
              text: 'Synthetic transcript $i',
              speaker: 'SPEAKER_00',
              isUser: true,
              personId: null,
              translations: [],
              start: i * 5.0,
              end: i * 5.0 + 4),
      ],
    );

Future<SharedPreferencesUtil> _prefs(Map<String, Object> values) async {
  SharedPreferences.setMockInitialValues({'uid': 'fixture-owner', ...values});
  await SharedPreferencesUtil.init(mirrorNativeAuthToken: false);
  return SharedPreferencesUtil();
}

class _RejectingConversationCache extends InMemorySharedPreferencesStore {
  _RejectingConversationCache(super.data, {required this.throwOnLegacyWrite}) : super.withData();

  final bool throwOnLegacyWrite;

  @override
  Future<bool> setValue(String valueType, String key, Object value) async {
    if (key == 'flutter.cachedConversations') return false;
    if (key == 'flutter.cachedMemories') {
      if (throwOnLegacyWrite) throw StateError('Legacy cache write failed');
      return false;
    }
    return super.setValue(valueType, key, value);
  }
}

class _DelayedConversationCache extends InMemorySharedPreferencesStore {
  _DelayedConversationCache(super.data) : super.withData();

  final started = Completer<void>();
  final release = Completer<void>();

  @override
  Future<bool> setValue(String valueType, String key, Object value) async {
    if (key == 'flutter.cachedConversations' && !started.isCompleted) {
      started.complete();
      await release.future;
    }
    return super.setValue(valueType, key, value);
  }
}

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();
  setUp(() {
    offUiIsolateFallbacks = 0;
    SharedPreferencesUtil.cachedConversationsBackgroundDecodeThreshold = 1;
    SharedPreferencesUtil.cachedConversationsBackgroundEncodeThreshold = 1;
  });
  tearDown(() {
    SharedPreferencesUtil.cachedConversationsBackgroundDecodeThreshold = 64 * 1024;
    SharedPreferencesUtil.cachedConversationsBackgroundEncodeThreshold = 20;
  });

  test('2000 conversations with 60 segments cross the worker without inline fallback', () async {
    final encoded = [for (var i = 0; i < 2000; i++) jsonEncode(_conversation('fixture-$i', segments: 60).toJson())];
    final prefs = await _prefs({'cachedConversations': encoded});
    final restored = await prefs.loadCachedConversations();
    expect(restored, hasLength(2000));
    expect(restored.first.id, 'fixture-0');
    expect(restored.last.id, 'fixture-1999');
    expect(restored.every((conversation) => conversation.transcriptSegments.length == 60), isTrue);
    expect(offUiIsolateFallbacks, 0);
    expect(prefs.getStringList('cachedConversations'), encoded);
  });

  test('corrupt rows are skipped in order without rewriting the source cache', () async {
    final encoded = [
      jsonEncode(_conversation('a').toJson()),
      'not-json',
      '[]',
      '{"id":42}',
      jsonEncode(_conversation('b').toJson())
    ];
    final prefs = await _prefs({'cachedConversations': encoded});
    expect((await prefs.loadCachedConversations()).map((row) => row.id), ['a', 'b']);
    expect(prefs.getStringList('cachedConversations'), encoded);
    expect(offUiIsolateFallbacks, 0);
  });

  test('a racing cache write retries the new snapshot', () async {
    final prefs = await _prefs({
      'cachedConversations': [jsonEncode(_conversation('old').toJson())]
    });
    final pending = prefs.loadCachedConversations();
    prefs.cachedConversations = [_conversation('new')];
    expect((await pending).map((row) => row.id), ['new']);
  });

  test('display clear invalidates an admitted decode', () async {
    final prefs = await _prefs({
      'cachedConversations': [jsonEncode(_conversation('old').toJson())]
    });
    final pending = prefs.loadCachedConversations();
    prefs.clearUserDisplayCache();
    expect(await pending, isEmpty);
    expect(prefs.uid, isEmpty);
  });

  test('full clear invalidates decode before its asynchronous cleanup completes', () async {
    final prefs = await _prefs({
      'cachedConversations': [jsonEncode(_conversation('old').toJson())]
    });
    final pending = prefs.loadCachedConversations();
    await prefs.clear();
    expect(await pending, isEmpty);
  });

  test('owner replacement and reinitialization reject old reads', () async {
    final prefs = await _prefs({
      'cachedConversations': [jsonEncode(_conversation('old').toJson())]
    });
    final ownerChange = prefs.loadCachedConversations();
    prefs.uid = 'another-fixture-owner';
    expect(await ownerChange, isEmpty);
    final oldInstance = prefs.loadCachedConversations();
    await _prefs({
      'cachedConversations': [jsonEncode(_conversation('replacement').toJson())]
    });
    expect(await oldInstance, isEmpty);
  });

  test('legacy migration matches the synchronous getter wire normalization', () async {
    final legacy = _conversation('legacy').toJson()
      ..['plugins_results'] = [
        {'appId': 'fixture-plugin', 'content': 'Synthetic result'}
      ]
      ..['siri_visibility_valid'] = false;
    final prefs = await _prefs({
      'migratedMemories': true,
      'cachedMemories': [jsonEncode(legacy), 'not-json']
    });
    final restored = await prefs.loadCachedConversations();
    expect(restored.map((row) => row.toJson()).toList(), prefs.cachedConversations.map((row) => row.toJson()).toList());
    expect(restored.single.siriVisibilityValid, prefs.cachedConversations.single.siriVisibilityValid);
    expect(restored.single.appResults.single.appId, 'fixture-plugin');
    expect(offUiIsolateFallbacks, 0);
  });

  test('eviction removes the selected row from both cache formats off the UI isolate', () async {
    final removed = jsonEncode(_conversation('deleted', segments: 60).toJson());
    final kept = jsonEncode(_conversation('keep').toJson());
    final prefs = await _prefs({
      'migratedMemories': true,
      'cachedMemories': [removed, kept],
      'cachedConversations': [kept, removed],
    });
    final completedBefore = offUiIsolateWorkerCompletions;

    await prefs.evictCachedConversation('deleted');

    expect(prefs.getStringList('cachedConversations'), [kept]);
    expect(prefs.getStringList('cachedMemories'), [kept]);
    expect((await prefs.loadCachedConversations()).map((row) => row.id), ['keep']);
    expect(offUiIsolateWorkerCompletions, greaterThan(completedBefore));
    expect(offUiIsolateFallbacks, 0);
  });

  test('a confirmed delete survives a restart before cache eviction finishes', () async {
    final deleted = jsonEncode(_conversation('deleted').toJson());
    final kept = jsonEncode(_conversation('keep').toJson());
    final store = _DelayedConversationCache({
      'flutter.uid': 'fixture-owner',
      'flutter.cachedConversations': [deleted, kept],
    });
    SharedPreferences.setMockInitialValues({});
    SharedPreferencesStorePlatform.instance = store;
    await SharedPreferencesUtil.init(mirrorNativeAuthToken: false);
    final prefs = SharedPreferencesUtil();
    await prefs.recordConfirmedConversationDelete('deleted');
    final eviction = prefs.evictCachedConversation('deleted');
    await store.started.future;
    final interruptedDisk = await store.getAll();
    store.release.complete();
    expect(await eviction, isTrue);
    expect((await store.getAll())['flutter.pendingConversationCacheEvictions:fixture-owner'], isEmpty);

    expect(interruptedDisk['flutter.cachedConversations'], [deleted, kept]);
    SharedPreferences.setMockInitialValues(interruptedDisk);
    await SharedPreferencesUtil.init(mirrorNativeAuthToken: false);
    expect((await prefs.loadCachedConversations()).map((row) => row.id), ['keep']);
  });

  for (final throwOnLegacyWrite in [false, true]) {
    test('failed cache writes cannot bring a confirmed deletion back on restart (throw: $throwOnLegacyWrite)',
        () async {
      final removed = jsonEncode(_conversation('deleted').toJson());
      final kept = jsonEncode(_conversation('keep').toJson());
      final cache = [removed, kept];
      final store = _RejectingConversationCache({
        'flutter.uid': 'fixture-owner',
        'flutter.migratedMemories': true,
        'flutter.cachedMemories': cache,
        'flutter.cachedConversations': cache,
      }, throwOnLegacyWrite: throwOnLegacyWrite);
      SharedPreferences.setMockInitialValues({});
      SharedPreferencesStorePlatform.instance = store;
      await SharedPreferencesUtil.init(mirrorNativeAuthToken: false);
      final prefs = SharedPreferencesUtil();

      expect(await prefs.evictCachedConversation('deleted'), isFalse);

      final disk = await store.getAll();
      expect(disk['flutter.cachedConversations'], cache);
      expect(disk['flutter.cachedMemories'], cache);
      SharedPreferences.setMockInitialValues(disk);
      await SharedPreferencesUtil.init(mirrorNativeAuthToken: false);

      expect((await prefs.loadCachedConversations()).map((row) => row.id), ['keep']);
      expect(prefs.cachedConversations.map((row) => row.id), ['keep']);
      await prefs.saveBool('migratedMemories', false);
      await prefs.saveStringList('cachedConversations', cache);
      expect((await prefs.loadCachedConversations()).map((row) => row.id), ['keep']);

      prefs.uid = 'different-owner';
      expect((await prefs.loadCachedConversations()).map((row) => row.id), ['deleted', 'keep']);
    });
  }

  test('an old legacy read cannot migrate over a newer cache writer', () async {
    final prefs = await _prefs({
      'migratedMemories': true,
      'cachedMemories': [jsonEncode(_conversation('legacy').toJson())]
    });
    final pending = prefs.loadCachedConversations();
    prefs.cachedConversations = [_conversation('fresh')];
    expect(await pending, isEmpty);
    final persisted =
        prefs.getStringList('cachedConversations').map((value) => ServerConversation.fromJson(jsonDecode(value)));
    expect(persisted.map((row) => row.id), ['fresh']);
  });

  test('background cache writes cannot cross preference reinitialization or owner change', () async {
    var prefs = await _prefs({});
    final oldWrite = prefs.cacheConversations([_conversation('old')]);
    prefs = await _prefs({
      'cachedConversations': [jsonEncode(_conversation('replacement').toJson())]
    });
    await oldWrite;
    expect(prefs.cachedConversations.map((row) => row.id), ['replacement']);
    final ownerWrite = prefs.cacheConversations([_conversation('old-owner')]);
    prefs.uid = 'another-fixture-owner';
    await ownerWrite;
    expect(prefs.cachedConversations.map((row) => row.id), ['replacement']);
  });
}
