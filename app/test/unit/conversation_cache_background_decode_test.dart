import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';

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
